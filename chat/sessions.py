import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict


def _now() -> str:
    """Return the current UTC time in ISO 8601 format with Z suffix."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


class ChatSession:
    """Manages chat sessions stored as JSON files on disk."""

    def __init__(
        self, sessions_dir: str = "sessions", session_id: str | None = None
    ) -> None:
        self.dir: Path = Path(sessions_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

        # Generate session if none provided
        if session_id is None:
            session_id = self.create_session()
        else:
            if not self._path(session_id).exists():
                self.create_session(session_id=session_id)

        self.active_session: str = session_id

    def _path(self, sid: str) -> Path:
        """Return the file path for a given session ID."""
        return self.dir / f"{sid}.json"

    def _write(self, path: Path, data: type[TypedDict]) -> None:
        """Write data to disk atomically."""
        tmp: Path = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    def create_session(
        self,
        initial: list[type[TypedDict]] | None = None,
        session_id: str | None = None,
    ) -> str:
        """Create a new chat session with optional initial messages, and return its ID."""
        sid: str = session_id or str(uuid.uuid4())
        meta: dict[str, str | None] = {
            "id": sid,
            "created_at": _now(),
            "updated_at": _now(),
        }
        payload: type[TypedDict] = {"meta": meta, "messages": initial or []}
        self._write(self._path(sid), payload)
        return sid

    def list_sessions(self) -> list[type[TypedDict]]:
        """Return a list of available sessions with their metadata."""
        sessions: list[type[TypedDict]] = []
        for p in sorted(self.dir.glob("*.json")):
            try:
                with p.open("r", encoding="utf-8") as f:
                    data: type[TypedDict] = json.load(f)
                meta: type[TypedDict] = data.get("meta", {})
                sessions.append(
                    {
                        "id": meta.get("id", p.stem),
                        "updated_at": meta.get("updated_at"),
                    }
                )
            except Exception:
                continue
        return sessions

    def load_full(self, sid: str) -> type[TypedDict]:
        """Load the full session data for a given ID."""
        p: Path = self._path(sid)
        if not p.exists():
            raise FileNotFoundError(sid)
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)

    def get_messages(self) -> list[type[TypedDict]]:
        """Get the list of messages for the active session."""
        return self.load_full(self.active_session).get("messages", [])

    def append_messages(self, messages: list[type[TypedDict]]) -> None:
        """Append messages to the active session and update its timestamp."""
        p: Path = self._path(self.active_session)
        if not p.exists():
            raise FileNotFoundError(self.active_session)
        with p.open("r", encoding="utf-8") as f:
            data: type[TypedDict] = json.load(f)

        data.setdefault("messages", []).extend(messages)
        data.setdefault("meta", {})["updated_at"] = _now()
        self._write(p, data)

    def switch_session(self, sid: str, create_if_missing: bool = False) -> None:
        """Switch to another session, optionally creating it if missing."""
        if not self._path(sid).exists():
            if create_if_missing:
                self.create_session(session_id=sid)
            else:
                raise FileNotFoundError(sid)
        self.active_session = sid


if __name__ == "__main__":
    mgr = ChatSession(sessions_dir="./.sessions_test")
    mgr.append_messages([{"role": "user", "content": "hi"}])
    print(mgr.get_messages())
