from django import forms
from django.contrib import admin, messages

from .models import WebhookEvent, WhatsAppConfig, WhatsAppMessage


class WhatsAppConfigForm(forms.ModelForm):
    class Meta:
        model = WhatsAppConfig
        fields = "__all__"
        widgets = {
            "access_token": forms.PasswordInput(render_value=True),
            "app_secret": forms.PasswordInput(render_value=True),
        }


@admin.register(WhatsAppConfig)
class WhatsAppConfigAdmin(admin.ModelAdmin):
    form = WhatsAppConfigForm
    list_display = ("name", "phone_number_id", "default_template", "is_active", "updated_at")
    actions = ["make_active"]

    @admin.action(description="Make the selected connection active")
    def make_active(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Select exactly one connection.", level=messages.ERROR)
            return
        config = queryset.first()
        config.is_active = True
        config.save()
        self.message_user(request, f"{config.name} is now the active connection.")


@admin.register(WhatsAppMessage)
class WhatsAppMessageAdmin(admin.ModelAdmin):
    list_display = ("created_at", "to_number", "template_name", "reference_type", "reference_id", "status")
    list_filter = ("status", "template_name", "reference_type")
    search_fields = ("to_number", "reference_id", "wa_message_id")


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("received_at", "summary")
