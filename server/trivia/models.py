from typing import List

from redis_om import HashModel, JsonModel, Field, Migrator, get_redis_connection


class Lobby(JsonModel):
    name: str = Field(primary_key=True)
    users: List[str] = []


Migrator().run()
