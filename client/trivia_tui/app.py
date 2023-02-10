from typing import Optional

from textual import events
from textual.app import App

from .screens import LoginOrRegisterScreen
from .clients import TriviaClient

TRIVIA_SERVER_URL = "localhost:8000/"


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

    def on_mount(self) -> None:
        self.push_screen(LoginOrRegisterScreen())

    def on_key(self, event: events.Key):
        if event.key == "escape" and len(self.screen_stack) > 2:
            screen = self.screen
            self.install_screen(screen)
            self.pop_screen()
            self.uninstall_screen(screen)
