import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.tasks import pull_all_repos_task, _notify_admins


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_bot():
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    return bot


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.get_users_by_role = AsyncMock(return_value=[])
    return db


@pytest.fixture
def make_admin():
    def _make(user_id: int):
        admin = MagicMock()
        admin.user_id = user_id
        return admin

    return _make


# Minimal fake PROJECTS dict used across tests
FAKE_PROJECTS = {
    "proj_a": {
        "name": "Project A",
        "project_dir": "/repos/proj_a",
        "submodules": ("sub1",),
        "project_prompt": "",
        "repo_url": None,
    },
    "proj_b": {
        "name": "Project B",
        "project_dir": "/repos/proj_b",
        "submodules": (),
        "project_prompt": "",
        "repo_url": None,
    },
    "proj_empty": {
        "name": "Empty Dir Project",
        "project_dir": "",  # should be skipped
        "submodules": (),
        "project_prompt": "",
        "repo_url": None,
    },
}


# ---------------------------------------------------------------------------
# _notify_admins
# ---------------------------------------------------------------------------


class TestNotifyAdmins:
    @pytest.mark.asyncio
    async def test_sends_to_all_admins(self, mock_bot, mock_db, make_admin):
        mock_db.get_users_by_role.return_value = [make_admin(1), make_admin(2)]

        await _notify_admins(mock_bot, mock_db, "hello")

        assert mock_bot.send_message.call_count == 2
        mock_bot.send_message.assert_any_call(
            chat_id=1, text="hello", parse_mode="HTML"
        )
        mock_bot.send_message.assert_any_call(
            chat_id=2, text="hello", parse_mode="HTML"
        )

    @pytest.mark.asyncio
    async def test_no_admins_no_send(self, mock_bot, mock_db):
        mock_db.get_users_by_role.return_value = []
        await _notify_admins(mock_bot, mock_db, "hello")
        mock_bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_individual_send_failure_is_swallowed(
        self, mock_bot, mock_db, make_admin
    ):
        mock_db.get_users_by_role.return_value = [make_admin(1), make_admin(2)]
        mock_bot.send_message.side_effect = [Exception("network error"), None]

        # Should not raise
        await _notify_admins(mock_bot, mock_db, "hello")

    @pytest.mark.asyncio
    async def test_db_failure_is_swallowed(self, mock_bot, mock_db):
        mock_db.get_users_by_role.side_effect = Exception("db error")
        # Should not raise
        await _notify_admins(mock_bot, mock_db, "hello")
        mock_bot.send_message.assert_not_called()


# ---------------------------------------------------------------------------
# pull_all_repos_task
# ---------------------------------------------------------------------------


class TestPullAllReposTask:
    @pytest.mark.asyncio
    async def test_happy_path_pulls_all_configured_projects(self, mock_bot, mock_db):
        """pull_current_branch is called for every project that has a project_dir."""
        with (
            patch("telegram_bot.tasks.PROJECTS", FAKE_PROJECTS),
            patch("telegram_bot.tasks.pull_current_branch") as mock_pull,
        ):
            await pull_all_repos_task(mock_bot, mock_db)

        assert mock_pull.call_count == 2  # proj_empty is skipped
        mock_pull.assert_any_call("/repos/proj_a", ("sub1",))
        mock_pull.assert_any_call("/repos/proj_b", ())
        mock_bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_empty_project_dir(self, mock_bot, mock_db):
        """Projects with an empty project_dir are never passed to pull_current_branch."""
        with (
            patch("telegram_bot.tasks.PROJECTS", FAKE_PROJECTS),
            patch("telegram_bot.tasks.pull_current_branch") as mock_pull,
        ):
            await pull_all_repos_task(mock_bot, mock_db)

        called_dirs = [c.args[0] for c in mock_pull.call_args_list]
        assert "" not in called_dirs

    @pytest.mark.asyncio
    async def test_failure_notifies_admins_and_continues(
        self, mock_bot, mock_db, make_admin
    ):
        """On per-project failure admins are notified; remaining projects still run."""
        mock_db.get_users_by_role.return_value = [make_admin(99)]

        def _pull_side_effect(project_dir: str, submodules: tuple) -> None:
            if project_dir == "/repos/proj_a":
                raise RuntimeError("auth failed")

        with (
            patch("telegram_bot.tasks.PROJECTS", FAKE_PROJECTS),
            patch(
                "telegram_bot.tasks.pull_current_branch", side_effect=_pull_side_effect
            ) as mock_pull,
        ):
            await pull_all_repos_task(mock_bot, mock_db)

        # Both configured projects were attempted
        assert mock_pull.call_count == 2

        # Admin was notified exactly once (only proj_a failed)
        mock_bot.send_message.assert_called_once()
        sent_text: str = mock_bot.send_message.call_args.kwargs["text"]
        assert "Project A" in sent_text
        assert "auth failed" in sent_text

    @pytest.mark.asyncio
    async def test_failure_message_format(self, mock_bot, mock_db, make_admin):
        """Failure notification matches AUTO_PULL_FAILED_MESSAGE template."""
        mock_db.get_users_by_role.return_value = [make_admin(1)]

        with (
            patch("telegram_bot.tasks.PROJECTS", FAKE_PROJECTS),
            patch(
                "telegram_bot.tasks.pull_current_branch",
                side_effect=RuntimeError("timeout"),
            ),
        ):
            await pull_all_repos_task(mock_bot, mock_db)

        # Two projects fail → two notifications to admin 1
        assert mock_bot.send_message.call_count == 2
        for c in mock_bot.send_message.call_args_list:
            assert c.kwargs.get("parse_mode") == "HTML"
            assert "⚠️" in c.kwargs["text"]
