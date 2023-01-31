from textual import events
from textual.app import App

from .screens import LoginOrRegisterScreen


class TriviaApp(App):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.access_token: str | None = None

    def on_mount(self) -> None:
        self.push_screen(LoginOrRegisterScreen())

    def on_key(self, event: events.Key):
        if event.key == "escape" and len(self.screen_stack) > 3:
            self.pop_screen()
