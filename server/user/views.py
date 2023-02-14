from rest_framework.generics import CreateAPIView, ListAPIView

from . import serializers
from .models import User


class UserRegisterView(CreateAPIView):
    """
    Simple registration view without any additional verification steps.
    Creates an account in the system with the given username and password.
    """

    serializer_class = serializers.UserRegisterSerializer


class UserRankingView(ListAPIView):
    """Lists users by their rank in descending order"""

    serializer_class = serializers.UserRankSerializer
    queryset = User.objects.all().order_by("-rank")
