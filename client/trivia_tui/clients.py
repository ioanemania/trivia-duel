from asyncio import Task

import jwt
import websockets
from requests import Response
from typing import Optional, Any

import requests
from requests.auth import AuthBase

from trivia_tui.exceptions import RefreshTokenExpiredError, ResponseError
from trivia_tui.types import TrainingQuestionData


class TokenAuth(AuthBase):
    def __init__(self, token: str, auth_scheme="Bearer"):
        self.token = token
        self.auth_scheme = auth_scheme

    def __call__(self, request):
        request.headers["Authorization"] = f"{self.auth_scheme} {self.token}"
        return request


class TriviaClient:
    """Class that handles communication with a Trivia Duel Server"""

    def __init__(self, base_url: str):
        self.base_url = base_url[:-1] if base_url.endswith("/") else base_url
        self.api_base_url = "http://" + self.base_url
        self.ws_base_url = "ws://" + self.base_url

        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None

    def _make_request(
        self, method: str, url: str, authenticated: bool = True, *args, **kwargs
    ) -> ResponseError | Response:
        if authenticated and not self.access_token:
            raise Exception("Trying to make an authenticated request without being authenticated")

        if authenticated:
            self._check_expiration_and_refresh_access_token()
            auth = TokenAuth(self.access_token)
        else:
            auth = None

        try:
            response = requests.request(method=method, url=url, auth=auth, *args, **kwargs)
            response.raise_for_status()
        except requests.exceptions.ConnectionError:
            raise ResponseError({"detail": "Unable to connect to the server"})
        except requests.exceptions.HTTPError as e:
            raise ResponseError(e.response.json())

        return response

    def _check_expiration_and_refresh_access_token(self):
        """Check if the access token has expired and if so, re-obtain it using the refresh token"""
        headers = jwt.get_unverified_header(self.access_token)
        try:
            jwt.decode(
                self.access_token, algorithms=[headers["alg"]], options={"verify_signature": False, "verify_exp": True}
            )
        except jwt.exceptions.ExpiredSignatureError:
            url = self.api_base_url + "/api/token/refresh/"
            access_token_response = requests.post(url, json={"refresh": self.refresh_token})

            if access_token_response.status_code == 401:
                raise RefreshTokenExpiredError("Refresh token has expired")

            self.access_token = access_token_response.json()["access"]

    def register(self, username: str, password: str) -> None:
        url = self.api_base_url + "/api/user/register/"
        self._make_request(
            "POST",
            url=url,
            authenticated=False,
            json={"username": username, "password": password},
        )

    def login(self, username: str, password: str) -> None:
        url = self.api_base_url + "/api/token/"

        data = self._make_request(
            "POST",
            url=url,
            authenticated=False,
            json={"username": username, "password": password},
        ).json()
        self.access_token, self.refresh_token = data["access"], data["refresh"]

    def get_lobbies(self, ranked: Optional[bool] = None) -> list:
        url_components = (self.api_base_url, "/api/trivia/lobbies/")

        if ranked is not None:
            url_components += f"?ranked=", str(ranked)
        url = "".join(url_components)

        return self._make_request("GET", url=url).json()

    def create_lobby(self, lobby_name: str, ranked: bool) -> dict:
        url = self.api_base_url + "/api/trivia/lobbies/"

        return self._make_request("POST", url=url, json={"name": lobby_name, "ranked": ranked}).json()

    def join_lobby(self, lobby_name: str) -> dict:
        url = self.api_base_url + f"/api/trivia/lobbies/{lobby_name}/join/"

        return self._make_request("POST", url=url).json()

    def get_rankings(self) -> list[dict]:
        url = self.api_base_url + "/api/user/ranking/"

        return self._make_request("GET", url=url).json()

    def get_training_questions(self) -> list[TrainingQuestionData]:
        url = self.api_base_url + "/api/trivia/train/"

        return self._make_request("GET", url=url).json()

    def post_training_result(self) -> None:
        url = self.api_base_url + "/api/trivia/train/"

        self._make_request("POST", url=url)

    def get_user_games(self) -> list[dict]:
        url = self.api_base_url + "/api/trivia/history"

        return self._make_request("GET", url=url).json()

    def ws_join_lobby(self, lobby_name: str, token: str) -> Task[websockets.WebSocketClientProtocol]:
        url = self.ws_base_url + f"/ws/trivia/lobbies/{lobby_name}?{token}"

        return websockets.connect(url)
