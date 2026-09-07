from __future__ import annotations

import argparse
import json
from pathlib import Path

from graphcode.indexer import get_index_service
from graphcode.watcher.daemon import get_watch


def main() -> None:
    p = argparse.ArgumentParser(prog="graphcode")
    sub = p.add_subparsers(dest="cmd", required=True)
    idx = sub.add_parser("index")
    idx.add_argument("path")
    st = sub.add_parser("status")
    w = sub.add_parser("watch")
    w.add_argument("path")
    chat = sub.add_parser("chat", help="interactive MCP-backed coding agent for a repo")
    chat.add_argument("path")
    chat.add_argument("--model", default=None)
    sub.add_parser(
        "mcp-server",
        help="run the graph-code MCP server on stdio, for an external MCP host "
        "(Claude Desktop, Claude Code, Cursor) to spawn directly",
    )
    pr = sub.add_parser(
        "pr-comment",
        help="blast-radius report for symbols changed between two git refs — "
        "prints a markdown comment, optionally posts it to a GitHub PR",
    )
    pr.add_argument("--repo", default=".", help="repo root, default: current directory")
    pr.add_argument("--base", required=True, help="base ref, e.g. origin/main")
    pr.add_argument("--head", default="HEAD", help="head ref, default: HEAD")
    pr.add_argument("--direction", default="upstream", choices=["upstream", "downstream", "both"])
    pr.add_argument(
        "--post",
        action="store_true",
        help="also post as a PR comment via the GitHub API — needs GITHUB_TOKEN, "
        "GITHUB_REPOSITORY (owner/repo), and PR_NUMBER in the environment",
    )

    # One-shot, JSON-out query commands — stateless per invocation (no daemon), safe
    # because the graph they read is durable: `graphcode index` persists a RocksDB
    # snapshot that the *next* process's IndexService rehydrates automatically on
    # startup (see indexer.py::_hydrate). Built for scriptable/editor-integration use
    # (the VS Code extension shells out to exactly these) where a long-lived MCP
    # session per query would be unnecessary process-management overhead.
    query = sub.add_parser("query", help="one-shot JSON queries against the last-indexed repo")
    qsub = query.add_subparsers(dest="qcmd", required=True)

    qb = qsub.add_parser("blast-radius")
    qb.add_argument("symbol")
    qb.add_argument("--direction", default="upstream", choices=["upstream", "downstream", "both"])

    qp = qsub.add_parser("shortest-path")
    qp.add_argument("from_symbol")
    qp.add_argument("to_symbol")

    qs = qsub.add_parser("semantic")
    qs.add_argument("text")
    qs.add_argument("--k", type=int, default=8)

    qc = qsub.add_parser("call-chain")
    qc.add_argument("symbol")

    qsrc = qsub.add_parser("source")
    qsrc.add_argument("path")
    qsrc.add_argument("--start", type=int, default=1)
    qsrc.add_argument("--end", type=int, default=60)

    args = p.parse_args()

    if args.cmd == "chat":
        import asyncio

        from graphcode.mcp.client import main as chat_main

        asyncio.run(chat_main(args.path, model=args.model))
        return

    if args.cmd == "mcp-server":
        from graphcode.mcp.server import main as server_main

        server_main()
        return

    if args.cmd == "pr-comment":
        import os

        from graphcode.pr_bot import build_comment, changed_line_ranges, changed_symbols, post_github_comment

        root = Path(args.repo).resolve()
        svc = get_index_service()
        svc.index_repo(root)
        ranges = changed_line_ranges(root, args.base, args.head)
        changed = changed_symbols(svc, ranges)
        comment = build_comment(svc, changed, direction=args.direction)
        print(comment or "(no changed symbols found in the diff)")
        if args.post and comment:
            post_github_comment(
                os.environ["GITHUB_REPOSITORY"],
                int(os.environ["PR_NUMBER"]),
                comment,
                os.environ["GITHUB_TOKEN"],
            )
        return

    if args.cmd == "query":
        from graphcode.context.compiler import slice_source
        from graphcode.queries.call_chain import call_chain
        from graphcode.queries.hybrid import semantic_search
        from graphcode.queries.paths import blast_radius, shortest_path

        svc = get_index_service()
        root = (svc.last_index or {}).get("root")
        if args.qcmd == "blast-radius":
            print(json.dumps(blast_radius(svc.memory, args.symbol, direction=args.direction, org_id="local"), indent=2))
        elif args.qcmd == "shortest-path":
            print(json.dumps(shortest_path(svc.memory, args.from_symbol, args.to_symbol, org_id="local"), indent=2))
        elif args.qcmd == "semantic":
            print(json.dumps(semantic_search(svc, args.text, k=args.k, org_id="local"), indent=2))
        elif args.qcmd == "call-chain":
            print(json.dumps(call_chain(svc.memory, args.symbol, org_id="local"), indent=2))
        elif args.qcmd == "source":
            if not root:
                print(json.dumps({"error": "no repo indexed yet"}))
                return
            text = slice_source(Path(root), args.path, args.start, args.end, budget_lines=max(1, args.end - args.start + 1))
            print(json.dumps({"path": args.path, "start": args.start, "end": args.end, "text": text}, indent=2))
        return

    svc = get_index_service()
    if args.cmd == "index":
        print(json.dumps(svc.index_repo(Path(args.path)), indent=2))
    elif args.cmd == "status":
        print(json.dumps(svc.last_index or {"error": "not indexed"}, indent=2))
    elif args.cmd == "watch":
        print(json.dumps(get_watch().start(args.path, svc), indent=2))
        try:
            import time

            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            get_watch().stop()


if __name__ == "__main__":
    main()
