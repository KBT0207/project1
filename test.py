import os
import requests
from dotenv import load_dotenv

load_dotenv()

URL = 'https://graph.facebook.com/v25.0'
WABA_ID = os.getenv('WABA_ID')
PHONE_NUMBER_ID = os.getenv('PHONE_NUMBER_ID')
ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')


def test(url, phone_number_id, access_token, to):
    res = requests.post(
        url=f"{url}/{phone_number_id}/messages",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "messaging_product": "whatsapp",
            "to": f"91{to}",
            "type": "template",
            "template": {"name": "hello_world", "language": {"code": "en_US"}},
        },
    )
    print(res.json())
    return res.json()


def check_template_status(url, waba_id, access_token, name):
    """Confirm the template is approved and get its exact language code."""
    res = requests.get(
        url=f"{url}/{waba_id}/message_templates",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"name": name}
    )
    data = res.json()
    print("Template status check:", data)
    return data


def send_template_message(url, phone_number_id, access_token, to, template_name, lang_code="en_US", body_params=None):
    """Send a pre-approved WhatsApp template message."""
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": lang_code},
        }
    }

    if body_params:
        payload["template"]["components"] = [
            {
                "type": "body",
                "parameters": [{"type": "text", "text": p} for p in body_params]
            }
        ]

    res = requests.post(
        url=f"{url}/{phone_number_id}/messages",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        },
        json=payload
    )
    print("Send status:", res.status_code, res.json())
    return res.json()


def upload_media(url, phone_number_id, access_token, file_path):
    """Upload a local PDF to Meta's servers and get back a media ID."""
    with open(file_path, 'rb') as f:
        res = requests.post(
            url=f"{url}/{phone_number_id}/media",
            headers={"Authorization": f"Bearer {access_token}"},
            files={
                "file": (os.path.basename(file_path), f, "application/pdf")
            },
            data={
                "messaging_product": "whatsapp",
                "type": "application/pdf"
            }
        )
    data = res.json()
    print("Upload result:", data)
    return data

def send_pdf_template_by_id(url, phone_number_id, access_token, to, template_name,
                            language_code, media_id, body_params, filename="invoice.pdf"):
    res = requests.post(
        url=f"{url}/{phone_number_id}/messages",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": [
                    {
                        "type": "header",
                        "parameters": [
                            {"type": "document",
                             "document": {"id": media_id, "filename": filename}}
                        ],
                    },
                    {
                        "type": "body",
                        "parameters": [{"type": "text", "text": str(p)} for p in body_params],
                    },
                ],
            },
        },
    )
    data = res.json()
    print("Send result:", res.status_code, data)
    return data

if __name__ == "__main__":
    TEMPLATE_NAME = "test_templates"
    LANGUAGE_CODE = "en"
    RECIPIENT = "919137860167"
    PDF_PATH = "2620498169.pdf"

    BODY_PARAMS = ["Vivek", "2,500"]

    check_template_status(URL, WABA_ID, ACCESS_TOKEN, TEMPLATE_NAME)

    upload = upload_media(URL, PHONE_NUMBER_ID, ACCESS_TOKEN, PDF_PATH)
    media_id = upload.get("id")
    if not media_id:
        raise SystemExit(f"Upload failed: {upload}")

    send_pdf_template_by_id(
        url=URL,
        phone_number_id=PHONE_NUMBER_ID,
        access_token=ACCESS_TOKEN,
        to=RECIPIENT,
        template_name=TEMPLATE_NAME,
        language_code=LANGUAGE_CODE,
        media_id=media_id,
        body_params=BODY_PARAMS,
        filename=os.path.basename(PDF_PATH),
    )