from django.urls import path

from .views import (
    busy_send,
    dashboard,
    login,
    logout,
    whatsapp_config,
    whatsapp_config_delete,
    whatsapp_config_edit,
    whatsapp_webhook,
)

urlpatterns = [
    path("login/", login, name="login"),
    path("logout/", logout, name="logout"),
    path("webhook/whatsapp/", whatsapp_webhook, name="whatsapp_webhook"),
    path("api/busy/send/", busy_send, name="busy_send"),
    path("whatsapp/dashboard/", dashboard, name="whatsapp_dashboard"),
    path("whatsapp/whatsapp_config/", whatsapp_config, name="whatsapp_config"),
    path("whatsapp/whatsapp_config_edit/<int:pk>", whatsapp_config_edit, name="whatsapp_config_edit"),
    path("whatsapp/whatsapp_config_delete/<int:pk>", whatsapp_config_delete, name="whatsapp_config_delete"),
]