from typing import Optional

from textual import events
from textual.app import App
from textual.screen import Screen

from .clients import TriviaClient
from .screens import LoginOrRegisterScreen

TRIVIA_SERVER_URL = "app:8000"


class BaseApp(App):
    async def fixed_pop_screen(self) -> Screen:
        """
        Installs, Pops and Uninstalls the screen.
        Without installing the screen first, popping does not work as intended.
        """

        screen = self.screen
        await self.install_screen(screen)
        self.pop_screen()
        self.uninstall_screen(screen)
        return screen

    async def fixed_switch_screen(self, screen: Screen | str):
        """
        Installs, Switches and Uninstalls the screen.
        Without installing the screen first, switching does not work as intended.
        """

        old_screen = self.screen
        await self.install_screen(old_screen)
        await self.switch_screen(screen)
        self.uninstall_screen(old_screen)


class TriviaApp(BaseApp):
    """
    The Trivia Duel App

    Allows the user to interact with a Trivia Duel Server, play multiplayer trivia games,
    play training games, view leaderboards and game history.
    """

    CSS_PATH = "css/main.css"

    def __init__(self, trivia_server_url: str, *args, **kwargs):
        self.client = TriviaClient(trivia_server_url)
        self.username: Optional[str] = None

        super().__init__(*args, **kwargs)

    async def on_mount(self) -> None:
        await self.fixed_switch_screen(LoginOrRegisterScreen())

    async def on_key(self, event: events.Key):
        if event.key == "escape":
            if len(self.screen_stack) == 1:
                self.exit()
                return

            await self.fixed_pop_screen()

    async def on_back_button_pressed(self):
        await self.fixed_pop_screen()
