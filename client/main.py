from argparse import ArgumentParser
from pathlib import Path

from trivia_tui.app import TRIVIA_SERVER_URL, TriviaApp

if __name__ == "__main__":
    parser = ArgumentParser(prog=Path(__file__).name, description="Duel other players in multiplayer trivia games!")
    parser.add_argument(
        "server_location",
        default=TRIVIA_SERVER_URL,
        nargs="?",
        help=f"hostname and port of the server (default: {TRIVIA_SERVER_URL})",
    )
    args = parser.parse_args()

    app = TriviaApp(args.server_location)
    app.run()
