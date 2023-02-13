import json
from pathlib import Path
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from textual.css.query import NoMatches
from textual.widgets import Button
from trivia_tui import screens
from trivia_tui.app import BaseApp
from trivia_tui.exceptions import ResponseError
from trivia_tui.messages import TrainingQuestionAnswered
from trivia_tui.widgets import BackButton, TrainingQuestion

FIXTURES_PATH = Path(__file__).resolve().parent / "fixtures"


class BaseTester(BaseApp):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = MagicMock()
        self._push_screen = self.push_screen
        self.push_screen = AsyncMock()


class LoginOrRegisterScreenTestCase(IsolatedAsyncioTestCase):
    class Tester(BaseTester):
        async def on_mount(self) -> None:
            await self._push_screen(screens.LoginOrRegisterScreen())

    async def test_register_success(self):
        async with self.Tester().run_test() as pilot:
            pilot.app.query_one("#btn-register").press()

        pilot.app.client.register.assert_called_once()
        pilot.app.push_screen.assert_awaited_once()
        self.assertIsInstance(pilot.app.push_screen.call_args[0][0], screens.InfoScreen)

    async def test_register_fail(self):
        async with self.Tester().run_test() as pilot:
            pilot.app.client.register.side_effect = ResponseError({"detail": "ERROR!"})
            pilot.app.query_one("#btn-register").press()

        pilot.app.client.register.assert_called_once()
        pilot.app.push_screen.assert_awaited_once()
        self.assertIsInstance(pilot.app.push_screen.call_args[0][0], screens.ErrorScreen)

    async def test_login_success(self):
        async with self.Tester().run_test() as pilot:
            pilot.app.query_one("#btn-login").press()

        pilot.app.client.login.assert_called_once()
        pilot.app.push_screen.assert_awaited_once()
        self.assertIsInstance(pilot.app.push_screen.call_args[0][0], screens.MainMenuScreen)

    async def test_login_fail(self):
        async with self.Tester().run_test() as pilot:
            pilot.app.client.login.side_effect = ResponseError({"detail": "ERROR!"})
            pilot.app.query_one("#btn-login").press()

        pilot.app.client.login.assert_called_once()
        pilot.app.push_screen.assert_awaited_once()
        self.assertIsInstance(pilot.app.push_screen.call_args[0][0], screens.ErrorScreen)

    async def test_query_credentials(self):
        async with self.Tester().run_test() as pilot:
            pilot.app.query_one("#username").value = "TEST_NAME"
            pilot.app.query_one("#password").value = "TEST_PASSWORD"

            username, password = pilot.app.screen.query_credentials()
            self.assertEqual(username, "TEST_NAME")
            self.assertEqual(password, "TEST_PASSWORD")


class MainMenuScreenTestCase(IsolatedAsyncioTestCase):
    class Tester(BaseTester):
        async def on_mount(self) -> None:
            await self._push_screen(screens.MainMenuScreen())

    async def test_play_button(self):
        async with self.Tester().run_test() as pilot:
            pilot.app.query_one("#btn-play").press()
        self.assertIsInstance(pilot.app.push_screen.call_args[0][0], screens.PlayMenuScreen)

    async def test_leaderboard_button(self):
        async with self.Tester().run_test() as pilot:
            pilot.app.query_one("#btn-leaderboard").press()
        self.assertIsInstance(pilot.app.push_screen.call_args[0][0], screens.UserRankingScreen)

    async def test_history_button(self):
        async with self.Tester().run_test() as pilot:
            pilot.app.query_one("#btn-history").press()
        self.assertIsInstance(pilot.app.push_screen.call_args[0][0], screens.GameHistoryScreen)


class PlayMenuScreenTestCase(IsolatedAsyncioTestCase):
    class Tester(BaseTester):
        async def on_mount(self) -> None:
            await self._push_screen(screens.PlayMenuScreen())

    async def test_ranked_button(self):
        screens.JoinOrHostScreen = MagicMock()

        async with self.Tester().run_test() as pilot:
            pilot.app.query_one("#btn-ranked").press()

        self.assertEqual(pilot.app.push_screen.call_args[0][0], screens.JoinOrHostScreen.return_value)
        screens.JoinOrHostScreen.assert_called_once_with("ranked")

    async def test_normal_button(self):
        screens.JoinOrHostScreen = MagicMock()

        async with self.Tester().run_test() as pilot:
            pilot.app.query_one("#btn-normal").press()

        self.assertEqual(pilot.app.push_screen.call_args[0][0], screens.JoinOrHostScreen.return_value)
        screens.JoinOrHostScreen.assert_called_once_with("normal")

    async def test_training_button(self):
        async with self.Tester().run_test() as pilot:
            pilot.app.query_one("#btn-training").press()
        self.assertIsInstance(pilot.app.push_screen.call_args[0][0], screens.TrainingScreen)


class TrainingScreenTestCase(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with open(FIXTURES_PATH / "training_questions.json", "r") as file:
            cls.questions = json.load(file)

    def setUp(self) -> None:
        self.decode_training_questions_patcher = patch("trivia_tui.screens.decode_training_questions")
        self.mock_decode_training_questions = self.decode_training_questions_patcher.start()
        self.mock_decode_training_questions.return_value = self.questions

    def tearDown(self) -> None:
        self.decode_training_questions_patcher.stop()

    class Tester(BaseTester):
        async def on_mount(self) -> None:
            await self._push_screen(screens.TrainingScreen())

    async def test_on_mount_successfully_obtained_questions(self):
        async with self.Tester().run_test() as pilot:
            self.assertEqual(pilot.app.query_one(TrainingQuestion).question_data, self.questions[0])
            pilot.app.query_one("#btn-action")
            pilot.app.client.get_training_questions.assert_called_once()

    async def test_on_mount_failed_to_obtain_questions(self):
        tester = self.Tester()
        tester.client.get_training_questions.side_effect = ResponseError({"detail": "ERROR"})

        async with tester.run_test() as pilot:
            self.assertIsInstance(pilot.app.screen, screens.ErrorScreen)

    async def test_question_was_answered(self):
        async with self.Tester().run_test() as pilot:
            training_question = pilot.app.query_one(TrainingQuestion)
            await pilot.app.screen.post_message(TrainingQuestionAnswered(training_question, False, "easy"))
            await pilot.pause()
            self.assertEqual(str(pilot.app.query_one("#btn-action").label), "Next")

    async def test_last_question_was_answered_but_saving_results_failed(self):
        self.mock_decode_training_questions.return_value = [self.questions[0]]

        async with self.Tester().run_test() as pilot:
            pilot.app.client.post_training_result.side_effect = ResponseError({"detail": "ERROR"})
            training_question = pilot.app.query_one(TrainingQuestion)
            await pilot.app.screen.post_message(TrainingQuestionAnswered(training_question, False, "easy"))
            await pilot.pause()

            self.assertIsInstance(pilot.app.screen, screens.ErrorScreen)

    async def test_last_question_was_answered_and_results_saved(self):
        self.mock_decode_training_questions.return_value = [self.questions[0]]

        async with self.Tester().run_test() as pilot:
            training_question = pilot.app.query_one(TrainingQuestion)
            await pilot.app.screen.post_message(TrainingQuestionAnswered(training_question, False, "easy"))
            await pilot.pause()

            with self.assertRaises(NoMatches):
                pilot.app.query_one("#btn-action")
            pilot.app.query_one(BackButton)
            pilot.app.client.post_training_result.assert_called_once()

    @patch("trivia_tui.screens.TrainingScreen.mount_next_question")
    async def test_skip_button_pressed(self, mock_mount_next_question: AsyncMock):
        async with self.Tester().run_test() as pilot:
            pilot.app.query_one("#btn-action").press()
            await pilot.pause()

            self.assertEqual(pilot.app.screen.questions[-1], self.questions[0])
            self.assertEqual(pilot.app.screen.questions[0], self.questions[1])
            mock_mount_next_question.assert_awaited_once()

    @patch("trivia_tui.screens.TrainingScreen.mount_next_question")
    async def test_next_button_pressed(self, mock_mount_next_question: AsyncMock):
        async with self.Tester().run_test() as pilot:
            training_question = pilot.app.query_one(TrainingQuestion)
            await pilot.app.screen.post_message(TrainingQuestionAnswered(training_question, False, "easy"))
            await pilot.pause()
            pilot.app.query_one("#btn-action").press()
            await pilot.pause()

            self.assertEqual(pilot.app.screen.questions[0], self.questions[1])
            self.assertEqual(len(pilot.app.screen.questions), len(self.questions) - 1)
            mock_mount_next_question.assert_awaited_once()

    @patch("trivia_tui.screens.TrainingScreen.mount_next_question")
    async def test_unexpected_button_pressed(self, mock_mount_next_question: AsyncMock):
        async with self.Tester().run_test() as pilot:
            await pilot.app.screen.post_message(Button.Pressed(Button("UNEXPECTED BUTTON")))
            await pilot.pause()
            mock_mount_next_question.assert_not_awaited()

    async def test_clear_widgets(self):
        async with self.Tester().run_test() as pilot:
            await pilot.app.screen.clear_widgets()

            self.assertEqual(len(pilot.app.screen.children), 0)
            self.assertIsNone(pilot.app.screen.focused)

    async def test_mount_next_question(self):
        async with self.Tester().run_test() as pilot:
            await pilot.app.screen.mount_next_question()
            await pilot.pause()

            self.assertEqual(len(pilot.app.screen.children), 2)
            self.assertIsInstance(pilot.app.screen.children[0], TrainingQuestion)
            self.assertIsInstance(pilot.app.screen.children[1], Button)

    @patch("trivia_tui.screens.TrainingScreen.clear_widgets")
    async def test_escape_key_pressed(self, mock_clear_widgets: AsyncMock):
        async with self.Tester().run_test() as pilot:
            await pilot.press("escape")
            await pilot.pause()

            mock_clear_widgets.assert_awaited_once()
