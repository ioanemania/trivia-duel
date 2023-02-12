from textual.screen import Screen
from textual.widget import AwaitMount
from typing import Optional

from textual import events
from textual.app import App

from .messages import BackButtonPressed
from .screens import LoginOrRegisterScreen
from .clients import TriviaClient

TRIVIA_SERVER_URL = "localhost:8000"


class TriviaApp(App):
    DEFAULT_CSS = """
     Screen {
        height: 100%;
        margin: 4 8;
        padding: 1 2;
        align: center middle;
    }

    Static {
        content-align: center middle;
    }
    """

    def __init__(self, *args, **kwargs):
        self.client = TriviaClient(TRIVIA_SERVER_URL)
        self.username: Optional[str] = None

        super().__init__(*args, **kwargs)

    async def on_mount(self) -> None:
        await self.push_screen(LoginOrRegisterScreen())

    async def on_key(self, event: events.Key):
        if event.key == "escape" and len(self.screen_stack) > 2:
            await self.fixed_pop_screen()

    async def on_back_button_pressed(self):
        await self.fixed_pop_screen()

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

    async def fixed_switch_screen(self, screen: Screen | str) -> AwaitMount:
        """
        Installs, Switches and Uninstalls the screen.
        Without installing the screen first, switching does not work as intended.
        """

        old_screen = self.screen
        await self.install_screen(old_screen)
        await self.switch_screen(screen)
        self.uninstall_screen(old_screen)
