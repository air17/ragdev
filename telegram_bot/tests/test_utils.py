from unittest.mock import patch

from telegram_bot.utils import markdown_to_telegram_html_ai


@patch("telegram_bot.utils.remove_non_telegram_html")
@patch("telegram_bot.utils.query_deepseek")
def test_markdown_converter_uses_v4_flash(query_deepseek_mock, clean_html_mock):
    query_deepseek_mock.return_value = "<b>hello</b>"
    clean_html_mock.return_value = "<b>hello</b>"

    result = markdown_to_telegram_html_ai("**hello**")

    assert result == "<b>hello</b>"
    assert query_deepseek_mock.call_args.kwargs["model"] == "deepseek-v4-flash"
    assert query_deepseek_mock.call_args.kwargs["thinking"] is False
