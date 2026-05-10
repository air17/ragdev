from typing import Literal

from openai import OpenAI
from openai.types.chat import (
    ChatCompletionUserMessageParam,
    ChatCompletionSystemMessageParam,
)

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL

deepseek_client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL,
)


def query_deepseek(
    query: str,
    model: Literal["deepseek-v4-flash", "deepseek-v4-pro"] = "deepseek-v4-pro",
    system_prompt: str | None = None,
) -> str:
    messages: list = []
    if system_prompt:
        messages.append(
            ChatCompletionSystemMessageParam(content=system_prompt, role="system")
        )
    messages.append(ChatCompletionUserMessageParam(content=query, role="user"))
    return (
        deepseek_client.chat.completions.create(
            model=model,
            messages=messages,
        )
        .choices[0]
        .message.content
    )
