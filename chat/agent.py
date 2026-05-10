import json
from typing import TypedDict, Generator

from openai import OpenAI
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionUserMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolParam,
    ChatCompletionMessage,
    ChatCompletionToolMessageParam,
    ChatCompletionAssistantMessageParam,
)
from openai.types.shared_params import FunctionDefinition

from agent_tools.file_list import ls
from agent_tools.grep import search_codebase
from agent_tools.read_file import (
    scroll_up,
    scroll_down,
    read_file_with_context,
    read_file,
)
from agent_tools.terminal import run_terminal_command
from chat.const import SYSTEM_PROMPT, TERMINAL_INSTRUCTIONS
from chat.sessions import ChatSessionManager
from config import (
    DEEPSEEK_BASE_URL,
    DEEPSEEK_API_KEY,
)


class ChatAgent:
    def __init__(
        self,
        project_dir: str,
        api_key: str = DEEPSEEK_API_KEY,
        model: str = "deepseek-v4-pro",
        max_iterations: int = 15,
        session_manager: ChatSessionManager | None = None,
        terminal_enabled: bool = False,
    ) -> None:
        # session is optional; if provided, messages are loaded from it and persisted there
        self.session_manager: ChatSessionManager | None = session_manager
        self.messages: list[type[TypedDict]] = (
            self.session_manager.get_messages() if self.session_manager else []
        )

        self.max_iterations: int = max_iterations
        self.deepseek: OpenAI = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
        self.model: str = model
        self.project_dir: str = project_dir
        self.terminal_enabled: bool = terminal_enabled

        self.project_prompt: str | None = (
            session_manager.project_prompt if session_manager else None
        )
        self.submodules: tuple[str] = (
            session_manager.submodules if session_manager else ()
        )
        self.repo_url: str | None = (
            session_manager.repo_url if session_manager else None
        )

        _terminal_tool: ChatCompletionToolParam = ChatCompletionToolParam(
            type="function",
            function=FunctionDefinition(
                name="terminal",
                description=(
                    "Run a non-interactive shell command from the project root. "
                    "This is the primary/default tool for read-only project exploration, code search, "
                    "git inspection, dependency/config discovery, and safe command verification. "
                    "Prefer bounded commands using `rg`, `find`, `sed -n`, and `git`. "
                    "Do not use destructive, mutating, interactive, or long-running commands unless the user explicitly asks. "
                    "Use `cd path && command` for subdirectories when needed."
                    "Commands are non-interactive and run from the project root; use `cd path && command` for subdirs.\n"
                    "IMPORTANT ripgrep flag warning: in `rg`, `-r`/`--replace` substitutes matches in displayed output "
                    "(it is NOT the recursive flag — rg is recursive by default). "
                    "Never use `-r` when you mean recursive search. Use `rg -n <pattern>` for line-numbered search."
                ),
                parameters={
                    "type": "object",
                    "required": ["command", "explanation"],
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The shell command to execute.",
                        },
                        "explanation": {
                            "type": "string",
                            "description": "One sentence explaining why this command is needed and how it contributes to the goal.",
                        },
                        "timeout_seconds": {
                            "type": "integer",
                            "description": "Timeout in seconds. Default 10, hard max 120. Only raise above 10 when justified.",
                        },
                    },
                },
            ),
        )

        _read_search_tools: list[ChatCompletionToolParam] = [
            ChatCompletionToolParam(
                type="function",
                function=FunctionDefinition(
                    name="grep_search",
                    description="Fast text-based regex search that finds exact pattern matches within files or directories, utilizing the ripgrep command for efficient searching.\\nResults will be formatted in the style of ripgrep and include line numbers and content.\\nTo avoid overwhelming output, the results are capped at 50 matches.\\n\\nThis is best for finding exact text matches or regex patterns.\\nMore precise than semantic search for finding specific strings or patterns.\\nThis is preferred over semantic search when we know the exact symbol/function name/etc. to search in some set of directories/file types.",
                    parameters={
                        "type": "object",
                        "required": ["query"],
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The regex pattern to search for",
                            },
                            "path": {
                                "type": "string",
                                "description": "The directory/file to search over (optional).",
                            },
                        },
                    },
                ),
            ),
            ChatCompletionToolParam(
                type="function",
                function=FunctionDefinition(
                    name="read_file",
                    description=(
                        "Read the contents of a file. The output of this tool call will be the 1-indexed file "
                        "contents from start_line_one_indexed to end_line_one_indexed_inclusive.\\n"
                        "Note that this call can view at most 250 lines at a time.\\n\\n"
                        "When using this tool to gather information, it's your responsibility to ensure you "
                        "have the COMPLETE context. Specifically, each time you call this command you should:\\n"
                        "1) Assess if the contents you viewed are sufficient to proceed with your task.\\n"
                        "2) Take note of where there are lines not shown.\\n"
                        "3) If the file contents you have viewed are insufficient, and you suspect they may "
                        "be in lines not shown, proactively call scroll_down or scroll_up tools to view those lines.\\n"
                        "4) When in doubt, call this tool again to gather more information. Remember that "
                        "partial file views may miss critical dependencies, imports, or functionality."
                    ),
                    parameters={
                        "type": "object",
                        "required": ["path", "start_line_one_indexed"],
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "The relative path to the file to read.",
                            },
                            "start_line_one_indexed": {
                                "type": "integer",
                                "description": "The one-indexed line number to start reading from (inclusive).",
                            },
                            "end_line_one_indexed_inclusive": {
                                "type": "integer",
                                "description": "The one-indexed line number to end reading at (inclusive). Optional. Default is 100.",
                            },
                            "with_context": {
                                "type": "boolean",
                                "description": "Whether to include a summary of the lines before and after the specified lines range. Default is false. Use it when you want more context about the specified file.",
                            },
                        },
                    },
                ),
            ),
            ChatCompletionToolParam(
                type="function",
                function=FunctionDefinition(
                    name="list_dir",
                    description="List the contents of a directory. The quick tool to use for discovery, before using more targeted tools like semantic search or file reading. Useful to try to understand the file structure before diving deeper into specific files. Can be used to explore the codebase.",
                    parameters={
                        "type": "object",
                        "required": ["path"],
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Path to list contents of, relative to the workspace root.",
                            },
                        },
                    },
                ),
            ),
            ChatCompletionToolParam(
                type="function",
                function=FunctionDefinition(
                    name="scroll_up",
                    description="Read 100 lines before a given line in a file. This is especially useful when the read_file output is missing important context in previous lines.",
                    parameters={
                        "type": "object",
                        "required": ["path", "line_from"],
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "The relative path to the file.",
                            },
                            "line_from": {
                                "type": "integer",
                                "description": "The starting line number to scroll up from.",
                            },
                        },
                    },
                ),
            ),
            ChatCompletionToolParam(
                type="function",
                function=FunctionDefinition(
                    name="scroll_down",
                    description="Read the next 100 lines immediately after a given line in a file. This is especially useful to load extra context after a read_file call with last line number as a line_from argument.",
                    parameters={
                        "type": "object",
                        "required": ["path", "line_from"],
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "The relative path to the file.",
                            },
                            "line_from": {
                                "type": "integer",
                                "description": "The ending line number to scroll down from.",
                            },
                        },
                    },
                ),
            ),
        ]

        self.tools: list[ChatCompletionToolParam] = (
            [_terminal_tool] + _read_search_tools
            if terminal_enabled
            else _read_search_tools
        )
        self.system_prompt = SYSTEM_PROMPT.format(
            project_tree=ls(self.project_dir),
            project_prompt=(
                "\n<project_rules>\n" + self.project_prompt + "\n</project_rules>\n"
                if self.project_prompt
                else ""
            ),
            repo_url="<repo_url>" + (self.repo_url or "") + "</repo_url>\n",
            terminal_instructions=TERMINAL_INSTRUCTIONS if terminal_enabled else "",
        )

    def get_deepseek_response_text(
        self, user_question: str
    ) -> Generator[tuple[str, str], None, None]:
        """
        Interact with Deepseek's chat completion API to get a response to the user question, handling tool calls as needed.
        Yields tuples of (response_text, status), where status is 'partial' for intermediate responses
        and 'final' for the final response.
        """
        if not self.messages:
            self._append_message(
                ChatCompletionSystemMessageParam(
                    content=self.system_prompt, role="system"
                )
            )
        self._append_message(
            ChatCompletionUserMessageParam(content=user_question, role="user")
        )
        iterations: int = 0
        while True:
            completion_kwargs: dict[str, object] = {
                "model": self.model,
                "messages": self.messages,
            }
            if iterations < self.max_iterations:
                completion_kwargs["tools"] = self.tools
            response: ChatCompletion = self.deepseek.chat.completions.create(
                **completion_kwargs
            )
            new_assistant_message: ChatCompletionMessage = response.choices[0].message
            print(
                f"ASSISTANT_OUTPUT: {new_assistant_message.content}\nTOOL_CALLS: {new_assistant_message.tool_calls}"
            )
            if new_assistant_message.tool_calls:
                # Yield the assistant's output before processing tool calls
                if new_assistant_message.content:
                    yield new_assistant_message.content, "partial"
                iterations += 1
                if iterations > self.max_iterations:
                    self._append_message(
                        ChatCompletionUserMessageParam(
                            content="Error - too many tools use, answer my question with what you have so far:",
                            role="user",
                        )
                    )
                    final_response: ChatCompletionMessage = (
                        self.deepseek.chat.completions.create(
                            model=self.model, messages=self.messages
                        )
                        .choices[0]
                        .message
                    )
                    self._append_message(final_response)
                    yield final_response.content, "final"
                    return

                self._append_message(
                    ChatCompletionAssistantMessageParam(
                        content=new_assistant_message.content,
                        role="assistant",
                        tool_calls=new_assistant_message.tool_calls,
                    ),
                    total_tokens=response.usage.total_tokens
                    if response.usage
                    else None,
                )

                for tool_call in new_assistant_message.tool_calls:
                    tool = tool_call.function.name
                    args_json = tool_call.function.arguments
                    args = json.loads(args_json)
                    print(f"TOOL_CALL: {tool}({args})")
                    # Dispatch
                    result: str = self.dispatch_tool_call(tool, args)
                    print(f"TOOL_RESULT: {result}")
                    self._append_message(
                        ChatCompletionToolMessageParam(
                            role="tool",
                            tool_call_id=tool_call.id,
                            content=json.dumps(result),
                        )
                    )
            else:
                # No tool calls, yield the response if it has content and return it
                response_text: str = new_assistant_message.content
                yield response_text, "final"
                return

    def run(self, user_question: str) -> Generator[tuple[str, str], None, None]:
        if "deepseek" in self.model:
            for output in self.get_deepseek_response_text(user_question):
                yield output
        else:
            raise ValueError(f"Unsupported model: {self.model}")

    def dispatch_tool_call(self, tool, args) -> str:
        try:
            if tool == "grep_search":
                path: str = self.project_dir
                if args.get("path"):
                    path += "/" + args["path"]
                result = search_codebase(args["query"], path, self.project_dir)
            elif tool == "read_file":
                end_line: int | None = (
                    args.get("end_line_one_indexed_inclusive")
                    or args.get("end_line_one_indexed")
                    or args.get("end_line")
                )
                start_line: int | None = args.get("start_line_one_indexed") or args.get(
                    "start_line"
                )
                with_context: bool = args.get("with_context", False)
                if not start_line:
                    raise ValueError("start_line is required")
                # show additional 10 lines after end_line
                if end_line:
                    end_line += 10
                if with_context:
                    result = read_file_with_context(
                        self.project_dir + "/" + args["path"],
                        int(start_line),
                        int(end_line) if end_line else None,
                    )
                else:
                    result = read_file(
                        self.project_dir + "/" + args["path"],
                        int(start_line),
                        int(end_line) if end_line else start_line + 100,
                        add_line_numbers=True,
                    )
            elif tool == "list_dir":
                result = ls(self.project_dir + "/" + args["path"])
            elif tool == "scroll_up":
                result = scroll_up(
                    self.project_dir + "/" + args["path"],
                    int(args["line_from"]),
                )
            elif tool == "scroll_down":
                result = scroll_down(
                    self.project_dir + "/" + args["path"],
                    int(args["line_from"]),
                )
            elif tool == "terminal":
                if self.terminal_enabled:
                    timeout: int = min(int(args.get("timeout_seconds", 10)), 120)
                    result = run_terminal_command(
                        args["command"], self.project_dir, timeout
                    )
                else:
                    result = "The terminal is currently unavailable. Don't use it throughout this session."
            else:
                result = f"Error: unknown tool {tool}"
        except Exception as e:
            result = f"Tool call failed with exception: {e}"
        return result

    def _append_message(
        self, message: type[TypedDict], total_tokens: int | None = None
    ) -> None:
        """Append message to in-memory history and persist if session provided."""
        self.messages.append(message)
        if self.session_manager:
            self.session_manager.append_messages([message], total_tokens=total_tokens)

    @property
    def total_tokens(self) -> int:
        return (
            self.session_manager.get_meta().get("total_tokens", 0)
            if self.session_manager
            else 0
        )
