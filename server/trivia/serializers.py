from rest_framework import serializers

from .models import Lobby


class LobbySerializer(serializers.Serializer):
    name = serializers.SlugField(max_length=100)
    ranked = serializers.BooleanField(default=False)

    class Meta:
        model = Lobby

    def validate_name(self, value: str):
        if any(Lobby.find(Lobby.name == value).all()):
            raise serializers.ValidationError("Lobby with the given name already exists")
        return value
