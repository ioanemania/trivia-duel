from rest_framework import serializers

from .models import Lobby


class LobbySerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)

    class Meta:
        model = Lobby

    def create(self, validated_data):
        lobby = self.Meta.model(name=validated_data['name'])
        lobby.save()
        return lobby
