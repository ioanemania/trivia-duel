from typing import TypedDict, Literal


class QuestionData(TypedDict):
    category: str
    type: Literal["boolean"] | Literal["multiple"]
    difficulty: Literal["easy"] | Literal["medium"] | Literal["hard"]
    question: str
    answers: list[str]
    duration: str


class TrainingQuestionData(TypedDict):
    category: str
    type: Literal["boolean"] | Literal["multiple"]
    difficulty: Literal["easy"] | Literal["medium"] | Literal["hard"]
    question: str
    correct_answer: str
    incorrect_answers: list[str]
