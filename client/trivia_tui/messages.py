from textual.message import Message, MessageTarget
from textual.widgets import Button


class GameStarted(Message):
    bubble = False


class NextQuestion(Message):
    bubble = False


class CountdownFinished(Message):
    bubble = False


class QuestionAnswered(Message):
    bubble = False

    def __init__(self, sender: MessageTarget, answer: str):
        self.answer = answer
        super().__init__(sender)


class TrainingQuestionAnswered(Message):
    bubble = False

    def __init__(self, sender: MessageTarget, correctly: bool, difficulty: str) -> None:
        self.correctly = correctly
        self.difficulty = difficulty
        super().__init__(sender)


class FiftyFiftyTriggered(Message):
    bubble = False

    def __init__(self, sender: MessageTarget, incorrect_answers: list[str]):
        self.incorrect_answers = incorrect_answers
        super().__init__(sender)


class GameTimedOut(Message):
    bubble = False


class BackButtonPressed(Message):
    pass


class GameLeaveRequested(Message):
    bubble = False
