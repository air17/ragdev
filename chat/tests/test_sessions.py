import os
import tempfile
from pathlib import Path

import pytest

from chat.sessions import ChatSessionManager


def test_create_session():
    """Test creating a new session with and without a custom ID."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Test creating with auto-generated ID
        ChatSessionManager(sessions_dir=temp_dir).create_session()
        assert len(os.listdir(temp_dir)) == 1

        # Test creating with custom ID
        custom_id = "test-session-123"
        session = ChatSessionManager(sessions_dir=temp_dir)
        session.create_session(session_id=custom_id)
        assert (Path(temp_dir) / f"{custom_id}.pickle").exists()
        assert session.active_session == custom_id


def test_append_and_retrieve_messages():
    """Test appending and retrieving messages from a session."""
    with tempfile.TemporaryDirectory() as temp_dir:
        session = ChatSessionManager(sessions_dir=temp_dir)
        session.create_session()
        test_messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]

        # Test appending messages
        session.append_messages(test_messages)

        # Test retrieving messages
        messages = session.get_messages()
        assert len(messages) == 2
        assert messages[0]["content"] == "Hello"
        assert messages[1]["content"] == "Hi there!"


def test_list_sessions():
    """Test listing available sessions."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create multiple sessions
        [
            ChatSessionManager(sessions_dir=temp_dir).create_session(
                session_id=f"session-{i}"
            )
            for i in range(3)
        ]

        # Test listing sessions
        session_list = ChatSessionManager(sessions_dir=temp_dir).list_sessions()
        assert len(session_list) == 3
        assert all("id" in s and "updated_at" in s for s in session_list)


def test_load_nonexistent_session():
    """Test loading a non-existent session raises FileNotFoundError."""
    with tempfile.TemporaryDirectory() as temp_dir:
        session = ChatSessionManager(sessions_dir=temp_dir)
        with pytest.raises(FileNotFoundError):
            session.load_full("non-existent-session")


def test_append_to_nonexistent_session():
    """Test initializing a non-existent session raises FileNotFoundError."""
    with tempfile.TemporaryDirectory() as temp_dir:
        with pytest.raises(FileNotFoundError):
            ChatSessionManager(sessions_dir=temp_dir, session_id="test-session")
