from typing import List, Tuple

from redis_om import JsonModel, Field, Migrator


UserId = int
Token = str
TokenTuple = Tuple[Token, UserId]


class Lobby(JsonModel):
    name: str = Field(primary_key=True)
    user_count: int = 0
    tokens: List[TokenTuple] = []


Migrator().run()
