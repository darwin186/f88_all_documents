from django import forms

from .models import NotificationChannel, NotificationReport, NotificationSubscription


class NotificationSubscriptionForm(forms.ModelForm):
    class Meta:
        model = NotificationSubscription
        fields = ["report", "channel", "target", "is_active"]
        widgets = {
            "report": forms.Select(attrs={"class": "select"}),
            "channel": forms.Select(attrs={"class": "select"}),
            "target": forms.TextInput(attrs={"class": "input", "placeholder": "Gapo user ID / email / webhook"}),
            "is_active": forms.CheckboxInput(attrs={"class": ""}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.fields["report"].queryset = NotificationReport.objects.filter(is_active=True).order_by("name")
        self.fields["channel"].choices = NotificationChannel.choices

    def save(self, commit=True):
        if not self.user:
            raise ValueError("user is required to save subscription")
        instance = super().save(commit=False)
        instance.user = self.user
        if commit:
            instance.save()
        return instance
