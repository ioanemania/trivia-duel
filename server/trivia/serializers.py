from rest_framework import serializers

from .models import Game, Lobby, UserGame
from .types import GameStatus, GameType


class LobbySerializer(serializers.Serializer):
    name = serializers.SlugField(max_length=100)
    ranked = serializers.BooleanField(default=False)

    class Meta:
        model = Lobby


class GameSerializer(serializers.ModelSerializer):
    class Meta:
        model = Game
        fields = ["type", "timestamp"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["type"] = GameType(data["type"]).name.lower()
        return data


class UserGameSerializer(serializers.ModelSerializer):
    opponent = serializers.SlugRelatedField(slug_field="username", read_only=True)
    game = GameSerializer(read_only=True)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["status"] = GameStatus(data["status"]).name.lower()
        return data

    class Meta:
        model = UserGame
        exclude = ("id", "user", "extra_data")
