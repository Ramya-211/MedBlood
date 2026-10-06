"""
fake_llm.py (test helper)

A scripted LLMProvider implementing the SAME interface as OpenAIToolCallingProvider, used to
prove the LLM-tool-calling pathway in orchestrator.py actually works end-to-end: tool selection,
argument passing, tool execution, and a second call to phrase the final answer from the tool
result. This is not a mock of the chatbot's intelligence -- it is a stand-in for the network call
only, so the tool-routing/execution/response-assembly code genuinely runs.

Per the project's own instructions: "If the external LLM API cannot be called during CI, isolate
the provider behind an interface and test the complete tool-routing/data layer independently."
This is exactly that isolation point.
"""

from app.llm.provider import LLMProvider, LLMResult, ToolCall


class FakeToolCallingProvider(LLMProvider):
    def __init__(self, tool_name: str, tool_args: dict, final_text: str = None):
        self.tool_name = tool_name
        self.tool_args = tool_args
        self.final_text = final_text
        self.calls = []  # records every .chat() invocation for assertions

    def available(self) -> bool:
        return True

    def chat(self, messages: list, tools: list) -> LLMResult:
        self.calls.append({"messages": messages, "n_tools_offered": len(tools)})
        if len(self.calls) == 1:
            return LLMResult(tool_calls=[ToolCall(id="call_1", name=self.tool_name, arguments=self.tool_args)])
        # Second call: the "model" phrases the final answer. If no script was given, prove it
        # actually received the tool's real JSON result by echoing a fact from it.
        tool_message = next(m for m in messages if m.get("role") == "tool")
        return LLMResult(text=self.final_text or f"(from tool result) {tool_message['content'][:120]}")
