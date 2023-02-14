import html

from trivia_tui.types import Difficulty, TrainingQuestionData


def decode_training_questions(questions: list[TrainingQuestionData]) -> list[TrainingQuestionData]:
    """
    Decodes a training questions received from the Trivia Duel server.

    Questions are expected to be html escaped. Decoding involves un-escaping
    the html escaped data.

    Args:
        questions: Training questions from the Trivia Duel server

    Returns:
        A list of decoded training questions

    """
    for question in questions:
        question["question"] = html.unescape(question["question"])
        question["correct_answer"] = html.unescape(question["correct_answer"])

        for idx, incorrect_answer in enumerate(question["incorrect_answers"]):
            question["incorrect_answers"][idx] = html.unescape(incorrect_answer)

    return questions


def convert_difficulty_to_stars(difficulty: Difficulty):
    if difficulty == "easy":
        return "*"
    elif difficulty == "medium":
        return "**"

    return "***"
