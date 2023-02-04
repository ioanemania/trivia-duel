from django.urls import path
from rest_framework.routers import DefaultRouter

from . import consumers, views

router = DefaultRouter()
router.register("lobbies", views.LobbyViewSet, basename="lobby")

urlpatterns = [path("train/", views.TrainingView.as_view(), name="train")] + router.urls

websocket_urlpatterns = [path("lobbies/<slug:lobby_name>", consumers.GameConsumer.as_asgi())]
