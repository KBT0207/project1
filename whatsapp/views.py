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

def normalize_mobile(raw):
    """Return digits only, with 91 added for 10-digit Indian numbers."""
    digits = re.sub(r"\D", "", raw or "")
    digits = digits.lstrip("0")
    if len(digits) == 10:
        digits = "91" + digits
    return digits


@csrf_exempt
def busy_send(request):
    """
    Called by BUSY. Expects (GET or POST):
        key         shared secret (BUSY_API_KEY in .env)
        mobile      customer number
        message     text that contains the PDF link (or use `link`)
        link        (optional) direct PDF link
        invoice_no  (optional) for reference on the dashboard
        filename    (optional) name shown in WhatsApp
    """
    data = request.GET if request.method == "GET" else request.POST

    # Log exactly what BUSY sends so you can inspect it on the dashboard "events" tab
    WebhookEvent.objects.create(
        payload={"busy": dict(data.items()), "method": request.method}
    )

    api_key = os.getenv("BUSY_API_KEY", "")
    if not api_key or not hmac.compare_digest(data.get("key", ""), api_key):
        return JsonResponse({"error": "unauthorized"}, status=403)

    to = normalize_mobile(data.get("mobile"))
    message = data.get("message", "")
    found = URL_RE.search(message)
    link = data.get("link") or (found.group(0) if found else "")
    # WhatsApp template params cannot contain newlines
    text = " ".join(URL_RE.sub("", message).split()) or "your invoice"

    if not to or not link:
        return JsonResponse({"error": "mobile and a PDF link are required"}, status=400)

    # Download the PDF, upload it to Meta, then send by media id
    try:
        pdf = requests.get(link, timeout=30)
        pdf.raise_for_status()
        if not pdf.content.startswith(b"%PDF"):
            return JsonResponse({"error": "link is not a direct PDF"}, status=400)

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf.content)
        try:
            media_id = services.upload_media(tmp.name)
        finally:
            os.remove(tmp.name)
    except Exception as exc:
        return JsonResponse({"error": f"pdf fetch/upload failed: {exc}"}, status=502)

    msg = services.send_template(
        to,
        components=[
            services.doc_header(media_id=media_id, filename=data.get("filename", "invoice.pdf")),
            services.body(text),
        ],
        reference_type="busy",
        reference_id=data.get("invoice_no", ""),
    )
    return JsonResponse(
        {"status": msg.status, "id": msg.wa_message_id, "error": msg.error},
        status=200 if msg.status != "failed" else 502,
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