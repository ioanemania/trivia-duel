import html


def decode_questions(questions: list[dict]) -> list[dict]:
    for question in questions:
        question["question"] = html.unescape(question["question"])
        question["correct_answer"] = html.unescape(question["correct_answer"])

        for idx, incorrect_answer in enumerate(question["incorrect_answers"]):
            question["incorrect_answers"][idx] = html.unescape(incorrect_answer)

    return questions
