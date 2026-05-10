from unittest.mock import MagicMock, patch

from agent_tools.llms import query_deepseek


@patch("agent_tools.llms.deepseek_client")
def test_query_deepseek_uses_v4_pro_by_default(mock_client):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="ok"))]
    mock_client.chat.completions.create.return_value = mock_response

    result = query_deepseek("hello")

    assert result == "ok"
    assert mock_client.chat.completions.create.call_args.kwargs["model"] == (
        "deepseek-v4-pro"
    )


@patch("agent_tools.llms.deepseek_client")
def test_query_deepseek_accepts_v4_flash(mock_client):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="ok"))]
    mock_client.chat.completions.create.return_value = mock_response

    query_deepseek("hello", model="deepseek-v4-flash")

    assert mock_client.chat.completions.create.call_args.kwargs["model"] == (
        "deepseek-v4-flash"
    )
