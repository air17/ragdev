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
                    description="Read 100 lines above a given line in a file",
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
                    description="Read 100 lines below a given line in a file",
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
        self.system_prompt = (
            """You're a helpful assistant designed to quickly explore and clarify user ideas, investigate project structures, and retrieve relevant code snippets or information from files.
You have tools at your disposal to understand the codebase and gather more information.\n
If it's a general question, that can be answered without exploring project just answer without calling tools.
Otherwise, you must use the tools to gather information until you have all necessary context to answer the user question.\n"""
            "Here is the root folder list of files and directories:\n"
            f"{ls(self.project_dir)}\n\n"
            """<search_and_reading>
If you are unsure about the answer to the USER's request or how to satiate their request, you should gather more information.
This can be done with additional tool calls, asking clarifying questions, etc...

For example, if you've performed a semantic search, and the results may not fully answer the USER's request, or merit gathering more information, feel free to call more tools.

Bias towards not asking the user for help if you can find the answer yourself.
</search_and_reading>"""
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
                result = search_codebase(args["query"], self.project_dir)
            elif tool == "read_file":
                result = read_file_with_context(
                    self.project_dir + "/" + args["path"],
                    int(args["start_line_one_indexed"]),
                    args.get("end_line_one_indexed_inclusive"),
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
