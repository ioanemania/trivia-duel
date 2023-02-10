import html

from trivia_tui.types import TrainingQuestionData


def decode_training_questions(questions: list[TrainingQuestionData]) -> list[TrainingQuestionData]:
    for question in questions:
        question["question"] = html.unescape(question["question"])
        question["correct_answer"] = html.unescape(question["correct_answer"])

        for idx, incorrect_answer in enumerate(question["incorrect_answers"]):
            question["incorrect_answers"][idx] = html.unescape(incorrect_answer)

    return questions
