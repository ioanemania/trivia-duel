import itertools
import random
from typing import Optional

from rich.text import TextType
from textual.app import ComposeResult, RenderableType
from textual.reactive import reactive
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Button, DataTable, Static

from .messages import (
    BackButtonPressed,
    CountdownFinished,
    FiftyFiftyTriggered,
    GameTimedOut,
    QuestionAnswered,
    TrainingQuestionAnswered,
)
from .types import QuestionData, TrainingQuestionData
from .utils import convert_difficulty_to_stars


class Question(Static):
    """
    A multiplayer trivia question widget.

    The widget consists of the question, buttons for all possible answers and a countdown.

    The answer buttons emit a QuestionAnswered event whenever one of them is pressed.
    """

    def __init__(self, question_data: QuestionData, *args, **kwargs):
        self.question_data = question_data
        self.chosen_answer: Optional[Button] = None
        self.question_answered: bool = False
        super().__init__(*args, **kwargs)

    def compose(self) -> ComposeResult:
        yield Countdown(int(self.question_data["duration"]))
        yield Static(convert_difficulty_to_stars(self.question_data["difficulty"]))
        yield Static(self.question_data["question"])

        for answer in self.question_data["answers"]:
            yield Button(answer)

    async def on_countdown_finished(self):
        if not self.question_answered:
            self.disable_answers()
            await self.emit(QuestionAnswered(self, ""))

    async def on_button_pressed(self, event: Button.Pressed):
        event.prevent_default()
        self.question_answered = True
        self.disable_answers()
        self.chosen_answer = event.button
        await self.emit(QuestionAnswered(self, str(event.button.label)))

    async def on_fifty_fifty_triggered(self, event: FiftyFiftyTriggered):
        for answer_button in self.query(Button):
            if str(answer_button.label) in event.incorrect_answers:
                answer_button.disabled = True

    def highlight_answers(self, correct_answer: str, correctly: bool) -> None:
        for answer in self.query(Button):
            if str(answer.label) == correct_answer:
                answer.variant = "success"
                break

        if not correctly and self.chosen_answer:
            self.chosen_answer.variant = "error"

    def disable_answers(self) -> None:
        for button in self.query(Button):
            button.disabled = True


class TrainingQuestion(Static):
    """
    A training question widget.

    Consist of the question and buttons for all answers.

    The answer buttons emit TrainingQuestionAnswered event whenever one of them is pressed.
    """

    def __init__(self, question_data: TrainingQuestionData, *args, **kwargs):
        self.question_data = question_data

        super().__init__(*args, **kwargs)

    def compose(self) -> ComposeResult:
        yield Static(convert_difficulty_to_stars(self.question_data["difficulty"]))
        yield Static(self.question_data["question"])

        if self.question_data["type"] == "boolean":
            yield Button("True")
            yield Button("False")
        else:
            all_answers = tuple(
                itertools.chain(self.question_data["incorrect_answers"], (self.question_data["correct_answer"],))
            )
            for answer in random.sample(all_answers, k=len(all_answers)):
                yield Button(answer)

    async def on_button_pressed(self, event: Button.Pressed):
        event.prevent_default()
        self.disable_answers()
        correctly = str(event.button.label) == self.question_data["correct_answer"]

        if correctly:
            event.button.variant = "success"
        else:
            event.button.variant = "error"
            self.highlight_correct_answer()

        await self.emit(TrainingQuestionAnswered(self, correctly, self.question_data["difficulty"]))

    def disable_answers(self) -> None:
        for button in self.query(Button):
            button.disabled = True

    def highlight_correct_answer(self):
        for button in self.query(Button):
            if str(button.label) == self.question_data["correct_answer"]:
                button.variant = "success"
                break


class Countdown(Static):
    """
    A countdown widget.

    Counts down from a starting number and emits a CountdownFinished event
    when the number reaches 0.
    """

    seconds = reactive(0)

    def __init__(self, duration: int, *args, **kwargs):
        self.duration = duration
        self.timer: Optional[Timer] = None

        super().__init__(*args, **kwargs)

    def render(self) -> RenderableType:
        return f"{self.seconds}"

    def on_mount(self):
        self.seconds = self.duration
        self.timer = self.set_interval(1, self.update_timer)

    async def update_timer(self) -> None:
        self.seconds -= 1
        if self.seconds == 0:
            await self.timer.stop()
            await self.emit(CountdownFinished(self))


class GameStatus(Static):
    """Game status widget, used to display the results of a multiplayer game."""

    def __init__(self, status: str, *args, **kwargs):
        self.status = status

        super().__init__(*args, **kwargs)

    def compose(self) -> ComposeResult:
        if self.status == "win":
            yield Static("You won the game!")
        elif self.status == "loss":
            yield Static("You lost the game!")
        elif self.status == "draw":
            yield Static("The game was a draw!")


class GameHistoryTable(DataTable):
    """Table that displays a history of previously played games."""

    def __init__(self, data: list[dict]):
        self.game_data = data
        super().__init__()

    async def on_mount(self):
        self.add_columns(*self.flattened_columns())
        self.add_rows((self.flattened_row(row) for row in self.game_data))

    def flattened_columns(self):
        for key in self.game_data[0].keys():
            if key == "game":
                yield from self.game_data[0][key].keys()
            else:
                yield key

    def flattened_row(self, row):  # noqa
        for key, value in row.items():
            if key == "game":
                yield from (str(value) for value in row[key].values())
            else:
                yield str(value)


class GameHeader(Widget):
    """
    A header widget that displays information about an ongoing game.

    Consists of the usernames and health points of both players and the game time countdown.
    """

    def __init__(self, player_name: str, opponent_name: str, duration: int, *children: Widget, **kwargs):
        super().__init__(*children, **kwargs)
        self.player_name = player_name
        self.opponent_name = opponent_name
        self.duration = duration

    def compose(self) -> ComposeResult:
        yield PlayerHeaderSection(player_name=self.player_name, id="section-player")
        yield Countdown(self.duration, id="countdown")
        yield PlayerHeaderSection(player_name=self.opponent_name, reverse=True, id="section-opponent")

    def decrease_player_hp(self, value: int):
        player_header_section = self.query_one("#section-player", PlayerHeaderSection)
        player_header_section.hp = max(player_header_section.hp - value, 0)

    def decrease_opponent_hp(self, value):
        opponent_header_section = self.query_one("#section-opponent", PlayerHeaderSection)
        opponent_header_section.hp = max(opponent_header_section.hp - value, 0)

    async def on_countdown_finished(self):
        await self.emit(GameTimedOut(self))


class PlayerHeaderSection(Static):
    """Widget that that displays the username and health points of a user"""

    def __init__(self, player_name: str, reverse: bool = False, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.player_name = player_name
        self.reverse = reverse

    hp = reactive(100)

    def render(self) -> RenderableType:
        if self.reverse:
            return f"{self.hp} {self.player_name}"

        return f"{self.player_name} {self.hp}"


class BackButton(Static):
    """
    A custom button used to go back to a previous screen.

    Emits a BackButtonPressed event whenever it is pressed.
    """

    def __init__(self, label: TextType, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.label = label

    def compose(self) -> ComposeResult:
        yield Button(self.label)

    async def on_button_pressed(self, event: Button.Pressed):
        event.prevent_default()
        await self.emit(BackButtonPressed(self))


class ConfirmLeaveModal(Static):
    """
    A widget used to display a confirmation modal,
    used to confirm when a user wants to leave a multiplayer game
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def compose(self) -> ComposeResult:
        yield Static("Are you sure you want to leave the game?")
        yield Static("Game will count as a loss")
        yield Button("Yes", id="confirm-accept")
        yield Button("No", id="confirm-reject")
