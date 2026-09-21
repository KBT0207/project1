import json

from django.db import models


class WhatsAppConfig(models.Model):
    name = models.CharField(max_length=50, unique=True, help_text="For example: test or production")
    access_token = models.TextField()
    phone_number_id = models.CharField(max_length=50)
    verify_token = models.CharField(max_length=100)
    app_secret = models.CharField(max_length=100, blank=True)
    api_version = models.CharField(max_length=10, default="v21.0")
    default_template = models.CharField(max_length=100, blank=True, default="invoice_simple")
    default_language = models.CharField(max_length=10, default="en")
    is_active = models.BooleanField(default=False, help_text="Only one connection can be active at a time")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.phone_number_id})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_active:
            WhatsAppConfig.objects.exclude(pk=self.pk).update(is_active=False)

    @staticmethod
    def mask(value):
        if not value:
            return ""
        if len(value) <= 10:
            return "••••"
        return f"{value[:6]}••••{value[-4:]}"

    @property
    def masked_access_token(self):
        return self.mask(self.access_token)

    @property
    def masked_app_secret(self):
        return self.mask(self.app_secret)


class WhatsAppMessage(models.Model):
    template_name = models.CharField(max_length=100, blank=True)
    reference_type = models.CharField(max_length=50, blank=True)
    reference_id = models.CharField(max_length=100, blank=True)
    to_number = models.CharField(max_length=20)
    wa_message_id = models.CharField(max_length=200, unique=True, null=True, blank=True)
    status = models.CharField(max_length=20, default="accepted")
    error = models.TextField(blank=True)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["reference_type", "reference_id"])]

    def __str__(self):
        return f"{self.reference_type} {self.reference_id} to {self.to_number} ({self.status})"

    @property
    def pretty_payload(self):
        return json.dumps(self.payload, indent=2, ensure_ascii=False)


class WebhookEvent(models.Model):
    payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at"]

    @property
    def summary(self):
        parts = []
        for entry in self.payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for status in value.get("statuses", []):
                    parts.append(f"{status.get('status')} to {status.get('recipient_id')}")
                for message in value.get("messages", []):
                    parts.append(f"reply from {message.get('from')}")
        return ", ".join(parts) or "Other event"

    @property
    def pretty_payload(self):
        return json.dumps(self.payload, indent=2, ensure_ascii=False)
