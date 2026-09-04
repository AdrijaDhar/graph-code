"""Runs the task set under three context conditions and grades pass/fail.

Conditions:
  - baseline: only the file the user named (simulates today's "few open files" context)
  - graph:    baseline + files found by blast_radius() from the primary file (this repo's
              structural context, matching what graph_compile_context would surface)
  - embed:    baseline + files found by embedding similarity to the prompt text, with
              no graph hops (isolates "does the graph add value beyond semantic search alone")

Usage:
    GROQ_API_KEY=... python -m benchmarks.agent_eval.runner
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import time
from pathlib import Path

from benchmarks.agent_eval.tasks import TASKS, Task
from graphcode.indexer import IndexService
from graphcode.llm.groq_client import DEFAULT_MODEL, GroqNotConfigured, chat
from graphcode.patch import parse_file_blocks
from graphcode.queries.hybrid import semantic_search
from graphcode.queries.paths import blast_radius

RESULTS_JSON = Path(__file__).parent.parent / "results" / "agent_eval.json"
RESULTS_MD = Path(__file__).parent.parent / "results" / "agent_eval.md"

SYSTEM_PROMPT = (
    "You are a careful software engineer making a focused code change. You will be given "
    "the full content of specific files from a repository and a task to perform. "
    "Output ONLY the complete new content of every file you add or modify, one block per "
    "file, in exactly this format and nothing else:\n\n"
    "<<<FILE path/to/file.py>>>\n"
    "<full new content of that file>\n"
    "<<<END>>>\n\n"
    "You may only reference files whose content you were given below — do not invent new "
    "file paths, and do not add commentary outside the FILE blocks."
)


def _write_repo(task: Task, root: Path) -> None:
    for rel, content in task.files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)


def _context_baseline(task: Task, root: Path) -> dict[str, str]:
    return {task.primary_file: task.files[task.primary_file]}


def _context_graph(task: Task, root: Path, max_extra: int = 5) -> dict[str, str]:
    svc = IndexService(rocks_path=Path(tempfile.mkdtemp(prefix="gc_eval_rocks_")))
    svc.index_repo(root, parallel=False)
    br = blast_radius(svc.memory, task.primary_file, direction="both", max_hops=2)
    ctx = dict(_context_baseline(task, root))
    for node in br.get("nodes") or []:
        path = node.get("path")
        if path and path in task.files and path not in ctx:
            ctx[path] = task.files[path]
        if len(ctx) > max_extra + 1:
            break
    return ctx


def _context_embedding(task: Task, root: Path, k: int = 5) -> dict[str, str]:
    svc = IndexService(rocks_path=Path(tempfile.mkdtemp(prefix="gc_eval_rocks_")))
    svc.index_repo(root, parallel=False)
    hits = semantic_search(svc, task.prompt, k=k)
    ctx = dict(_context_baseline(task, root))
    for hit in hits.get("hits") or []:
        path = hit.get("path")
        if path and path in task.files and path not in ctx:
            ctx[path] = task.files[path]
    return ctx


CONDITIONS = {
    "baseline": _context_baseline,
    "graph": _context_graph,
    "embedding": _context_embedding,
}


def _build_messages(task: Task, ctx: dict[str, str]) -> list[dict]:
    file_sections = "\n\n".join(f"--- {path} ---\n{content}" for path, content in ctx.items())
    user = f"{task.prompt}\n\nRepository files you can see:\n\n{file_sections}"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _apply_patch(task: Task, root: Path, response: str) -> list[str]:
    changed = []
    for path, content in parse_file_blocks(response):
        if path not in task.files:
            continue  # ignore hallucinated paths outside the known task repo
        (root / path).write_text(content.strip("\n") + "\n")
        changed.append(path)
    return changed


def run_task_condition(task: Task, condition: str, model: str) -> dict:
    ctx_fn = CONDITIONS[condition]
    src_root = Path(tempfile.mkdtemp(prefix=f"gc_eval_src_{task.id}_"))
    _write_repo(task, src_root)
    ctx = ctx_fn(task, src_root)

    messages = _build_messages(task, ctx)
    t0 = time.time()
    try:
        response, usage = chat(messages, model=model)
    except GroqNotConfigured as exc:
        return {"task": task.id, "condition": condition, "error": str(exc)}
    latency_s = time.time() - t0

    patch_root = Path(tempfile.mkdtemp(prefix=f"gc_eval_patch_{task.id}_"))
    _write_repo(task, patch_root)
    changed = _apply_patch(task, patch_root, response)
    passed, detail = task.run_check(patch_root)

    shutil.rmtree(src_root, ignore_errors=True)
    shutil.rmtree(patch_root, ignore_errors=True)

    return {
        "task": task.id,
        "condition": condition,
        "context_files": list(ctx.keys()),
        "changed_files": changed,
        "passed": passed,
        "detail": detail[:300],
        "latency_s": round(latency_s, 2),
        "usage": usage,
    }


def run_all(model: str, tasks: list[Task]) -> list[dict]:
    results = []
    for task in tasks:
        for condition in CONDITIONS:
            results.append(run_task_condition(task, condition, model))
    return results


def render_markdown(results: list[dict]) -> str:
    by_condition: dict[str, list[dict]] = {}
    for r in results:
        by_condition.setdefault(r["condition"], []).append(r)

    lines = ["# Task-level agent impact benchmark", ""]
    lines.append("| Condition | Pass rate | Tasks passed |")
    lines.append("|---|---|---|")
    for cond, rows in by_condition.items():
        passed = sum(1 for r in rows if r.get("passed"))
        lines.append(f"| {cond} | {passed}/{len(rows)} ({passed / len(rows):.0%}) | "
                      f"{', '.join(r['task'] for r in rows if r.get('passed'))} |")
    lines.append("")
    lines.append("## Per-task detail")
    lines.append("| Task | " + " | ".join(by_condition.keys()) + " |")
    lines.append("|---|" + "---|" * len(by_condition))
    task_ids = [r["task"] for r in by_condition[next(iter(by_condition))]]
    for tid in task_ids:
        row = [tid]
        for cond in by_condition:
            match = next((r for r in by_condition[cond] if r["task"] == tid), None)
            row.append("PASS" if match and match.get("passed") else "FAIL")
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

    results = run_all(args.model, tasks)

    RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_JSON.write_text(json.dumps(results, indent=2))
    report = render_markdown(results)
    RESULTS_MD.write_text(report)
    print(report)


if __name__ == "__main__":
    main()
