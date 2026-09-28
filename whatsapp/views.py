import functools
import hashlib
import hmac
import json
import os
import re
import tempfile

import requests
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt

from . import services
from .config import get_config
from .forms import WhatsAppConfigForm
from .models import WebhookEvent, WhatsAppConfig, WhatsAppMessage


STATUS_RANK = {"accepted": 0, "sent": 1, "delivered": 2, "read": 3}

PIPELINE = [
    ("accepted", "Accepted", "Meta received it"),
    ("sent", "Sent", "Left Meta's servers"),
    ("delivered", "Delivered", "On the customer's phone"),
    ("read", "Read", "Customer opened it"),
]

URL_RE = re.compile(r"https?://\S+")
AMOUNT_RE = re.compile(r"(?:Rs\.?|INR|₹)\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE)


def valid_signature(request, app_secret):
    if not app_secret:
        return True
    received = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(
        app_secret.encode(), request.body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(received, expected)


def update_status(status_data):
    message = WhatsAppMessage.objects.filter(wa_message_id=status_data.get("id")).first()
    if not message:
        return

    new_status = status_data.get("status")

    if new_status == "failed":
        message.status = "failed"
        message.error = json.dumps(status_data.get("errors", []))
    elif STATUS_RANK.get(new_status, -1) > STATUS_RANK.get(message.status, -1):
        message.status = new_status

    message.save()


@csrf_exempt
def whatsapp_webhook(request):
    cfg = get_config()

    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge", "")
        if mode == "subscribe" and cfg["verify_token"] and token == cfg["verify_token"]:
            return HttpResponse(challenge, content_type="text/plain")
        return HttpResponse("Forbidden", status=403)

    if request.method != "POST":
        return HttpResponse(status=405)

    if not valid_signature(request, cfg["app_secret"]):
        return HttpResponse("Invalid signature", status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse("Bad request", status=400)

    WebhookEvent.objects.create(payload=data)

    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            for status_data in change.get("value", {}).get("statuses", []):
                update_status(status_data)

    return JsonResponse({"ok": True})


# ---------------------------------------------------------------------------
# BUSY integration
# ---------------------------------------------------------------------------

DEBUG_SENSITIVE = {"key", "password", "token", "access_token", "secret", "authorization"}


def log_request(view):
    """Save what any request contains on the Webhook events tab, then run the view."""
    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        raw = request.body  # read before request.POST
        WebhookEvent.objects.create(payload={
            "debug": True,
            "method": request.method,
            "path": request.path,
            "query": {k: ("••••" if k.lower() in DEBUG_SENSITIVE else v)
                      for k, v in request.GET.dict().items()},
            "form": {k: ("••••" if k.lower() in DEBUG_SENSITIVE else v)
                     for k, v in request.POST.dict().items()},
            "raw_body": raw.decode("utf-8", "replace")[:5000],
            "headers": {k: v for k, v in request.headers.items()
                        if k.lower() not in ("authorization", "cookie")},
            "remote_addr": request.META.get("REMOTE_ADDR", ""),
        })
        return view(request, *args, **kwargs)
    return wrapper


@csrf_exempt
@log_request
def debug_echo(request):
    """Catch-all test endpoint. Point any system here to see what it sends. Remove when done."""
    return JsonResponse({"received": True})


SENSITIVE_KEYS = {"key", "password", "token", "access_token", "secret"}


def normalize_mobile(raw, country_code="91"):
    """Return digits only, with the country code added to 10-digit numbers."""
    digits = re.sub(r"\D", "", raw or "")
    digits = digits.lstrip("0")
    if len(digits) == 10:
        digits = country_code + digits
    return digits


def read_params(request, raw):
    """Merge query string, form body and JSON body into one dict."""
    params = request.GET.dict()
    params.update(request.POST.dict())
    if raw and "json" in (request.content_type or ""):
        try:
            body = json.loads(raw)
        except ValueError:
            body = None
        if isinstance(body, dict):
            params.update({k: str(v) for k, v in body.items()})
    return params


def scrub(text, secret):
    """Hide the secret key before anything is stored in the log."""
    return text.replace(secret, "••••") if secret else text


@csrf_exempt
def busy_send(request):
    """
    Called by BUSY. Accepts GET or POST (query string, form or JSON):
        key         BUSY API key saved on the active connection
        mobile      customer number
        message     text that contains the PDF link (or use `link`)
        link        (optional) direct PDF link
        file        (optional) the PDF itself, sent as a file upload (multipart POST)
                    or as the raw request body (body starting with %PDF)
        name        (optional) customer name for template variable {{1}}
        amount      (optional) invoice amount for template variable {{2}}
        invoice_no  (optional) for reference on the dashboard
        filename    (optional) name shown in WhatsApp

    Every call is saved on the dashboard "Webhook events" tab: what BUSY sent
    (key hidden), where it came from, and what we answered.
    """
    raw = request.body  # read first, before touching request.POST
    params = read_params(request, raw)
    secret = params.get("key", "")

    event = WebhookEvent.objects.create(
        payload={
            "busy": {
                k: (WhatsAppConfig.mask(v) if k.lower() in SENSITIVE_KEYS else v)
                for k, v in params.items()
            },
            "method": request.method,
            "content_type": request.content_type,
            "remote_addr": request.META.get("REMOTE_ADDR", ""),
            "forwarded_for": request.META.get("HTTP_X_FORWARDED_FOR", ""),
            "user_agent": request.META.get("HTTP_USER_AGENT", ""),
            "query_string": scrub(request.META.get("QUERY_STRING", "")[:2000], secret),
            "files": {name: f"{f.name}, {f.size} bytes" for name, f in request.FILES.items()},
            "body_is_pdf": raw.startswith(b"%PDF"),
            "raw_body": "(PDF file)" if raw.startswith(b"%PDF") else scrub(raw.decode("utf-8", "replace")[:2000], secret),
        }
    )

    def finish(body, status, note=""):
        event.payload["result"] = {"status": status, "note": note, **body}
        event.save(update_fields=["payload"])
        return JsonResponse(body, status=status)

    cfg = get_config()
    api_key = cfg["busy_api_key"]
    if not api_key:
        return finish({"error": "unauthorized"}, 403, "Busy api key is not set on the active connection")
    if not hmac.compare_digest(secret.encode(), api_key.encode()):
        return finish({"error": "unauthorized"}, 403, "key sent by BUSY does not match the saved key")

    to = normalize_mobile(params.get("mobile"), cfg["default_country_code"])
    message = params.get("message", "")
    found = URL_RE.search(message)
    link = params.get("link") or (found.group(0) if found else "")

    # The PDF can arrive as an uploaded file, as the raw body, or as a link
    pdf_bytes = None
    pdf_source = ""
    if request.FILES:
        uploaded = next(iter(request.FILES.values()))
        pdf_bytes, pdf_source = uploaded.read(), f"uploaded file {uploaded.name}"
    elif raw.startswith(b"%PDF"):
        pdf_bytes, pdf_source = raw, "raw request body"

    if not to or not (pdf_bytes or link):
        return finish(
            {"error": "mobile and a PDF (file or link) are required"},
            400,
            f"mobile={'ok' if to else 'missing'}, file={'ok' if pdf_bytes else 'missing'}, "
            f"link={'ok' if link else 'missing'}",
        )

    # Template test_templates needs two body variables: {{1}} name, {{2}} amount.
    # Use explicit `name` / `amount` params if BUSY sends them, otherwise try to
    # read the amount from the message text. WhatsApp params cannot be empty or
    # contain newlines.
    amount_match = AMOUNT_RE.search(message)
    name = " ".join((params.get("name") or "Customer").split())
    amount = " ".join(
        (params.get("amount") or (amount_match.group(1) if amount_match else "") or "-").split()
    )

    # Get the PDF (download it if we only have a link), upload it to Meta, send by media id
    try:
        if not pdf_bytes:
            pdf = requests.get(link, timeout=30)
            pdf.raise_for_status()
            pdf_bytes, pdf_source = pdf.content, f"link {link}"
        if not pdf_bytes.startswith(b"%PDF"):
            return finish({"error": "not a PDF"}, 400, f"{pdf_source} is not a direct PDF")

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
        try:
            media_id = services.upload_media(tmp.name)
        finally:
            os.remove(tmp.name)
    except Exception as exc:
        return finish({"error": f"pdf fetch/upload failed: {exc}"}, 502, pdf_source or f"link={link}")

    msg = services.send_template(
        to,
        components=[
            services.doc_header(media_id=media_id, filename=params.get("filename", "invoice.pdf")),
            services.body(name, amount),
        ],
        reference_type="busy",
        reference_id=params.get("invoice_no", ""),
    )
    return finish(
        {"status": msg.status, "id": msg.wa_message_id, "error": msg.error},
        200 if msg.status != "failed" else 502,
        f"to={to}, name={name}, amount={amount}, pdf from {pdf_source}",
    )


# ---------------------------------------------------------------------------
# Dashboard and config
# ---------------------------------------------------------------------------

@login_required(login_url="login")
def dashboard(request):
    tab = request.GET.get("tab", "messages")
    status = request.GET.get("status", "")
    query = request.GET.get("q", "").strip()

    messages = WhatsAppMessage.objects.all()
    if status:
        messages = messages.filter(status=status)
    if query:
        messages = messages.filter(
            Q(to_number__icontains=query)
            | Q(reference_id__icontains=query)
            | Q(reference_type__icontains=query)
            | Q(template_name__icontains=query)
        )

    counts = {
        row["status"]: row["total"]
        for row in WhatsAppMessage.objects.values("status").annotate(total=Count("id"))
    }
    total = sum(counts.values())

    def build_step(key, label, hint):
        count = counts.get(key, 0)
        return {
            "key": key,
            "label": label,
            "hint": hint,
            "count": count,
            "percent": round(count * 100 / total) if total else 0,
        }

    context = {
        "tab": tab,
        "status": status,
        "query": query,
        "total": total,
        "pipeline": [build_step(*step) for step in PIPELINE],
        "failed": build_step("failed", "Failed", "Not delivered"),
        "messages": messages[:200],
        "events": WebhookEvent.objects.all()[:50],
        "configs": WhatsAppConfig.objects.all().order_by("-is_active", "name"),
        "active": get_config(),
        "webhook_url": request.build_absolute_uri("/webhook/whatsapp/"),
        "busy_url": request.build_absolute_uri("/api/busy/send/"),
    }
    return render(request, "whatsapp/dashboard.html", context)


@login_required(login_url="login")
def whatsapp_config(request):
    if request.method == "POST":
        form = WhatsAppConfigForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("whatsapp_dashboard")
    else:
        form = WhatsAppConfigForm()

    return render(request, "whatsapp/whatsapp_config.html", {"form": form})


@login_required(login_url="login")
def whatsapp_config_edit(request, pk):
    config = get_object_or_404(WhatsAppConfig, pk=pk)
    if request.method == "POST":
        form = WhatsAppConfigForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            return redirect("whatsapp_dashboard")
    else:
        form = WhatsAppConfigForm(instance=config)

    return render(
        request,
        "whatsapp/whatsapp_edit.html",
        {"config": config, "form": form},
    )


@login_required(login_url="login")
def whatsapp_config_delete(request, pk):
    config = get_object_or_404(WhatsAppConfig, pk=pk)
    config.delete()
    return redirect("whatsapp_dashboard")


def login(request):
    if request.user.is_authenticated:
        return redirect("whatsapp_dashboard")

    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            auth_login(request, form.get_user())
            next_url = request.GET.get("next", "whatsapp_dashboard")
            return redirect(next_url)
    else:
        form = AuthenticationForm()

    return render(request, "login.html", {"form": form})


def logout(request):
    auth_logout(request)
    return redirect("login")



# ---------------------------------------------------------------------------
# Debug page: everything BUSY (or /api/debug/) sent us
# ---------------------------------------------------------------------------

def _debug_rows(kind="all", query=""):
    rows = []
    for event in WebhookEvent.objects.all()[:300]:
        p = event.payload
        if "busy" in p:
            source, fields = "BUSY", p["busy"]
        elif p.get("debug"):
            source, fields = "Debug", {**p.get("query", {}), **p.get("form", {})}
        else:
            continue

        result = p.get("result", {})
        status = result.get("status")
        row = {
            "id": event.pk,
            "received_at": event.received_at,
            "source": source,
            "method": p.get("method", ""),
            "path": p.get("path") or ("/api/busy/send/" if source == "BUSY" else ""),
            "mobile": fields.get("mobile", ""),
            "message": str(fields.get("message", "")),
            "status": status,
            "failed": isinstance(status, int) and status >= 400,
            "note": result.get("note") or result.get("error", ""),
            "fields": fields,
            "remote_addr": p.get("remote_addr", ""),
            "pretty": event.pretty_payload,
        }

        if kind == "busy" and source != "BUSY":
            continue
        if kind == "debug" and source != "Debug":
            continue
        if kind == "errors" and not row["failed"]:
            continue
        if query and query.lower() not in f"{row['mobile']} {row['message']} {row['note']}".lower():
            continue
        rows.append(row)
    return rows[:100]


@login_required(login_url="login")
def debug_page(request):
    kind = request.GET.get("kind", "all")
    query = request.GET.get("q", "").strip()
    context = {
        "kind": kind,
        "query": query,
        "rows": _debug_rows(kind, query),
        "busy_url": request.build_absolute_uri("/api/busy/send/"),
        "debug_url": request.build_absolute_uri("/api/debug/"),
    }
    return render(request, "whatsapp/debug.html", context)


@login_required(login_url="login")
def debug_clear(request):
    if request.method == "POST":
        ids = [
            e.pk for e in WebhookEvent.objects.all()
            if "busy" in e.payload or e.payload.get("debug")
        ]
        WebhookEvent.objects.filter(pk__in=ids).delete()
    return redirect("whatsapp_debug")