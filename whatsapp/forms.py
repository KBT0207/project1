from .models import WhatsAppConfig
from django import forms
from django.contrib.auth.forms import AuthenticationForm



class WhatsAppConfigForm(forms.ModelForm):
    class Meta:
        model = WhatsAppConfig
        fields = "__all__"


