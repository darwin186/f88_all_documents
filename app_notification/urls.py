from django.urls import path

from . import views

app_name = "app_notification"

urlpatterns = [
    path("", views.notification_dashboard, name="notification_dashboard"),
    path(
        "subscriptions/<int:pk>/toggle/",
        views.subscription_toggle,
        name="notification_subscription_toggle",
    ),
    path("api/trigger/", views.notification_trigger, name="notification_trigger"),
]
