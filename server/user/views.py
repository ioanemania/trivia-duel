from rest_framework.generics import CreateAPIView

from . import serializers


class UserRegisterView(CreateAPIView):
    serializer_class = serializers.UserRegisterSerializer
