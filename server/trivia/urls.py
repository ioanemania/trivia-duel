from django.urls import path

from . import consumers, views

urlpatterns = [
    path("lobbies/", views.LobbyView.as_view()),
]

websocket_urlpatterns = [
    path("lobbies/<slug:lobby_name>", consumers.GameConsumer.as_asgi())
]
