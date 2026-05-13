import logging
import pickle
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict, Any

logger: logging.Logger = logging.getLogger(__name__)


def _now() -> str:
    """Return the current UTC time in ISO 8601 format with Z suffix."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


class ChatSessionManager:
    """Manages chat sessions stored as JSON files on disk."""

    def __init__(
        self, sessions_dir: str = "sessions", session_id: str | None = None
    ) -> None:
        self.dir: Path = Path(sessions_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

        if session_id:
            # load project_dir and meta
            data: type[TypedDict] = self.load_full(session_id)
            self.project_dir: str | None = data.get("meta", {}).get("project_dir")
            self.project_prompt: str | None = data.get("meta", {}).get("project_prompt")
            self.submodules: tuple[str, ...] = data.get("meta", {}).get(
                "submodules", ()
            )
            self.repo_url: str | None = data.get("meta", {}).get("repo_url")

        self.active_session: str = session_id

    def _path(self, sid: str) -> Path:
        """Return the file path for a given session ID."""
        return self.dir / f"{sid}.pickle"

    @staticmethod
    def _write(path: Path, data: Any) -> None:
        """Write data to disk atomically."""
        with path.open("wb") as f:
            pickle.dump(data, f)

    def create_session(
        self,
        initial: list[type[TypedDict]] | None = None,
        session_id: str | None = None,
        project_dir: str | None = None,
        project_prompt: str | None = None,
        submodules: tuple[str, ...] | None = None,
        repo_url: str | None = None,
    ) -> str:
        """Create a new chat session with optional initial messages, and return its ID."""
        sid: str = session_id or str(uuid.uuid4())
        meta: dict[str, str | None] = {
            "id": sid,
            "project_dir": project_dir,
            "project_prompt": project_prompt,
            "submodules": submodules or (),
            "repo_url": repo_url,
            "created_at": _now(),
            "updated_at": _now(),
        }
        payload: type[TypedDict] = {"meta": meta, "messages": initial or []}
        self._write(self._path(sid), payload)
        self.project_dir = project_dir
        self.project_prompt = project_prompt
        self.submodules = submodules or ()
        self.repo_url = repo_url
        self.active_session = sid
        return sid

    def list_sessions(self) -> list[type[TypedDict]]:
        """Return a list of available sessions with their metadata."""
        sessions: list[type[TypedDict]] = []
        for p in sorted(self.dir.glob("*.pickle")):
            try:
                data: type[TypedDict] = self.load_full(p.stem)
                meta: type[TypedDict] = data.get("meta", {})
                sessions.append(
                    {
                        "id": meta.get("id", p.stem),
                        "updated_at": meta.get("updated_at"),
                        "project_dir": meta.get("project_dir"),
                        "total_tokens": meta.get("total_tokens"),
                    }
                )
            except Exception:
                continue
        return sessions

    def load_full(self, sid: str) -> Any:
        """Load the full session data for a given ID."""
        p: Path = self._path(sid)
        if not p.exists():
            raise FileNotFoundError(sid)
        with p.open("rb") as f:
            return pickle.load(f)

    def get_messages(self) -> list[type[TypedDict]]:
        """Get the list of messages for the active session."""
        return self.load_full(self.active_session).get("messages", [])

    def get_meta(self) -> type[TypedDict]:
        """Get the metadata for the active session."""
        return self.load_full(self.active_session).get("meta", {})

    def append_messages(
        self, messages: list[type[TypedDict]], total_tokens: int | None = None
    ) -> None:
        """Append messages to the active session and update its timestamp."""
        p: Path = self._path(self.active_session)
        data: type[TypedDict] = self.load_full(self.active_session)
        data.setdefault("messages", []).extend(messages)
        data.setdefault("meta", {})["updated_at"] = _now()
        if total_tokens is not None:
            data["meta"]["total_tokens"] = total_tokens
        self._write(p, data)

    @classmethod
    def delete_session(
        cls, sessions_dir: str = "sessions", session_id: str = ""
    ) -> None:
        """Delete a session by its ID."""
        p: Path = Path(sessions_dir) / f"{session_id}.pickle"
        if p.exists():
            p.unlink()
        else:
            logger.warning(f"Session file {p} does not exist and cannot be deleted.")

    def fix_messages_after_interruption(self) -> None:
        """Cleans up all the messages after the last complete assistant message.

        A "complete" assistant message is one without ``tool_calls``.  Messages
        that contain ``tool_calls`` require subsequent tool-response messages; if
        those responses are absent (e.g. after a crash) the API returns 400.
        If no complete assistant message exists, all messages are cleared.
        """
        p: Path = self._path(self.active_session)
        data: type[TypedDict] = self.load_full(self.active_session)
        messages: list[type[TypedDict]] = data.get("messages", [])
        if not messages:
            return
        # Find the last assistant message that has no tool_calls (a final reply).
        last_assistant_index: int | None = None
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            if msg.get("role") == "assistant" and not msg.get("tool_calls"):
                last_assistant_index = i
                break
        if last_assistant_index is None:
            # No complete assistant message found, clear all messages
            data["messages"] = []
        else:
            # Retain messages up to and including the last complete assistant message
            data["messages"] = messages[: last_assistant_index + 1]
        data.setdefault("meta", {})["updated_at"] = _now()
        self._write(p, data)
