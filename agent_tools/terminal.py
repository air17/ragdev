import os
import signal
import subprocess

MAX_TIMEOUT_SECONDS: int = 120
MAX_OUTPUT_CHARS: int = 8000


def run_terminal_command(command: str, cwd: str, timeout_seconds: int = 10) -> str:
    """Run a shell command in a new process group, kill the whole group on timeout.

    Args:
        command: Shell command string to execute.
        cwd: Working directory for the command (project root).
        timeout_seconds: Maximum seconds to wait. Capped at MAX_TIMEOUT_SECONDS (120).

    Returns:
        Combined stdout+stderr output (truncated at 8 000 chars), prefixed with the
        exit code, or a timeout notice if the process group was killed.
    """
    effective_timeout: int = min(timeout_seconds, MAX_TIMEOUT_SECONDS)

    proc = subprocess.Popen(
        command,
        shell=True,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )

    try:
        stdout_bytes, stderr_bytes = proc.communicate(timeout=effective_timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
        return (
            f"[timeout] Command exceeded {effective_timeout}s and was killed.\n"
            f"Command: {command}"
        )

    stdout: str = stdout_bytes.decode(errors="replace")
    stderr: str = stderr_bytes.decode(errors="replace")
    combined: str = stdout
    if stderr:
        combined = combined + ("[stderr]\n" + stderr if combined else stderr)

    truncated: bool = len(combined) > MAX_OUTPUT_CHARS
    if truncated:
        combined = combined[:MAX_OUTPUT_CHARS] + "\n... (output truncated)"

    exit_code: int = proc.returncode
    prefix: str = f"[exit {exit_code}]\n" if exit_code != 0 else ""
    return prefix + combined
