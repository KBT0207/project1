from django.forms import ModelForm
from .models import WhatsAppConfig


class WhatsAppConfigForm(ModelForm):
    class Meta:
        model = WhatsAppConfig
        fields = "__all__"