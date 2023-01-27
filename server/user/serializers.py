from rest_framework import serializers

from .models import User


class UserRegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["username", "password"]
        extra_kwargs = {
            "password": {"write_only": True}
        }

    def create(self, validated_data):
        username = validated_data["username"]
        password = validated_data["password"]

        user = User.objects.create_user(username=username, password=password)
        user.save()

        return user
