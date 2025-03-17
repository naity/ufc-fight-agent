import anthropic
import json
from dataclasses import asdict


class Agent:
    def __init__(
        self,
        model="claude-3-7-sonnet-20250219",
        tools=[],
        verbose=True,
    ):
        self.client = anthropic.Anthropic()
        self.model = model
        self.tools = {}
        self.verbose = verbose

        for tool in tools:
            self.tools[tool.name] = tool

        # Format tools for Claude API
        self.claude_tools = [tool.to_claude_format() for tool in self.tools.values()]
        self.messages = []

    def _log(self, title, content):
        if not self.verbose:
            return

        # Fixed width for Jupyter notebook display
        width = 80

        # Format the title with padding
        title_str = f"{'=' * 10} {title} {'=' * (width - len(title) - 12)}"
        print(f"{title_str}")

        # Format the content based on type
        if isinstance(content, dict) or isinstance(content, list):
            try:
                print(json.dumps(content, indent=2))
            except:
                print(str(content))
        elif hasattr(content, "__dict__"):
            try:
                print(json.dumps(asdict(content), indent=2))
            except:
                print(str(content))
        else:
            print(str(content))

        print(f"{'=' * width}\n")

    def run(self, query, thinking_mode=False):
        self._log("USER QUERY", query)
        self.messages.append({"role": "user", "content": query})

        thinking_config = self._get_thinking_config(thinking_mode)
        self._log("THINKING MODE", "Enabled" if thinking_mode else "Disabled")

        # step1: tool use
        self._log("STEP 1", "Determining Tool Usage")
        tool_use_response = self._tool_use(thinking_config)

        if tool_use_response["thinking_block"] is not None:
            self._log("THINKING PROCESS", tool_use_response["thinking_block"].thinking)

        if tool_use_response["tool_use_block"] is None:
            # no tool was selected
            final_response = tool_use_response["text_block"].text
            self._log("FINAL RESPONSE (NO TOOL USED)", final_response)
            return final_response

        self._log("TOOL SELECTED", f"Using {tool_use_response['tool_use_block'].name}")

        # must pass thinking and redacted_thinking blocks back to the API
        self.messages.append(
            {
                "role": "assistant",
                "content": (
                    [
                        tool_use_response["thinking_block"],
                        tool_use_response["tool_use_block"],
                    ]
                    if tool_use_response["thinking_block"]
                    else [tool_use_response["tool_use_block"]]
                ),
            }
        )

        # step2: execute tool
        self._log("STEP 2", "Executing Tool")
        tool_result = self._execute_tool(tool_use_response["tool_use_block"])

        # Log a preview of the tool result (truncated if very large)
        result_preview = str(tool_result)
        if len(result_preview) > 500:
            result_preview = result_preview[:500] + "... [truncated]"
        self._log("TOOL EXECUTION RESULT (PREVIEW)", result_preview)

        self.messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_response["tool_use_block"].id,
                        "content": tool_result,
                    }
                ],
            },
        )

        # step3: final response
        self._log("STEP 3", "Generating Final Response")
        final_response = self._final_response(thinking_config)
        self._log("FINAL RESPONSE", final_response)
        return final_response

    def _get_thinking_config(self, thinking_mode):
        if thinking_mode:
            thinking_config = {"type": "enabled", "budget_tokens": 16000}
        else:
            thinking_config = {"type": "disabled"}
        return thinking_config

    def _tool_use(self, thinking_config):
        system_msg = """
        Your task is to determine what UFC fight data to retrieve. Analyze user's query to choose appropriate parameters for the get_upcoming_matchups tool. Consider increasing max_events (up to 10) if you need to look beyond the next event (e.g., when user asks for title fights or specific fighters that may not appear in the immediate event).
        """

        response = self.client.messages.create(
            model=self.model,
            max_tokens=20000,
            thinking=thinking_config,
            tools=self.claude_tools,
            system=system_msg,
            messages=self.messages,
        )

        thinking_block = next(
            (block for block in response.content if block.type == "thinking"),
            None,
        )

        text_block = next(
            (block for block in response.content if block.type == "text"),
            None,
        )

        tool_use_block = next(
            (block for block in response.content if block.type == "tool_use"),
            None,
        )

        return {
            "thinking_block": thinking_block,
            "tool_use_block": tool_use_block,
            "text_block": text_block,
        }

    def _execute_tool(self, tool_use_block):
        """
        Execute the requested tool
        """
        tool_name = tool_use_block.name
        tool_input = tool_use_block.input

        self._log("EXECUTING TOOL", {"name": tool_name, "input": tool_input})

        if tool_name not in self.tools:
            return f"Error: Tool {tool_name} not found"

        try:
            result = self.tools[tool_name](**tool_input)

            # convert to JSON
            result = [asdict(event) for event in result]
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    def _final_response(self, thinking_config):
        """
        Generate the final response
        """
        system_msg = """
        Provide insightful fight recommendations based on the user's request and the UFC data. If no data is available, acknowledge to the user. Keep your analysis concise but informative and engaging.
        """

        response = self.client.messages.create(
            model=self.model,
            max_tokens=20000,
            thinking=thinking_config,
            tools=self.claude_tools,
            system=system_msg,
            messages=self.messages,
        )

        final_text = response.content[-1].text

        # Add the assistant's response to the conversation history
        self.messages.append({"role": "assistant", "content": final_text})

        return final_text
