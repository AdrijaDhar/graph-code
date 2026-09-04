"""Interactive MCP client/agent for graphcode — no third-party IDE required.

Connects to the graphcode MCP server (graphcode/mcp/server.py) over the real MCP
protocol (stdio transport), drives it with a $0 open-weight model on Groq doing real
tool-calling, and proposes code edits as a diff you confirm before anything is
written to disk.

Usage:
    graphcode chat <repo_path>
    GROQ_API_KEY=... python -m graphcode.mcp.client <repo_path>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from graphcode.llm.groq_client import GroqNotConfigured, chat_with_tools
from graphcode.patch import parse_file_blocks, unified_diff

SYSTEM_PROMPT = (
    "You are a coding agent for a single repository, working through MCP tools that "
    "query a structural code graph (functions, classes, imports, calls) built with "
    "Tree-sitter. The repository is already indexed.\n\n"
    "Before proposing any change:\n"
    "- Use graph_blast_radius, graph_shortest_path, graph_call_chain, "
    "graph_compile_context, or graph_semantic_search to understand what a change "
    "affects elsewhere in the repo — callers, importers, subclasses.\n"
    "- Use graph_read_file to get the exact current content of any file before you "
    "edit it. Never guess a file's content.\n\n"
    "When you are ready to make the change, respond with ONLY the complete new content "
    "of every file you add or modify, one block per file, in exactly this format and "
    "nothing else:\n\n"
    "<<<FILE path/to/file.py>>>\n"
    "<full new content of that file>\n"
    "<<<END>>>\n\n"
    "Do not include explanations outside the FILE blocks once you are ready to propose "
    "the change. It's fine to call tools across multiple turns first."
)


class GraphCodeAgent:
    """Wraps an already-open MCP ClientSession plus a Groq tool-calling loop."""

    def __init__(self, session: ClientSession, repo_path: Path, model: str | None = None) -> None:
        self.session = session
        self.repo_path = repo_path.resolve()
        self.model = model
        self.tools: list[dict] = []
        self.messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    async def setup(self) -> None:
        tools_result = await self.session.list_tools()
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description or "",
                    "parameters": t.inputSchema,
                },
            }
            for t in tools_result.tools
        ]
        print(f"Connected. {len(self.tools)} tools available. Indexing {self.repo_path} ...")
        result = await self._call_tool("graph_index_repo", {"path": str(self.repo_path)})
        print(result)

    async def _call_tool(self, name: str, arguments: dict) -> str:
        result = await self.session.call_tool(name, arguments=arguments)
        text = "".join(b.text for b in result.content if getattr(b, "type", None) == "text")
        if result.isError:
            return f"error calling {name}: {text}"
        return text

    async def run_turn(self, prompt: str, max_rounds: int = 8, verbose: bool = True) -> str:
        self.messages.append({"role": "user", "content": prompt})
        for _ in range(max_rounds):
            kwargs: dict = {"tools": self.tools}
            if self.model:
                kwargs["model"] = self.model
            message, _usage = chat_with_tools(self.messages, **kwargs)
            self.messages.append(message)
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                return message.get("content") or ""
            for call in tool_calls:
                name = call["function"]["name"]
                try:
                    args = json.loads(call["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                if verbose:
                    print(f"  [tool] {name}({args})")
                result_text = await self._call_tool(name, args)
                self.messages.append(
                    {"role": "tool", "tool_call_id": call["id"], "content": result_text}
                )
        return "(stopped after max tool-call rounds without a final answer)"

    def apply_response(self, response: str) -> None:
        blocks = parse_file_blocks(response)
        if not blocks:
            print(response)
            return
        for path, new_content in blocks:
            target = self.repo_path / path
            old_content = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
            new_content = new_content.strip("\n") + "\n"
            diff = unified_diff(old_content, new_content, path)
            print(diff or f"(no textual change to {path})")
            answer = input(f"Apply changes to {path}? [y/N] ").strip().lower()
            if answer == "y":
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(new_content)
                print(f"  wrote {path}")
            else:
                print(f"  skipped {path}")


async def main(repo_path: str, model: str | None = None) -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "graphcode.mcp.server"],
        env=dict(os.environ),
    )
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                agent = GraphCodeAgent(session, Path(repo_path), model=model)
                await agent.setup()
                print("Type a prompt, or 'exit' to quit.")
                while True:
                    try:
                        prompt = input("> ").strip()
                    except EOFError:
                        break
                    if not prompt:
                        continue
                    if prompt in ("exit", "quit"):
                        break
                    try:
                        response = await agent.run_turn(prompt)
                    except GroqNotConfigured as exc:
                        print(exc)
                        continue
                    agent.apply_response(response)
    except GroqNotConfigured as exc:
        print(exc)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("repo_path")
    ap.add_argument("--model", default=None)
    args = ap.parse_args()
    asyncio.run(main(args.repo_path, model=args.model))
