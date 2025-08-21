import json
import os
from typing import TypedDict

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
)
from chat.const import SYSTEM_PROMPT
from chat.sessions import ChatSessionManager
from config import (
    DEFAULT_COLLECTION_NAME,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_API_KEY,
    DEFAULT_PROJECT_DIR,
)
from rag.embeddings import EmbeddingManager
from rag.reranker import rerank_results
from rag.snippet_reader import read_snippets


class ChatAgent:
    def __init__(
        self,
        project_dir: str = DEFAULT_PROJECT_DIR,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        api_key: str = DEEPSEEK_API_KEY,
        model: str = "deepseek-reasoner",
        max_iterations: int = 15,
        session_manager: ChatSessionManager | None = None,
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
        self.embedding_manager = EmbeddingManager(collection_name=collection_name)

        self.tools: tuple[ChatCompletionToolParam, ...] = (
            ChatCompletionToolParam(
                type="function",
                function=FunctionDefinition(
                    name="semantic_search",
                    description="Find snippets of code from the codebase most relevant to the search query.\\nThis is a semantic search tool, so the query should ask for something semantically matching what is needed.\\nIf it makes sense to only search in particular directories, please specify them in the target_directories field.\\nUnless there is a clear reason to use your own search query, please just reuse the user's exact query with their wording.\\nTheir exact wording/phrasing can often be helpful for the semantic search query. Keeping the same exact question format can also be helpful.",
                    parameters={
                        "type": "object",
                        "required": ["question"],
                        "properties": {
                            "question": {
                                "type": "string",
                                "description": "The search query to find relevant code.",
                            },
                            "dir_path": {
                                "type": "string",
                                "description": "The directory to search over (optional).",
                            },
                        },
                    },
                ),
            ),
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
                    description="Read the contents of a file. The output of this tool call will be the 1-indexed file contents from start_line_one_indexed to end_line_one_indexed_inclusive, together with a summary of the lines outside start_line_one_indexed and end_line_one_indexed_inclusive.\\nNote that this call can view at most 250 lines at a time.\\n\\nWhen using this tool to gather information, it's your responsibility to ensure you have the COMPLETE context. Specifically, each time you call this command you should:\\n1) Assess if the contents you viewed are sufficient to proceed with your task.\\n2) Take note of where there are lines not shown.\\n3) If the file contents you have viewed are insufficient, and you suspect they may be in lines not shown, proactively call scroll_down or scroll_up tools to view those lines.\\n4) When in doubt, call this tool again to gather more information. Remember that partial file views may miss critical dependencies, imports, or functionality.",
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
            ChatCompletionToolParam(
                type="function",
                function=FunctionDefinition(
                    name="terminal",
                    description="Propose a command to run on behalf of the user in the project root directory.",
                    parameters={
                        "type": "object",
                        "required": ["command", "explanation"],
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "The terminal command to execute.",
                            },
                            "explanation": {
                                "description": "One sentence explanation as to why this command needs to be run and how it contributes to the goal.",
                                "type": "string",
                            },
                        },
                    },
                ),
            ),
        )
        self.project_prompt = self._get_project_prompt()
        self.system_prompt = SYSTEM_PROMPT.format(
            project_tree=ls(self.project_dir), project_prompt=self.project_prompt
        )

    def get_deepseek_response_text(self, user_question: str) -> str:
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
            response: ChatCompletion = self.deepseek.chat.completions.create(
                model=self.model, messages=self.messages, tools=self.tools
            )
            new_assistant_message: ChatCompletionMessage = response.choices[0].message
            print(
                f"ASSISTANT_OUTPUT: {new_assistant_message.content}\nTOOL_CALLS: {new_assistant_message.tool_calls}"
            )
            self._append_message(
                ChatCompletionAssistantMessageParam(
                    content=new_assistant_message.content,
                    role="assistant",
                    tool_calls=new_assistant_message.tool_calls,
                )
            )
            if new_assistant_message.tool_calls:
                iterations += 1
                if iterations > self.max_iterations:
                    self._append_message(
                        ChatCompletionSystemMessageParam(
                            content="Error: too many iterations, answer with what you have so far",
                            role="system",
                        )
                    )
                    self._append_message(
                        self.deepseek.chat.completions.create(
                            model=self.model, messages=self.messages, tools=self.tools
                        )
                        .choices[0]
                        .message
                    )
                    return self.messages[-1].content

                tool = new_assistant_message.tool_calls[0].function.name
                args_json = new_assistant_message.tool_calls[0].function.arguments
                args = json.loads(args_json)
                print(f"TOOL_CALL: {tool}({args})")
                # Dispatch
                result: str = self.dispatch_tool_call(tool, args)
                print(f"TOOL_RESULT: {result}")
                self._append_message(
                    ChatCompletionToolMessageParam(
                        role="tool",
                        tool_call_id=new_assistant_message.tool_calls[0].id,
                        content=json.dumps(result),
                    )
                )
            else:
                response_text: str = new_assistant_message.content
                return response_text

    def run(self, user_question: str) -> str:
        if "deepseek" in self.model:
            response_text = self.get_deepseek_response_text(user_question)
        else:
            raise ValueError(f"Unsupported model: {self.model}")
        return response_text

    def dispatch_tool_call(self, tool, args):
        try:
            if tool == "semantic_search":
                vector_results = rerank_results(
                    args["question"],
                    read_snippets(
                        self.embedding_manager.retrieve_vectors_for_question(
                            args["question"], 10, args.get("dir_path", None)
                        ),
                        base_dir=self.project_dir,
                    ),
                    max_results=3,
                )
                for record in vector_results:
                    record.pop("id", None)
                    record.pop("distance", None)
                result: str = json.dumps(vector_results)
            elif tool == "grep_search":
                path: str = self.project_dir
                if args.get("path"):
                    path += "/" + args["path"]
                result = search_codebase(args["query"], self.project_dir)
            elif tool == "read_file":
                end_line: int | None = (
                    args.get("end_line_one_indexed_inclusive")
                    or args.get("end_line_one_indexed")
                    or args.get("end_line")
                )
                start_line: int | None = args.get("start_line_one_indexed") or args.get(
                    "start_line"
                )
                if not start_line:
                    raise ValueError("start_line is required")
                # show additional 10 lines after end_line
                if end_line:
                    end_line += 10
                result = read_file_with_context(
                    self.project_dir + "/" + args["path"],
                    int(start_line),
                    int(end_line) if end_line else None,
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
                result = "The terminal is currently unavailable. Don't use it throughout this session."
            else:
                result = f"Error: unknown tool {tool}"
        except Exception as e:
            result = f"Tool call failed with exception: {e}"
        return result

    def _append_message(self, message: type[TypedDict]) -> None:
        """Append message to in-memory history and persist if session provided."""
        self.messages.append(message)
        if self.session_manager:
            self.session_manager.append_messages([message])

    def _get_project_prompt(self) -> str:
        try:
            with open(os.path.join(self.project_dir, "project_prompt.txt"), "r") as f:
                prompt: str = "\nCodebase description:\n" + f.read()
        except FileNotFoundError:
            prompt = ""
        return prompt
