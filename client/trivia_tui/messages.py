from textual.message import Message, MessageTarget


class GameStarted(Message):
    bubble = False


class NextQuestion(Message):
    bubble = False


class CountdownFinished(Message):
    bubble = False


class QuestionAnswered(Message):
    bubble = False

    def __init__(self, sender: MessageTarget, correctly: bool, difficulty: str) -> None:
        self.correctly = correctly
        self.difficulty = difficulty
        super().__init__(sender)
