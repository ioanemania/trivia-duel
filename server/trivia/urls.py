from django.urls import path
from rest_framework.routers import DefaultRouter

from . import consumers, views

router = DefaultRouter()
router.register("lobbies", views.LobbyViewSet, basename="lobby")

urlpatterns = router.urls

websocket_urlpatterns = [path("lobbies/<slug:lobby_name>", consumers.GameConsumer.as_asgi())]
