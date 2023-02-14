from django.conf import settings
from redis_om.model.model import NotFoundError
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

from .models import Game, Lobby, UserGame
from .serializers import LobbySerializer, UserGameSerializer
from .types import GameStatus, GameType
from .utils import TriviaAPIClient, generate_lobby_token, parse_boolean_string


class LobbyViewSet(ViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = LobbySerializer

    def create(self, request):
        """
        Creates a new lobby, and returns a lobby authentication token to the user

        Lobbies are created with an expiration time. This prevents cases of unused
        lobbies when users create lobbies but fail to join them afterwards.

        The lobbies are expected to be persisted after a user connects to the
        lobby's associated websocket for the first time.
        """
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        lobby = serializer.Meta.model(**serializer.validated_data)
        lobby.save()

        token = generate_lobby_token(request.user)

        lobby.db().expire(lobby.key(), settings.LOBBY_EXPIRE_SECONDS)

        return Response(data={"token": token}, status=status.HTTP_201_CREATED)

    def list(self, request):
        """
        List all available lobbies

        Accepts an additional query parameter "ranked" which can be either True
        or False, and filters out only ranked or normal games respectively.
        """

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
        """
        Generates a lobby authentication token, which can be used to join a lobby.

        The token is not really bound to a specific lobby, it can be used to join any
        lobby. Validation in this view is used to provide information to the user, actual
        validation happens when the user tries to connect to the lobby's websocket connection.
        """
        try:
            lobby = Lobby.get(pk)
        except NotFoundError:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if len(lobby.users) > 1:
            return Response(data={"detail": "Lobby is full"}, status=status.HTTP_400_BAD_REQUEST)

        if request.user.id in lobby.users.keys():
            return Response(
                data={"detail": "Already joined the lobby"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        token = generate_lobby_token(request.user)

        return Response(data={"token": token}, status=status.HTTP_200_OK)


class TrainingView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Gives questions to the client for training"""

        questions = TriviaAPIClient.get_questions()

        return Response(data=questions)

    def post(self, request):
        """Saves a record of a training."""

        game = Game(type=GameType.TRAINING)
        game.save()

        user_game = UserGame(user=request.user, game=game, status=GameStatus.WIN, rank=request.user.rank)
        user_game.save()

        return Response(status=status.HTTP_201_CREATED)


class HistoryView(ListAPIView):
    """Returns a list of all games that a user has previously played"""

    permission_classes = [IsAuthenticated]
    serializer_class = UserGameSerializer

    def get_queryset(self):
        return self.request.user.user_games.select_related("opponent", "game").order_by("-game__timestamp").all()
