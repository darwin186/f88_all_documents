from django.urls import path

from . import views

app_name = "gapo_relay"

urlpatterns = [
    path("health/", views.health, name="health"),
    path("webhook/<str:secret>/", views.ingress, name="ingress"),
    path("deliveries/claim/", views.claim, name="claim"),
    path("deliveries/ack/", views.ack, name="ack"),
    path("deliveries/nack/", views.nack, name="nack"),
]
