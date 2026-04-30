import time
from unittest.mock import patch


from agent_tools.terminal import (
    run_terminal_command,
    MAX_TIMEOUT_SECONDS,
    MAX_OUTPUT_CHARS,
)


class TestRunTerminalCommandSuccess:
    def test_stdout_returned(self, tmp_path):
        result = run_terminal_command("echo hello", str(tmp_path))
        assert "hello" in result

    def test_exit_0_no_prefix(self, tmp_path):
        result = run_terminal_command("echo hi", str(tmp_path))
        assert not result.startswith("[exit")

    def test_stderr_included(self, tmp_path):
        result = run_terminal_command("echo err >&2", str(tmp_path))
        assert "err" in result

    def test_non_zero_exit_prefix(self, tmp_path):
        result = run_terminal_command("exit 1", str(tmp_path))
        assert result.startswith("[exit 1]")

    def test_non_zero_exit_with_output(self, tmp_path):
        result = run_terminal_command("echo bad >&2; exit 2", str(tmp_path))
        assert "[exit 2]" in result
        assert "bad" in result


class TestRunTerminalCommandCwd:
    def test_command_resolves_in_cwd(self, tmp_path):
        (tmp_path / "sentinel.txt").write_text("found_it")
        result = run_terminal_command("cat sentinel.txt", str(tmp_path))
        assert "found_it" in result

    def test_subdir_via_cd(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.txt").write_text("deep_content")
        result = run_terminal_command("cd sub && cat deep.txt", str(tmp_path))
        assert "deep_content" in result


class TestRunTerminalCommandTimeout:
    def test_timeout_kills_process(self, tmp_path):
        start = time.monotonic()
        result = run_terminal_command("sleep 60", str(tmp_path), timeout_seconds=1)
        elapsed = time.monotonic() - start
        assert "[timeout]" in result
        assert elapsed < 10  # should die well under 10s

    def test_timeout_message_includes_timeout_value(self, tmp_path):
        result = run_terminal_command("sleep 60", str(tmp_path), timeout_seconds=1)
        assert "1s" in result

    def test_timeout_cap_at_120(self, tmp_path):
        """timeout_seconds > 120 is silently capped; command with 1s sleep finishes fine."""
        # We pass a huge timeout but the function must cap it internally.
        # Verify the function doesn't raise and the cap constant is 120.
        assert MAX_TIMEOUT_SECONDS == 120
        result = run_terminal_command(
            "echo capped", str(tmp_path), timeout_seconds=9999
        )
        assert "capped" in result

    def test_timeout_cap_enforced_on_long_sleep(self, tmp_path):
        """Internal cap: even if caller passes 9999, communicate is called with at most 120."""
        communicated_with: list[int] = []

        class FakePopen:
            def __init__(self, *args, **kwargs):
                self.pid = 12345
                self.returncode = 0

            def communicate(self, timeout=None):
                communicated_with.append(timeout)
                return b"ok", b""

        with patch("agent_tools.terminal.subprocess.Popen", FakePopen):
            run_terminal_command("echo hi", str(tmp_path), timeout_seconds=9999)

        assert communicated_with == [120]


class TestRunTerminalCommandOutputTruncation:
    def test_output_truncated_at_limit(self, tmp_path):
        # Write a file larger than MAX_OUTPUT_CHARS and cat it
        big = "x" * (MAX_OUTPUT_CHARS + 1000)
        (tmp_path / "big.txt").write_text(big)
        result = run_terminal_command("cat big.txt", str(tmp_path))
        assert len(result) <= MAX_OUTPUT_CHARS + 100  # small buffer for prefix/note
        assert "truncated" in result

    def test_small_output_not_truncated(self, tmp_path):
        result = run_terminal_command("echo small", str(tmp_path))
        assert "truncated" not in result
