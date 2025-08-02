from google.genai import types, Client

from config import GEMINI_API_KEY, DEFAULT_COLLECTION_NAME
from agent_tools.grep import search_codebase
from agent_tools.file_list import ls
from agent_tools.read_file import read_file, scroll_up, scroll_down
from rag.embeddings import EmbeddingManager
from rag.reranker import rerank_results
from rag.snippet_reader import read_snippets


class ChatAgent:
    def __init__(
        self,
        project_dir: str = ".",
        collection_name: str = DEFAULT_COLLECTION_NAME,
        gemini_api_key: str = GEMINI_API_KEY,
        model: str = "gemini-2.5-pro",
        max_iterations: int = 15,
    ):
        self.messages: list[str] = []
        self.max_iterations: int = max_iterations
        self.gemini: Client = Client(api_key=gemini_api_key)
        self.model: str = model
        self.project_dir = project_dir

        self.system_prompt = (
            "You are an expert developer for answering questions using a Python codebase as a context.\n"
            "Here is the root folder list of files and directories:\n"
            f"{ls()}\n\n"
            "You have these tools available, you can call them as many times as you need:\n"
            "  • query_vector_db(question: str)\n"
            "  • grep_search(query: str)\n"
            "  • read_file(path: str, start_line: int, end_line: int)\n"
            "  • ls(path: str)\n"
            "  • scroll_up(path: str, start_line: int)\n"
            "  • scroll_down(path: str, end_line: int)\n"
            "\nWhen you need to call a tool, respond exactly with:\n"
            'TOOL: <tool_name>("<argument without name>")\n'
            "Be careful to not add any extra text before or after the tool call.\n"
            "For example:\n"
            'TOOL: query_vector_db("UserSerializer")'
            'TOOL: read_file("./relative/path/to/file.py", 12, 93)\n'
            "The agent will run the tool, append the result, and prompt you again.\n"
            "When using read_file: you can not read more than 100 lines at once (end_line - start_line <= 100).\n"
            "When using query_vector_db it returns code chunks but they may be not full (half of class or function) so you may need to read the next lines with other tools.\n"
            "If you dont need extra context, or you have already got all the information you need, return your final answer in plain text (no TOOL: prefix)."
            "In your final answer cite code snippets from the codebase and add links to the codebase (grep format). Never ever make up code snippets.\n"
        )
        self.embedding_manager = EmbeddingManager(collection_name=collection_name)

    def run(self, user_question: str) -> str:
        self.messages.append(f"User input: {user_question}")
        iterations: int = 0

        while True:
            response: types.GenerateContentResponse = (
                self.gemini.models.generate_content(
                    model=self.model,
                    contents=self.messages,
                    config=types.GenerateContentConfig(
                        system_instruction=self.system_prompt,
                    ),
                )
            )
            response_text: str = response.text
            print(f"ASSISTANT_OUTPUT: {response_text}")
            self.messages.append(f"Assistant input: {response_text}")

            # Check for tool invocation
            if response_text.strip().splitlines()[-1].strip().startswith("TOOL:"):
                self.call_tool(response_text)
                iterations += 1
                if iterations > self.max_iterations:
                    self.messages.append(
                        "Error: too many iterations, answer with what you have so far"
                    )
                    return self.gemini.models.generate_content(
                        model=self.model,
                        contents=self.messages,
                        config=types.GenerateContentConfig(
                            system_instruction=self.system_prompt,
                        ),
                    ).text
                continue
            # No more TOOL calls → final answer
            break
        return response_text

    def call_tool(self, call_text: str):
        tool_call = call_text.strip().splitlines()[-1].strip()[5:].strip()
        tool_name, args_str = tool_call.split("(", 1)
        args = args_str.rstrip(")").strip().strip("'\"")
        print(f"TOOL_CALL: {tool_name}({args})")
        # Dispatch
        try:
            if tool_name == "query_vector_db":
                result = rerank_results(
                    args,
                    read_snippets(
                        self.embedding_manager.retrieve_vectors_for_question(args, 10),
                        base_dir=self.project_dir,
                    ),
                    max_results=5,
                )
                for record in result:
                    record.pop("id", None)
                    record.pop("distance", None)
            elif tool_name == "grep_search":
                result = search_codebase(args, self.project_dir)
            elif tool_name == "read_file":
                path, start_line, end_line = map(
                    lambda x: x.strip("'\""), args.split(", ")
                )
                result = read_file(
                    self.project_dir + "/" + path,
                    int(start_line),
                    int(end_line),
                    add_line_numbers=True,
                )
            elif tool_name == "ls":
                ls(args)
            elif tool_name == "scroll_up":
                path, start_line = map(lambda x: x.strip("'\""), args.split(", "))
                result = scroll_up(path, int(start_line))
            elif tool_name == "scroll_down":
                path, end_line = map(lambda x: x.strip("'\""), args.split(", "))
                result = scroll_down(path, int(end_line))
            else:
                result = f"Error: unknown tool {tool_name}"
        except Exception as e:
            result = f"Tool call failed with exception: {e}"

        self.messages.append(
            f"Tool call: tool name:{tool_name}({args}) result:\n{result}"
        )
        print("TOOL_RESULT:", str(result)[:100] + "...")
