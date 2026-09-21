import json
import os

import requests

from .config import get_config
from .models import WhatsAppMessage


def _base_url(cfg):
    return f"https://graph.facebook.com/{cfg['api_version']}/{cfg['phone_number_id']}"


def _auth(cfg):
    return {"Authorization": f"Bearer {cfg['access_token']}"}


def _send(payload, template_name="", reference_type="", reference_id=""):
    cfg = get_config()

    try:
        response = requests.post(
            f"{_base_url(cfg)}/messages",
            headers=_auth(cfg),
            json=payload,
            timeout=30,
        )
        result = response.json()
    except (requests.RequestException, ValueError) as exc:
        result = {"error": {"message": str(exc)}}

    message_id = (result.get("messages") or [{}])[0].get("id")

    return WhatsAppMessage.objects.create(
        template_name=template_name,
        reference_type=reference_type,
        reference_id=str(reference_id),
        to_number=payload["to"],
        wa_message_id=message_id,
        status="accepted" if message_id else "failed",
        error="" if message_id else json.dumps(result.get("error", result)),
        payload=payload,
    )


def upload_media(path):
    cfg = get_config()
    filename = os.path.basename(path)
    with open(path, "rb") as f:
        response = requests.post(
            f"{_base_url(cfg)}/media",
            headers=_auth(cfg),
            data={"messaging_product": "whatsapp", "type": "application/pdf"},
            files={"file": (filename, f, "application/pdf")},
            timeout=60,
        )
    return response.json()["id"]


def send_template(to, template=None, components=None, language=None, reference_type="", reference_id=""):
    cfg = get_config()
    template = template or cfg["default_template"]
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {"name": template, "language": {"code": language or cfg["default_language"]}},
    }
    if components:
        payload["template"]["components"] = components
    return _send(payload, template, reference_type, reference_id)


def send_document(to, link=None, media_id=None, filename="invoice.pdf", caption="", reference_type="", reference_id=""):
    document = {"filename": filename}
    document.update({"link": link} if link else {"id": media_id})
    if caption:
        document["caption"] = caption
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "document",
        "document": document,
    }
    return _send(payload, "document (no template)", reference_type, reference_id)


def doc_header(link=None, media_id=None, filename="invoice.pdf"):
    document = {"filename": filename}
    document.update({"link": link} if link else {"id": media_id})
    return {"type": "header", "parameters": [{"type": "document", "document": document}]}


def body(*values):
    return {"type": "body", "parameters": [{"type": "text", "text": str(v)} for v in values]}
