from django.urls import path

from .views import dashboard, whatsapp_webhook

urlpatterns = [
    path("webhook/whatsapp/", whatsapp_webhook, name="whatsapp_webhook"),
    path("whatsapp/dashboard/", dashboard, name="whatsapp_dashboard"),
]
