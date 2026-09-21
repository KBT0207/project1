import os

from .models import WhatsAppConfig


def get_config():
    active = WhatsAppConfig.objects.filter(is_active=True).first()

    if active:
        return {
            "source": active.name,
            "access_token": active.access_token,
            "phone_number_id": active.phone_number_id,
            "verify_token": active.verify_token,
            "app_secret": active.app_secret,
            "api_version": active.api_version,
            "default_template": active.default_template,
            "default_language": active.default_language,
        }

    return {
        "source": ".env",
        "access_token": os.getenv("ACCESS_TOKEN", ""),
        "phone_number_id": os.getenv("PHONE_NUMBER_ID", ""),
        "verify_token": os.getenv("VERIFY_TOKEN", ""),
        "app_secret": os.getenv("APP_SECRET", ""),
        "api_version": os.getenv("API_VERSION", "v21.0"),
        "default_template": os.getenv("TEMPLATE_NAME", "invoice_simple"),
        "default_language": os.getenv("TEMPLATE_LANG", "en"),
    }
