import json
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
from config import DEFAULT_COLLECTION_NAME, DEEPSEEK_BASE_URL, DEEPSEEK_API_KEY
from rag.embeddings import EmbeddingManager
from rag.reranker import rerank_results
from rag.snippet_reader import read_snippets


class ChatAgent:
    def __init__(
        self,
        project_dir: str = ".",
        collection_name: str = DEFAULT_COLLECTION_NAME,
        api_key: str = DEEPSEEK_API_KEY,
        model: str = "deepseek-reasoner",
        max_iterations: int = 15,
    ):
        self.messages: list[str | type[TypedDict]] = []
        self.max_iterations: int = max_iterations
        # self.gemini: Client = Client(api_key=api_key)
        self.deepseek: OpenAI = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
        self.model: str = model
        self.project_dir = project_dir
        self.embedding_manager = EmbeddingManager(collection_name=collection_name)

        self.tools: tuple[ChatCompletionToolParam, ...] = (
            ChatCompletionToolParam(
                type="function",
                function=FunctionDefinition(
                    name="query_vector_db",
                    description="Query a vector database for code snippets related to the question",
                    parameters={
                        "type": "object",
                        "required": ["question"],
                        "properties": {
                            "question": {
                                "type": "string",
                                "description": "The question to search for similar vectors.",
                            },
                            "dir_path": {
                                "type": "string",
                                "description": "The directory to search in (optional).",
                            },
                        },
                    },
                ),
            ),
            ChatCompletionToolParam(
                type="function",
                function=FunctionDefinition(
                    name="grep_search",
                    description="Search for text patterns in the codebase using grep",
                    parameters={
                        "type": "object",
                        "required": ["query"],
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The text pattern to search for in the codebase.",
                            },
                        },
                    },
                ),
            ),
            ChatCompletionToolParam(
                type="function",
                function=FunctionDefinition(
                    name="read_file",
                    description="Read a specific range of lines from a file",
                    parameters={
                        "type": "object",
                        "required": ["path", "start_line"],
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "The relative path to the file to read.",
                            },
                            "start_line": {
                                "type": "integer",
                                "description": "The starting line number (1-indexed).",
                            },
                            "end_line": {
                                "type": "integer",
                                "description": "The ending line number (1-indexed). Must not exceed start_line + 100.",
                            },
                        },
                    },
                ),
            ),
            ChatCompletionToolParam(
                type="function",
                function=FunctionDefinition(
                    name="ls",
                    description="List files and directories in a given path",
                    parameters={
                        "type": "object",
                        "required": ["path"],
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "The path to list contents of.",
                            },
                        },
                    },
                ),
            ),
            ChatCompletionToolParam(
                type="function",
                function=FunctionDefinition(
                    name="scroll_up",
                    description="Read lines above a given line in a file",
                    parameters={
                        "type": "object",
                        "required": ["path", "start_line"],
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "The relative path to the file.",
                            },
                            "start_line": {
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
                    description="Read lines below a given line in a file",
                    parameters={
                        "type": "object",
                        "required": ["path", "end_line"],
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "The relative path to the file.",
                            },
                            "end_line": {
                                "type": "integer",
                                "description": "The ending line number to scroll down from.",
                            },
                        },
                    },
                ),
            ),
        )
        self.system_prompt = (
            """You're a helpful assistant designed to quickly explore and clarify user ideas, investigate project structures, and retrieve relevant code snippets or information from files.
If it's general question, that can be answered without exploring project just answer without calling tools.
Otherwise, you must use the tools to gather information until you have all necessary context to answer the user question.\n"""
            "Here is the root folder list of files and directories:\n"
            f"{ls(self.project_dir)}\n\n"
            "In your final answer cite code snippets from the codebase and add links to the codebase. Never ever make up code snippets.\n"
        )
        # if "gemini" in self.model:
        #     self.system_prompt += (
        #         "You have these tools available, you can call them as many times as you need:\n"
        #         "  • query_vector_db(question: str, dir_path: str = '')\n"
        #         "  • grep_search(query: str)\n"
        #         "  • read_file(path: str, start_line: int, end_line: int)\n"
        #         "  • ls(path: str)\n"
        #         "  • scroll_up(path: str, start_line: int)\n"
        #         "  • scroll_down(path: str, end_line: int)\n"
        #         "\nWhen you need to call a tool, respond exactly with:\n"
        #         'TOOL: <tool_name>("<argument without name>")\n'
        #         "Be careful to not add any extra text before or after the tool call.\n"
        #         "For example:\n"
        #         'TOOL: query_vector_db("UserSerializer")'
        #         'TOOL: read_file("./relative/path/to/file.py", 12, 93)\n'
        #         "The agent will run the tool, append the result, and prompt you again.\n"
        #         "When using read_file: you can not read more than 100 lines at once (end_line - start_line <= 100).\n"
        #         "When using query_vector_db it returns code chunks but they may be not full (half of class or function) so you may need to read the next lines with tools like scroll_down or read_file. dir_path is optional to specify which directory to search in.\n"
        #         "If you dont need extra context, or you have already got all the information you need, return your final answer in plain text (no TOOL: prefix)."
        #     )

    # def get_gemini_response_text(self, user_question: str) -> str:
    #     self.messages.append(f"User input: {user_question}")
    #     iterations: int = 0
    #
    #     while True:
    #         response: types.GenerateContentResponse = (
    #             self.gemini.models.generate_content(
    #                 model=self.model,
    #                 contents=self.messages,
    #                 config=types.GenerateContentConfig(
    #                     system_instruction=self.system_prompt,
    #                 ),
    #             )
    #         )
    #         response_text: str = response.text
    #         print(f"ASSISTANT_OUTPUT: {response_text}")
    #         self.messages.append(f"Assistant input: {response_text}")
    #
    #         # Check for tool invocation
    #         if response_text.strip().splitlines()[-1].strip().startswith("TOOL:"):
    #             self.call_tool_gemini(response_text)
    #             iterations += 1
    #             if iterations > self.max_iterations:
    #                 self.messages.append(
    #                     "Error: too many iterations, answer with what you have so far"
    #                 )
    #                 return self.gemini.models.generate_content(
    #                     model=self.model,
    #                     contents=self.messages,
    #                     config=types.GenerateContentConfig(
    #                         system_instruction=self.system_prompt,
    #                     ),
    #                 ).text
    #             continue
    #         # No more TOOL calls → final answer
    #         break
    #     return response_text

    def get_deepseek_response_text(self, user_question: str) -> str:
        if not self.messages:
            self.messages.append(
                ChatCompletionSystemMessageParam(
                    content=self.system_prompt, role="system"
                )
            )
        self.messages.append(
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
            self.messages.append(
                ChatCompletionAssistantMessageParam(
                    content=new_assistant_message.content,
                    role="assistant",
                    tool_calls=new_assistant_message.tool_calls,
                )
            )
            if new_assistant_message.tool_calls:
                iterations += 1
                if iterations > self.max_iterations:
                    self.messages.append(
                        ChatCompletionSystemMessageParam(
                            content="Error: too many iterations, answer with what you have so far",
                            role="system",
                        )
                    )
                    self.messages.append(
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
                self.messages.append(
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
        if "gemini" in self.model:
            response_text = self.get_gemini_response_text(user_question)
        elif "deepseek" in self.model:
            response_text = self.get_deepseek_response_text(user_question)
        else:
            raise ValueError(f"Unsupported model: {self.model}")
        return response_text

    # def call_tool_gemini(self, call_text: str):
    #     tool_call = call_text.strip().splitlines()[-1].strip()[5:].strip()
    #     tool_name, args_str = tool_call.split("(", 1)
    #     args = args_str.rstrip(")").strip().strip("'\"")
    #     print(f"TOOL_CALL: {tool_name}({args})")
    #     # Dispatch
    #     result = ""
    #     try:
    #         if tool_name == "query_vector_db":
    #             *query, dir_path = map(lambda x: x.strip("'\""), args.split(", "))
    #             result = rerank_results(
    #                 args,
    #                 read_snippets(
    #                     self.embedding_manager.retrieve_vectors_for_question(
    #                         ", ".join(query), 10, dir_path
    #                     ),
    #                     base_dir=self.project_dir,
    #                 ),
    #                 max_results=5,
    #             )
    #             for record in result:
    #                 record.pop("id", None)
    #                 record.pop("distance", None)
    #         elif tool_name == "grep_search":
    #             result = search_codebase(args, self.project_dir)
    #         elif tool_name == "read_file":
    #             path, start_line, end_line = map(
    #                 lambda x: x.strip("'\""), args.split(", ")
    #             )
    #             result = read_file(
    #                 self.project_dir + "/" + path,
    #                 int(start_line),
    #                 int(end_line),
    #                 add_line_numbers=True,
    #             )
    #         elif tool_name == "ls":
    #             ls(args)
    #         elif tool_name == "scroll_up":
    #             path, start_line = map(lambda x: x.strip("'\""), args.split(", "))
    #             result = scroll_up(path, int(start_line))
    #         elif tool_name == "scroll_down":
    #             path, end_line = map(lambda x: x.strip("'\""), args.split(", "))
    #             result = scroll_down(path, int(end_line))
    #         else:
    #             result = f"Error: unknown tool {tool_name}"
    #     except Exception as e:
    #         result = f"Tool call failed with exception: {e}"
    #
    #     self.messages.append(
    #         f"Tool call: tool name:{tool_name}({args}) result:\n{result}"
    #     )
    #     print("TOOL_RESULT:", str(result)[:100] + "...")

    def dispatch_tool_call(self, tool, args):
        try:
            if tool == "query_vector_db":
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
                result = search_codebase(args["query"], self.project_dir)
            elif tool == "read_file":
                result = read_file_with_context(
                    self.project_dir + "/" + args["path"],
                    int(args["start_line"]),
                    args.get("end_line"),
                )
            elif tool == "ls":
                result = ls(self.project_dir + "/" + args["path"])
            elif tool == "scroll_up":
                result = scroll_up(
                    self.project_dir + "/" + args["path"],
                    int(args["start_line"]),
                )
            elif tool == "scroll_down":
                result = scroll_down(
                    self.project_dir + "/" + args["path"],
                    int(args["end_line"]),
                )
            else:
                result = f"Error: unknown tool {tool}"
        except Exception as e:
            result = f"Tool call failed with exception: {e}"
        return result
