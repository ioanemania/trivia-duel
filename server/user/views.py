from rest_framework.generics import CreateAPIView, ListAPIView

from . import serializers
from .models import User


class UserRegisterView(CreateAPIView):
    serializer_class = serializers.UserRegisterSerializer


class UserRankingView(ListAPIView):
    """Lists users by their rank in descending order"""

    serializer_class = serializers.UserRankSerializer
    queryset = User.objects.all().order_by("-rank")
