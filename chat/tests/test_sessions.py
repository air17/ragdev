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


def test_delete_session():
    """Test deleting a session."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a session
        session_id = "test-session-to-delete"
        session = ChatSessionManager(sessions_dir=temp_dir)
        session.create_session(session_id=session_id)

        # Verify session exists
        session_file = Path(temp_dir) / f"{session_id}.pickle"
        assert session_file.exists()

        # Delete the session
        ChatSessionManager.delete_session(sessions_dir=temp_dir, session_id=session_id)

        # Verify session is deleted
        assert not session_file.exists()

        # Test deleting non-existent session (should not raise an error)
        ChatSessionManager.delete_session(
            sessions_dir=temp_dir, session_id="non-existent"
        )


def test_fix_messages_after_interruption():
    """Test fixing messages after interruption."""
    with tempfile.TemporaryDirectory() as temp_dir:
        session = ChatSessionManager(sessions_dir=temp_dir)
        session_id = "test-fix-messages"

        # Test case 1: Messages after last assistant message should be removed
        session.create_session(session_id=session_id)
        test_messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
            {"role": "user", "content": "Another user message"},
        ]
        session.append_messages(test_messages)

        # Fix messages after interruption
        session.fix_messages_after_interruption()

        # Should only have messages up to and including the last assistant message
        messages = session.get_messages()
        assert len(messages) == 2
        assert messages[0]["content"] == "Hello"
        assert messages[1]["content"] == "Hi there!"
        assert messages[1]["role"] == "assistant"

        # Test case 2: No assistant messages - all messages should be cleared
        session = ChatSessionManager(sessions_dir=temp_dir)
        session_id_2 = "test-fix-messages-2"
        session.create_session(session_id=session_id_2)
        user_only_messages = [
            {"role": "user", "content": "Hello"},
            {"role": "user", "content": "How are you?"},
            {"role": "user", "content": "Another message"},
        ]
        session.append_messages(user_only_messages)

        # Fix messages after interruption
        session.fix_messages_after_interruption()

        # All messages should be cleared since no assistant messages exist
        messages = session.get_messages()
        assert len(messages) == 0

        # Test case 3: Empty message list should remain empty
        session = ChatSessionManager(sessions_dir=temp_dir)
        session_id_3 = "test-fix-messages-3"
        session.create_session(session_id=session_id_3)

        # Fix messages on empty session
        session.fix_messages_after_interruption()

        # Should still be empty
        messages = session.get_messages()
        assert len(messages) == 0

        # Test case 4: Last message is assistant message - no changes needed
        session = ChatSessionManager(sessions_dir=temp_dir)
        session_id_4 = "test-fix-messages-4"
        session.create_session(session_id=session_id_4)
        complete_conversation = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "Thanks"},
            {"role": "assistant", "content": "You're welcome!"},
        ]
        session.append_messages(complete_conversation)

        # Fix messages after interruption
        session.fix_messages_after_interruption()

        # All messages should remain since last message is from assistant
        messages = session.get_messages()
        assert len(messages) == 4
        assert messages[-1]["role"] == "assistant"
        assert messages[-1]["content"] == "You're welcome!"

        # Test case 5: Last assistant message has tool_calls (incomplete turn)
        # The method must skip it and fall back to the previous complete assistant message.
        session = ChatSessionManager(sessions_dir=temp_dir)
        session_id_5 = "test-fix-messages-5"
        session.create_session(session_id=session_id_5)
        tool_call_interrupted = [
            {"role": "user", "content": "Search for foo"},
            {"role": "assistant", "content": "Sure!"},
            {"role": "user", "content": "Now search for bar"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "tc1", "function": {"name": "grep_search"}}],
            },
            # tool response is missing — interrupted here
        ]
        session.append_messages(tool_call_interrupted)
        session.fix_messages_after_interruption()

        # Should roll back to the last *complete* assistant message (index 1)
        messages = session.get_messages()
        assert len(messages) == 2
        assert messages[-1]["role"] == "assistant"
        assert messages[-1]["content"] == "Sure!"
        assert not messages[-1].get("tool_calls")

        # Test case 6: All assistant messages have tool_calls — clear everything
        session = ChatSessionManager(sessions_dir=temp_dir)
        session_id_6 = "test-fix-messages-6"
        session.create_session(session_id=session_id_6)
        all_tool_calls = [
            {"role": "user", "content": "Do something"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "tc2", "function": {"name": "grep_search"}}],
            },
        ]
        session.append_messages(all_tool_calls)
        session.fix_messages_after_interruption()

        messages = session.get_messages()
        assert len(messages) == 0
