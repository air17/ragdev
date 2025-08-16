from unittest.mock import MagicMock, patch
from chat.agent import ChatAgent
from chat.sessions import ChatSessionManager
from config import DEEPSEEK_BASE_URL


def test_chat_agent_initialization():
    """Test that ChatAgent initializes with default parameters."""
    agent = ChatAgent(project_dir="/test/project")
    assert agent.project_dir == "/test/project"
    assert agent.model == "deepseek-reasoner"
    assert agent.max_iterations == 15
    assert agent.messages == []


def test_chat_agent_with_session():
    """Test that ChatAgent loads messages from a session if provided."""
    mock_session = MagicMock(spec=ChatSessionManager)
    mock_session.get_messages.return_value = [{"role": "user", "content": "test"}]

    agent = ChatAgent(project_dir="/test/project", session_manager=mock_session)

    mock_session.get_messages.assert_called_once()
    assert len(agent.messages) == 1
    assert agent.messages[0]["content"] == "test"


@patch("chat.agent.OpenAI")
def test_chat_agent_with_custom_parameters(mock_openai):
    """Test that ChatAgent can be initialized with custom parameters."""
    agent = ChatAgent(
        project_dir="/test/project",
        collection_name="test_collection",
        api_key="test_key",
        model="test-model",
        max_iterations=10,
    )

    assert agent.model == "test-model"
    assert agent.max_iterations == 10
    mock_openai.assert_called_once_with(api_key="test_key", base_url=DEEPSEEK_BASE_URL)
