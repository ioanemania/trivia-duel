from django.contrib.auth.models import AbstractUser
from django.db import models

USER_STARTING_RANK = 1000


class User(AbstractUser):
    rank = models.PositiveIntegerField(default=USER_STARTING_RANK)
