import asyncio
import websockets
# import websockets
#
#
# async def hello():
#     async with websockets.connect("ws://localhost/ws/trivia/echo/", port=8000) as websocket:
#         await websocket.send("Hello, World")
#         print(await websocket.recv())
#
#
# asyncio.run(hello())

from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.containers import Grid
from textual.widgets import Header, Footer, Button, Static, Input


class MainMenuScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Button("Send Message", id="btn-send-message")
        yield Button("Play", id="btn-play")
        yield Button("Leaderboards")
        yield Button("History")


class PlayMenuScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Button("Ranked")
        yield Button("Casual")
        yield Button("Training")


class SendMessageScreen(Screen):
    def compose(self):
        yield Input("Message: ", id="msg")
        yield Button("Send")

    async def on_button_pressed(self, _event: Button.Pressed) -> None:
        message = self.query_one("#msg", Input).value
        async with websockets.connect("ws://localhost/ws/trivia/echo/", port=8000) as websocket:
            await websocket.send(message)


class TriviaApp(App):
    """A Textual app to manage stopwatches."""
    SCREENS = {
        "main_menu": MainMenuScreen(),
        "play_menu": PlayMenuScreen(),
        "send_message_menu": SendMessageScreen(),
    }

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-send-message":
            self.push_screen("send_message_menu")
        elif event.button.id == "btn-play":
            self.push_screen("play_menu")

    def on_mount(self) -> None:
        self.push_screen("main_menu")


if __name__ == "__main__":
    app = TriviaApp()
    app.run()
