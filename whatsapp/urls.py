from django.urls import path

from .views import dashboard, whatsapp_webhook, whatsapp_config, whatsapp_config_edit, whatsapp_config_delete

urlpatterns = [
    path("webhook/whatsapp/", whatsapp_webhook, name="whatsapp_webhook"),
    path("whatsapp/dashboard/", dashboard, name="whatsapp_dashboard"),
    path("whatsapp/whatsapp_config/", whatsapp_config, name="whatsapp_config"),
    path("whatsapp/whatsapp_config_edit/<int:pk>", whatsapp_config_edit, name="whatsapp_config_edit"),
    path("whatsapp/whatsapp_config_delete/<int:pk>", whatsapp_config_delete, name="whatsapp_config_delete"),
]
