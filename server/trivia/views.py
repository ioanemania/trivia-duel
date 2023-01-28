import secrets

from rest_framework.viewsets import ViewSet
from rest_framework.decorators import action
from rest_framework import status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from redis_om.model.model import NotFoundError

from .serializers import LobbySerializer
from .models import Lobby


class LobbyViewSet(ViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = LobbySerializer

    def create(self, request):
        """Create a new lobby"""

        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(data=serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def join(self, request, pk=None):
        try:
            lobby = Lobby.get(pk)
        except NotFoundError:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if len(lobby.tokens) > 1:
            return Response(data={"detail": "Lobby is full"}, status=status.HTTP_400_BAD_REQUEST)

        if request.user.id in (token_tuple[1] for token_tuple in lobby.tokens):
            return Response(data={"detail": "Already joined the lobby"}, status=status.HTTP_400_BAD_REQUEST)

        token = secrets.token_urlsafe(16)
        lobby.tokens.append((token, request.user.id))
        lobby.save()

        return Response(data={"token": token}, status=status.HTTP_200_OK)
