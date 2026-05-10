from unittest.mock import MagicMock, patch
from chat.agent import ChatAgent
from chat.sessions import ChatSessionManager
from config import DEEPSEEK_BASE_URL


def test_chat_agent_initialization():
    """Test that ChatAgent initializes with default parameters."""
    agent = ChatAgent(project_dir="/test/project")
    assert agent.project_dir == "/test/project"
    assert agent.messages == []
    assert agent.model == "deepseek-v4-flash"


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


@patch("chat.agent.OpenAI")
def test_tool_call_assistant_message_includes_reasoning_content(mock_openai):
    """reasoning_content must be forwarded to the API in tool-call turns (thinking mode)."""
    mock_create = mock_openai.return_value.chat.completions.create

    tool_call = MagicMock()
    tool_call.id = "call_1"
    tool_call.function.name = "list_dir"
    tool_call.function.arguments = '{"path": "."}'

    first_message = MagicMock()
    first_message.content = None
    first_message.tool_calls = [tool_call]
    first_message.reasoning_content = "I should list the directory first."
    first_response = MagicMock()
    first_response.choices = [MagicMock(message=first_message)]
    first_response.usage = MagicMock(total_tokens=10)

    final_message = MagicMock()
    final_message.content = "Done"
    final_message.tool_calls = None
    final_response = MagicMock()
    final_response.choices = [MagicMock(message=final_message)]

    mock_create.side_effect = [first_response, final_response]
    agent = ChatAgent(project_dir="/test/project", api_key="test_key")

    list(agent.get_deepseek_response_text("question"))

    # The assistant message appended after the first tool call must carry reasoning_content
    assistant_msgs = [m for m in agent.messages if m.get("role") == "assistant"]
    assert len(assistant_msgs) == 1
    assert assistant_msgs[0].get("reasoning_content") == "I should list the directory first."


# ---------------------------------------------------------------------------
# Terminal tool presence / ordering
# ---------------------------------------------------------------------------


def test_terminal_absent_by_default():
    agent = ChatAgent(project_dir="/test/project")
    tool_names = [t["function"]["name"] for t in agent.tools]
    assert "terminal" not in tool_names
    assert agent.terminal_enabled is False


def test_terminal_present_and_first_when_enabled():
    agent = ChatAgent(project_dir="/test/project", terminal_enabled=True)
    tool_names = [t["function"]["name"] for t in agent.tools]
    assert tool_names[0] == "terminal"
    assert agent.terminal_enabled is True


def test_terminal_schema_includes_timeout_seconds():
    agent = ChatAgent(project_dir="/test/project", terminal_enabled=True)
    terminal_tool = agent.tools[0]
    assert terminal_tool["function"]["name"] == "terminal"
    props = terminal_tool["function"]["parameters"]["properties"]
    assert "timeout_seconds" in props
    assert "command" in props
    assert "explanation" in props


# ---------------------------------------------------------------------------
# Terminal dispatch
# ---------------------------------------------------------------------------


@patch("chat.agent.run_terminal_command")
def test_terminal_dispatch_uses_project_dir_and_caps_timeout(mock_run):
    mock_run.return_value = "ok"
    agent = ChatAgent(project_dir="/my/project", terminal_enabled=True)
    result = agent.dispatch_tool_call(
        "terminal", {"command": "ls", "explanation": "list", "timeout_seconds": 60}
    )
    mock_run.assert_called_once_with("ls", "/my/project", 60)
    assert result == "ok"


@patch("chat.agent.run_terminal_command")
def test_terminal_dispatch_caps_timeout_at_120(mock_run):
    mock_run.return_value = "ok"
    agent = ChatAgent(project_dir="/my/project", terminal_enabled=True)
    agent.dispatch_tool_call(
        "terminal",
        {"command": "sleep 200", "explanation": "long", "timeout_seconds": 999},
    )
    _, _, actual_timeout = mock_run.call_args.args
    assert actual_timeout == 120


@patch("chat.agent.run_terminal_command")
def test_terminal_dispatch_default_timeout(mock_run):
    mock_run.return_value = "ok"
    agent = ChatAgent(project_dir="/my/project", terminal_enabled=True)
    agent.dispatch_tool_call("terminal", {"command": "echo hi", "explanation": "x"})
    _, _, actual_timeout = mock_run.call_args.args
    assert actual_timeout == 30


def test_terminal_dispatch_disabled_returns_unavailable():
    agent = ChatAgent(project_dir="/my/project", terminal_enabled=False)
    result = agent.dispatch_tool_call(
        "terminal", {"command": "rm -rf /", "explanation": "bad"}
    )
    assert "unavailable" in result.lower()


# ---------------------------------------------------------------------------
# System prompt contains terminal instructions when enabled
# ---------------------------------------------------------------------------


def test_system_prompt_contains_terminal_instructions_when_enabled():
    agent = ChatAgent(project_dir="/test/project", terminal_enabled=True)
    assert "terminal" in agent.system_prompt.lower()
    assert "primary" in agent.system_prompt.lower()


def test_system_prompt_no_terminal_instructions_when_disabled():
    agent = ChatAgent(project_dir="/test/project", terminal_enabled=False)
    assert "<terminal_tool>" not in agent.system_prompt
