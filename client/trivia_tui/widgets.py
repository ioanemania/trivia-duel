import random

from typing import Optional, TypedDict, Iterable, Generator

from textual.app import ComposeResult, RenderableType
from textual.widgets import Static, Button, DataTable
from textual.reactive import reactive
from textual.timer import Timer

from .messages import QuestionAnswered, CountdownFinished, FiftyFiftyTriggered


class Question(Static):
    def __init__(
        self,
        question: str,
        incorrect_answers: list[str],
        correct_answer: str,
        difficulty: str,
        category: str,
        type: str,
        max_time: int = 30,
        *args,
        **kwargs,
    ):
        self.question = question
        self.difficulty = difficulty
        self.incorrect_answers = incorrect_answers
        self.correct_answer = correct_answer
        self.category = category
        self.type = type
        self.question_answered = False
        self.max_time = max_time

        super().__init__(*args, **kwargs)

    def compose(self) -> ComposeResult:
        if self.max_time:
            yield Countdown(self.max_time)
        yield Static(self.question)
        for answer in self.incorrect_answers:
            yield Button(answer)
        yield Button(self.correct_answer)

    async def on_button_pressed(self, event: Button.Pressed):
        event.prevent_default()
        self.disable_answers()
        correctly = str(event.button.label) == self.correct_answer
        self.question_answered = True

        if correctly:
            event.button.variant = "success"
        else:
            event.button.variant = "error"
            self.highlight_correct_answer()

        await self.emit(QuestionAnswered(self, correctly, self.difficulty))

    async def on_countdown_finished(self):
        if not self.question_answered:
            self.disable_answers()
            await self.emit(QuestionAnswered(self, False, self.difficulty))

    async def on_fifty_fifty_triggered(self, _event: FiftyFiftyTriggered):
        if self.type == "boolean":
            return

        random_incorrect_answers = random.sample(self.incorrect_answers, k=2)
        for answer_button in self.query(Button):
            if str(answer_button.label) in random_incorrect_answers:
                answer_button.disabled = True

    def disable_answers(self) -> None:
        for button in self.query(Button):
            button.disabled = True

    def highlight_correct_answer(self):
        for button in self.query(Button):
            if str(button.label) == self.correct_answer:
                button.variant = "success"
                break


class Countdown(Static):
    seconds = reactive(0)

    def __init__(self, duration: int):
        self.duration = duration
        self.timer: Optional[Timer] = None

        super().__init__()

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
    def __init__(self, status: str, *args, **kwargs):
        self.status = status

        super().__init__(*args, **kwargs)

    def compose(self) -> ComposeResult:
        yield Static(self.status)


class GameHistoryTable(DataTable):
    def __init__(self, data: list[dict]):
        self.game_data = data
        print("I WAS FIRST")
        super().__init__()

    def on_mount(self):
        self.add_columns(*self.flattened_columns())
        self.add_rows((self.flattened_row(row) for row in self.game_data))

    def flattened_columns(self):
        print("HELLO!!!", self.game_data)
        for key in self.game_data[0].keys():
            if key == "game":
                yield from self.game_data[0][key].keys()
            else:
                yield key

    def flattened_row(self, row):
        for key, value in row.items():
            if key == "game":
                yield from (str(value) for value in row[key].values())
            else:
                yield str(value)
