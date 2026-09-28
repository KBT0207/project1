import os

from .models import WhatsAppConfig


def get_config():
    """Return the active connection from the database.

    If no connection is active, fall back to .env so the app still works
    during first setup.
    """
    active = WhatsAppConfig.objects.filter(is_active=True).first()

    if active:
        return {
            "source": active.name,
            "access_token": active.access_token,
            "phone_number_id": active.phone_number_id,
            "waba_id": active.waba_id,
            "verify_token": active.verify_token,
            "app_secret": active.app_secret,
            "busy_api_key": active.busy_api_key,
            "api_version": active.api_version,
            "default_template": active.default_template,
            "default_language": active.default_language,
            "default_country_code": active.default_country_code,
        }

    return {
        "source": ".env",
        "access_token": os.getenv("ACCESS_TOKEN", ""),
        "phone_number_id": os.getenv("PHONE_NUMBER_ID", ""),
        "waba_id": os.getenv("WABA_ID", ""),
        "verify_token": os.getenv("VERIFY_TOKEN", ""),
        "app_secret": os.getenv("APP_SECRET", ""),
        "busy_api_key": os.getenv("BUSY_API_KEY", ""),
        "api_version": os.getenv("API_VERSION", "v25.0"),
        "default_template": os.getenv("TEMPLATE_NAME", "test_templates"),
        "default_language": os.getenv("TEMPLATE_LANG", "en"),
        "default_country_code": os.getenv("COUNTRY_CODE", "91"),
    }
