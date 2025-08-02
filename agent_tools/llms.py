from typing import Literal

from openai import OpenAI
from openai.types.chat import (
    ChatCompletionUserMessageParam,
    ChatCompletionSystemMessageParam,
)

from config import DEEPSEEK_API_KEY

deepseek_client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com",
)


def query_deepseek(
    query: str,
    model: Literal["deepseek-chat", "deepseek-reasoner"] = "deepseek-chat",
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
