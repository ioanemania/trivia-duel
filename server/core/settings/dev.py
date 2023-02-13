# flake8: noqa

from .base import *

# Database
# https://docs.djangoproject.com/en/4.1/ref/settings/#databases

POSTGRES_HOST = os.environ["POSTGRES_HOST"]
POSTGRES_USER = os.environ["POSTGRES_USER"]
POSTGRES_PASSWORD = os.environ["POSTGRES_PASSWORD"]
POSTGRES_DB = os.environ["POSTGRES_DB"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": POSTGRES_DB,
        "USER": POSTGRES_USER,
        "PASSWORD": POSTGRES_PASSWORD,
        "HOST": POSTGRES_HOST,
    }
}


# CHANNELS
REDIS_CHANNEL_LAYER_URL = os.environ["REDIS_CHANNEL_LAYER_URL"]

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_CHANNEL_LAYER_URL]},
    }
}
