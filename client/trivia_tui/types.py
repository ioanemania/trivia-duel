from typing import TypedDict, Literal

Difficulty = Literal["easy"] | Literal["medium"] | Literal["hard"]


class QuestionData(TypedDict):
    category: str
    type: Literal["boolean"] | Literal["multiple"]
    difficulty: Difficulty
    question: str
    answers: list[str]
    duration: str


class TrainingQuestionData(TypedDict):
    category: str
    type: Literal["boolean"] | Literal["multiple"]
    difficulty: Difficulty
    question: str
    correct_answer: str
    incorrect_answers: list[str]
