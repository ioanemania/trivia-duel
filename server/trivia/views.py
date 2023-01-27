from rest_framework.views import APIView
from rest_framework import status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .serializers import LobbySerializer


class LobbyView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LobbySerializer

    def post(self, request):
        """Create a new lobby"""

        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(data=serializer.data, status=status.HTTP_201_CREATED)
