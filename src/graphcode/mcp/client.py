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

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from graphcode.llm.groq_client import GroqNotConfigured, chat_with_tools
from graphcode.patch import parse_file_blocks, unified_diff

SYSTEM_PROMPT = (
    "You are a coding agent for a single repository, working through MCP tools that "
    "query a structural code graph (functions, classes, imports, calls) built with "
    "Tree-sitter. The repository is already indexed.\n\n"
    "You have a strict tool-call budget — at most 3 tool calls total before you must "
    "propose the change. Prefer graph_compile_context or graph_get_context first: they "
    "return blast-radius, call chains, AND relevant source in one call, which is almost "
    "always enough. Only call graph_read_file for a file you're about to edit and "
    "haven't seen exact content for yet. Do not call graph_semantic_search, "
    "graph_call_chain, graph_blast_radius, and graph_read_file all separately for the "
    "same symbol — that wastes your budget on redundant context.\n\n"
    "When you are ready to make the change (by your 3rd tool call at the latest), "
    "respond with ONLY the complete new content of every file you add or modify, one "
    "block per file, in exactly this format and nothing else:\n\n"
    "<<<FILE path/to/file.py>>>\n"
    "<full new content of that file>\n"
    "<<<END>>>\n\n"
    "Do not include explanations outside the FILE blocks once you are ready to propose "
    "the change."
)


class GraphCodeAgent:
    """Wraps an already-open MCP ClientSession plus a Groq tool-calling loop.

    `system_prompt` and `index_on_setup` are overridable (default: the interactive
    graph-tool CLI's own prompt and behavior, unchanged) so the same tool-loop and
    Groq-quirk recovery logic can drive a differently-tooled agent for benchmarking —
    see `benchmarks/agent_eval/live_runner.py`, which points this at a `read_file`
    + `grep`-only MCP server with no graph tools at all, as the comparison baseline."""

    def __init__(
        self,
        session: ClientSession,
        repo_path: Path,
        model: str | None = None,
        system_prompt: str = SYSTEM_PROMPT,
        index_on_setup: bool = True,
    ) -> None:
        self.session = session
        self.repo_path = repo_path.resolve()
        self.model = model
        self.index_on_setup = index_on_setup
        self.tools: list[dict] = []
        self.messages: list[dict] = [{"role": "system", "content": system_prompt}]

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
        print(f"Connected. {len(self.tools)} tools available.")
        if self.index_on_setup:
            print(f"Indexing {self.repo_path} ...")
            result = await self._call_tool("graph_index_repo", {"path": str(self.repo_path)})
            print(result)

    async def _call_tool(self, name: str, arguments: dict) -> str:
        result = await self.session.call_tool(name, arguments=arguments)
        text = "".join(b.text for b in result.content if getattr(b, "type", None) == "text")
        if result.isError:
            return f"error calling {name}: {text}"
        # Groq's free tier caps at 8000 tokens *per request* (confirmed live: an
        # accumulated conversation with a couple of tool results hit 9903 and got
        # rejected with 413) — cap individual tool results so a single graph_read_file
        # on a large file or a wide semantic_search can't blow the whole budget by itself.
        limit = 3000
        if len(text) > limit:
            text = text[:limit] + f"\n...[truncated, {len(text) - limit} more characters]"
        return text

    async def _chat_with_recovery(self, prompt: str, valid_names: set[str], verbose: bool, max_attempts: int = 5) -> dict:
        """Wraps chat_with_tools with recovery for three things confirmed live against
        Groq's free tier, none of which should crash the whole CLI session:

        1. 400 "tool X not in request.tools" — the model hallucinated a tool name
           (seen: "graph_search" instead of "graph_semantic_search"). No assistant
           message comes back at all in this case, so there's nothing to inspect
           client-side; tell it the valid names and retry.
        2. 413 "request too large" — this one request's own size exceeds the limit.
           Messages can't be trimmed piecemeal (the API also validates that every
           "tool" message immediately follows the assistant message that requested
           it, so removing one side of a pair just trades one 400 for another), so
           reset to system + the original prompt: guaranteed valid, guaranteed to
           fit, at the cost of this turn's accumulated tool-call context.
        3. 429 "rate limit reached ... tokens per minute" — a *rolling* per-minute
           budget, confirmed by the same request succeeding moments later once usage
           drained. Resetting context doesn't help here (the server-side counter
           doesn't care how big your next request is); a short wait does.

        Kept separate from run_turn's tool-calling round loop so these transient
        retries don't eat into max_rounds, which is meant to bound actual progress."""
        kwargs: dict = {"tools": self.tools}
        if self.model:
            kwargs["model"] = self.model
        for attempt in range(max_attempts):
            try:
                message, _usage = chat_with_tools(self.messages, **kwargs)
                return message
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code if exc.response is not None else None
                body = exc.response.text if exc.response is not None else str(exc)
                if status == 400 and "not in request.tools" in body:
                    if verbose:
                        print(f"  [warning] invalid tool name, retrying: {body[:200]}")
                    self.messages.append(
                        {
                            "role": "user",
                            "content": (
                                "That tool call failed: you used a tool name that doesn't exist. "
                                f"Valid tool names are exactly: {sorted(valid_names)}. Try again."
                            ),
                        }
                    )
                    continue
                if status == 413 and len(self.messages) > 2:
                    if verbose:
                        print(f"  [warning] request too large, resetting turn context: {body[:200]}")
                    self.messages[:] = [self.messages[0], {"role": "user", "content": prompt}]
                    continue
                if status == 429:
                    wait_s = 10 * (attempt + 1)
                    if verbose:
                        print(f"  [warning] rate limited, waiting {wait_s}s: {body[:200]}")
                    await asyncio.sleep(wait_s)
                    continue
                raise
        raise RuntimeError("Groq API kept failing (invalid tool calls / rate limits) after repeated retries.")

    async def run_turn(self, prompt: str, max_rounds: int = 8, verbose: bool = True) -> str:
        self.messages.append({"role": "user", "content": prompt})
        valid_names = {t["function"]["name"] for t in self.tools}
        for _ in range(max_rounds):
            message = await self._chat_with_recovery(prompt, valid_names, verbose)
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
                if name not in valid_names:
                    result_text = f"error: no such tool '{name}'. Valid tools: {sorted(valid_names)}"
                else:
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
            try:
                answer = input(f"Apply changes to {path}? [y/N] ").strip().lower()
            except EOFError:
                answer = "n"
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
