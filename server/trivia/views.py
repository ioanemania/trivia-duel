from rest_framework.viewsets import ViewSet
from rest_framework.decorators import action
from rest_framework import status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from redis_om.model.model import NotFoundError

from .serializers import LobbySerializer
from .models import Lobby
from .utils import generate_lobby_token_and_data, parse_boolean_string


class LobbyViewSet(ViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = LobbySerializer

    def create(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        lobby = serializer.Meta.model(**serializer.validated_data)
        token, data = generate_lobby_token_and_data(request.user)

        lobby.users[token] = data
        lobby.save()

        return Response(data={"token": token}, status=status.HTTP_201_CREATED)

    def list(self, request):
        is_ranked_param = request.query_params.get("ranked", "")

        try:
            is_ranked_filter = parse_boolean_string(is_ranked_param)
        except ValueError:
            is_ranked_filter = None

        if is_ranked_filter is not None:
            lobbies = Lobby.find(Lobby.ranked == int(is_ranked_filter)).all()
        else:
            lobbies = Lobby.find().all()

        serializer = self.serializer_class(instance=lobbies, many=True)

        return Response(data=serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def join(self, request, pk=None):
        try:
            lobby = Lobby.get(pk)
        except NotFoundError:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if len(lobby.users) > 1:
            return Response(data={"detail": "Lobby is full"}, status=status.HTTP_400_BAD_REQUEST)

        if request.user.id in (user["user_id"] for user in lobby.users.values()):
            return Response(
                data={"detail": "Already joined the lobby"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        token, data = generate_lobby_token_and_data(request.user)

        lobby.users[token] = data
        lobby.save()

        return Response(data={"token": token}, status=status.HTTP_200_OK)
