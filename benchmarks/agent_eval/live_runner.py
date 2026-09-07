"""Live autonomous-agent benchmark: unlike `runner.py` (which pre-builds context once
per condition and makes a single LLM call), this spawns the *actual* MCP agent loop
from `graphcode.mcp.client.GraphCodeAgent` — the same tool-calling loop, same Groq
rate-limit/retry handling used interactively — and lets it decide for itself which
tools to call and how many times, against two real MCP servers:

  - graph:    graphcode.mcp.server — blast radius, call chain, semantic search,
              structural context compilation, read_file.
  - baseline: benchmarks.agent_eval.baseline_server — list_files, read_file, grep
              only. This is what a typical "open files + text search" coding agent
              has today, with no structural understanding of the codebase.

Same task set as `runner.py` (`tasks.py`), same pass/fail grading (a subprocess check
script that doesn't care how the fix was made). What's measured here that the
context-injection ablation can't: how many tool calls each agent actually needs to
reach a correct answer when it has to explore for itself, not just "given the right
files, can it write the fix."

Usage:
    GROQ_API_KEY=... python -m benchmarks.agent_eval.live_runner
    GROQ_API_KEY=... python -m benchmarks.agent_eval.live_runner --tasks rename_function
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from benchmarks.agent_eval.tasks import TASKS, Task
from graphcode.llm.groq_client import DEFAULT_MODEL, GroqNotConfigured
from graphcode.mcp.client import GraphCodeAgent
from graphcode.patch import parse_file_blocks

RESULTS_JSON = Path(__file__).parent.parent / "results" / "live_agent_eval.json"
RESULTS_MD = Path(__file__).parent.parent / "results" / "live_agent_eval.md"

# The graph agent's own system prompt (imported, not duplicated) assumes graph tools
# exist and budgets 3 calls because graph_compile_context front-loads everything in
# one shot. The baseline has no such shortcut — it must read_file/grep its way to an
# answer — so it gets a larger budget and prompt text that doesn't reference tools it
# doesn't have.
from graphcode.mcp.client import SYSTEM_PROMPT as GRAPH_SYSTEM_PROMPT  # noqa: E402

BASELINE_SYSTEM_PROMPT = (
    "You are a coding agent for a single repository. You have three tools: "
    "list_files(pattern), read_file(path), and grep(pattern) for text search across "
    "the repo. There is no structural graph and no semantic search — grep is the only "
    "way to find callers or usages of a symbol. You have a tool-call budget of at most "
    "8 calls before you must propose the change.\n\n"
    "When you are ready to make the change, respond with ONLY the complete new content "
    "of every file you add or modify, one block per file, in exactly this format and "
    "nothing else:\n\n"
    "<<<FILE path/to/file.py>>>\n"
    "<full new content of that file>\n"
    "<<<END>>>\n\n"
    "Do not include explanations outside the FILE blocks once you are ready to propose "
    "the change."
)

CONDITIONS = {
    "graph": ("graphcode.mcp.server", GRAPH_SYSTEM_PROMPT, 8),
    "baseline_toolagent": ("benchmarks.agent_eval.baseline_server", BASELINE_SYSTEM_PROMPT, 10),
}


def _write_repo(task: Task, root: Path) -> None:
    for rel, content in task.files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)


async def _run_one(task: Task, condition: str, model: str) -> dict:
    server_module, system_prompt, max_rounds = CONDITIONS[condition]
    root = Path(tempfile.mkdtemp(prefix=f"gc_live_{task.id}_{condition}_"))
    _write_repo(task, root)

    # IndexService hydrates from settings.rocksdb_path unconditionally on startup
    # (graphcode/indexer.py::_hydrate) — the default path already has persisted
    # snapshots from every real repo indexed this session (retrieval-ranking-engine,
    # click, typer, cli, ...), which would silently merge into this task's tiny
    # synthetic repo and pollute blast_radius/semantic_search results (confirmed live:
    # a 4-file task repo reported 657 modules / 5445 functions before this fix). Give
    # each run its own empty RocksDB dir via env so the subprocess starts genuinely
    # clean, matching the isolation `runner.py`'s in-process IndexService(rocks_path=...)
    # already has.
    rocks_dir = Path(tempfile.mkdtemp(prefix=f"gc_live_rocks_{task.id}_{condition}_"))
    env = dict(os.environ)
    env["ROCKSDB_PATH"] = str(rocks_dir)
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", server_module],
        env=env,
    )
    t0 = time.time()
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                agent = GraphCodeAgent(
                    session,
                    root,
                    model=model,
                    system_prompt=system_prompt,
                    index_on_setup=True,
                )
                await agent.setup()
                response = await agent.run_turn(task.prompt, max_rounds=max_rounds, verbose=False)
    except GroqNotConfigured as exc:
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(rocks_dir, ignore_errors=True)
        return {"task": task.id, "condition": condition, "error": str(exc)}
    latency_s = time.time() - t0

    tool_calls = [m for m in agent.messages if m.get("role") == "tool"]
    tool_call_names: list[str] = []
    for m in agent.messages:
        for call in (m.get("tool_calls") or []):
            tool_call_names.append(call["function"]["name"])

    changed: list[str] = []
    for path, content in parse_file_blocks(response):
        if path not in task.files:
            continue
        target = root / path
        target.write_text(content.strip("\n") + "\n")
        changed.append(path)
    passed, detail = task.run_check(root)
    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(rocks_dir, ignore_errors=True)

    return {
        "task": task.id,
        "condition": condition,
        "passed": passed,
        "detail": detail[:300],
        "tool_call_count": len(tool_calls),
        "tool_calls": tool_call_names,
        "changed_files": changed,
        "latency_s": round(latency_s, 2),
    }


async def run_all(model: str, tasks: list[Task]) -> list[dict]:
    results = []
    for task in tasks:
        for condition in CONDITIONS:
            print(f"[{task.id} / {condition}] running...")
            result = await _run_one(task, condition, model)
            status = "PASS" if result.get("passed") else result.get("error", "FAIL")
            print(f"[{task.id} / {condition}] {status} "
                  f"({result.get('tool_call_count', '?')} tool calls, "
                  f"{result.get('latency_s', '?')}s)")
            results.append(result)
    return results


def render_markdown(results: list[dict]) -> str:
    by_condition: dict[str, list[dict]] = {}
    for r in results:
        by_condition.setdefault(r["condition"], []).append(r)

    lines = ["# Live autonomous-agent benchmark (real tool-calling, not pre-built context)", ""]
    lines.append("| Condition | Pass rate | Avg tool calls | Avg latency (s) |")
    lines.append("|---|---|---|---|")
    for cond, rows in by_condition.items():
        passed = sum(1 for r in rows if r.get("passed"))
        valid = [r for r in rows if "tool_call_count" in r]
        avg_calls = sum(r["tool_call_count"] for r in valid) / len(valid) if valid else 0
        avg_latency = sum(r["latency_s"] for r in valid) / len(valid) if valid else 0
        lines.append(
            f"| {cond} | {passed}/{len(rows)} ({passed / len(rows):.0%}) | "
            f"{avg_calls:.1f} | {avg_latency:.1f} |"
        )
    lines.append("")
    lines.append("## Per-task detail")
    lines.append("| Task | " + " | ".join(f"{c} (pass/calls)" for c in by_condition) + " |")
    lines.append("|---|" + "---|" * len(by_condition))
    task_ids = [r["task"] for r in by_condition[next(iter(by_condition))]]
    for tid in task_ids:
        row = [tid]
        for cond in by_condition:
            match = next((r for r in by_condition[cond] if r["task"] == tid), None)
            if match is None:
                row.append("?")
            elif "error" in match:
                row.append(f"ERROR: {match['error'][:40]}")
            else:
                mark = "PASS" if match.get("passed") else "FAIL"
                row.append(f"{mark} / {match.get('tool_call_count', '?')}")
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--tasks", default="", help="comma-separated task ids, default all")
    args = ap.parse_args()

    tasks = TASKS
    if args.tasks:
        wanted = set(args.tasks.split(","))
        tasks = [t for t in TASKS if t.id in wanted]

    results = asyncio.run(run_all(args.model, tasks))

    RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_JSON.write_text(json.dumps(results, indent=2))
    report = render_markdown(results)
    RESULTS_MD.write_text(report)
    print(report)


if __name__ == "__main__":
    main()
