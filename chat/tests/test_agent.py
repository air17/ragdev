from unittest.mock import MagicMock, patch
from chat.agent import ChatAgent
from chat.sessions import ChatSessionManager
from config import DEEPSEEK_BASE_URL


def test_chat_agent_initialization():
    """Test that ChatAgent initializes with default parameters."""
    agent = ChatAgent(project_dir="/test/project")
    assert agent.project_dir == "/test/project"
    assert agent.messages == []


def test_chat_agent_with_session():
    """Test that ChatAgent loads messages from a session if provided."""
    mock_session = MagicMock(spec=ChatSessionManager)
    mock_session.get_messages.return_value = [{"role": "user", "content": "test"}]
    mock_session.project_prompt = ""
    mock_session.submodules = ()
    mock_session.repo_url = None

    agent = ChatAgent(project_dir="/test/project", session_manager=mock_session)

    mock_session.get_messages.assert_called_once()
    assert len(agent.messages) == 1
    assert agent.messages[0]["content"] == "test"


@patch("chat.agent.OpenAI")
def test_chat_agent_with_custom_parameters(mock_openai):
    """Test that ChatAgent can be initialized with custom parameters."""
    agent = ChatAgent(
        project_dir="/test/project",
        # collection_name="test_collection",
        api_key="test_key",
        model="test-model",
        max_iterations=10,
    )

    assert agent.model == "test-model"
    assert agent.max_iterations == 10
    mock_openai.assert_called_once_with(api_key="test_key", base_url=DEEPSEEK_BASE_URL)


@patch("chat.agent.OpenAI")
def test_chat_agent_omits_tools_on_final_iteration(mock_openai):
    """Test that available tools are not sent when no tool-use budget remains."""
    mock_create = mock_openai.return_value.chat.completions.create
    tool_call = MagicMock()
    tool_call.id = "call_1"
    tool_call.function.name = "list_dir"
    tool_call.function.arguments = '{"path": "."}'

    first_message = MagicMock()
    first_message.content = None
    first_message.tool_calls = [tool_call]
    first_response = MagicMock()
    first_response.choices = [MagicMock(message=first_message)]
    first_response.usage = MagicMock(total_tokens=42)

    final_message = MagicMock()
    final_message.content = "Final answer"
    final_message.tool_calls = None
    final_response = MagicMock()
    final_response.choices = [MagicMock(message=final_message)]

    mock_create.side_effect = [first_response, final_response]
    agent = ChatAgent(project_dir="/test/project", api_key="test_key", max_iterations=1)

    assert list(agent.get_deepseek_response_text("question")) == [
        ("Final answer", "final")
    ]

    first_call_kwargs = mock_create.call_args_list[0].kwargs
    final_call_kwargs = mock_create.call_args_list[1].kwargs
    assert first_call_kwargs["tools"] == agent.tools
    assert "tools" not in final_call_kwargs
    assert agent.messages[-1]["role"] == "tool"
