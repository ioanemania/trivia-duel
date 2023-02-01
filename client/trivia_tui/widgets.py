from typing import Optional

from textual.app import ComposeResult, RenderableType
from textual.widgets import Static, Button
from textual.reactive import reactive
from textual.timer import Timer

from .messages import QuestionAnswered, CountdownFinished


class Question(Static):
    def __init__(
        self,
        question: str,
        incorrect_answers: list[str],
        correct_answer: str,
        difficulty: str,
        category: str,
        type: str,
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

        super().__init__(*args, **kwargs)

    def compose(self) -> ComposeResult:
        yield Countdown(30)
        yield Static(self.question)
        for answer in self.incorrect_answers:
            yield Button(answer)
        yield Button(self.correct_answer)

    async def on_button_pressed(self, event: Button.Pressed):
        self.disable_answers()
        correctly = str(event.button.label) == self.correct_answer
        self.question_answered = True
        await self.emit(QuestionAnswered(self, correctly, self.difficulty))

    async def on_countdown_finished(self):
        if not self.question_answered:
            self.disable_answers()
            await self.emit(QuestionAnswered(self, False, self.difficulty))

    def disable_answers(self) -> None:
        for button in self.query(Button):
            button.disabled = True


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
