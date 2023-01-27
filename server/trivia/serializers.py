from rest_framework import serializers

from .models import Lobby


class LobbySerializer(serializers.Serializer):
    lobby_name = serializers.CharField(max_length=100)

    class Meta:
        model = Lobby

    def create(self, validated_data):
        self.Meta.model(lobby_name=validated_data['lobby_name']).save()
