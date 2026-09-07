"""Real subprocess tests for `graphcode query ...` — the exact integration boundary
the VS Code extension shells out across (vscode-extension/src/extension.ts). Testing
via real subprocess + real JSON parsing, not calling cli.py's internals directly,
because a field-name mismatch between what queries/*.py returns and what a JSON
consumer expects is precisely the kind of bug that only shows up at that boundary.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent / "fixtures" / "mini_repo"


def _run(args: list[str], rocks_dir: Path) -> dict:
    env = {**os.environ, "ROCKSDB_PATH": str(rocks_dir)}
    proc = subprocess.run(
        [sys.executable, "-m", "graphcode.cli", *args],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    return json.loads(proc.stdout)


def test_cli_query_blast_radius_matches_extension_field_expectations(tmp_path):
    rocks = tmp_path / "rocks"
    _run(["index", str(ROOT)], rocks)
    result = _run(["query", "blast-radius", "parse_config", "--direction", "upstream"], rocks)

    assert "qualified_name" in result["origin"]
    non_origin = [n for n in result["nodes"] if n["id"] != result["origin"]["id"]]
    assert non_origin
    for n in non_origin:
        # exactly the fields vscode-extension/src/extension.ts::nodeQuickPickItem and
        # openAtLine read off each node
        assert "path" in n and "via" in n and "hop" in n


def test_cli_query_semantic_matches_extension_field_expectations(tmp_path):
    rocks = tmp_path / "rocks"
    _run(["index", str(ROOT)], rocks)
    result = _run(["query", "semantic", "parse a config file", "--k", "3"], rocks)

    assert result["hits"]
    for h in result["hits"]:
        assert "path" in h and "score" in h and "qualified_name" in h


def test_cli_query_shortest_path_matches_extension_field_expectations(tmp_path):
    rocks = tmp_path / "rocks"
    _run(["index", str(ROOT)], rocks)
    result = _run(["query", "shortest-path", "ApiController", "parse_config"], rocks)

    assert len(result["path"]) >= 2
    # step 0 is the origin (no "via"); every later step carries the edge type used to
    # reach it — exactly what extension.ts's shortestPath() renders as "→ via →"
    assert "via" not in result["path"][0] or result["path"][0]["via"] is None
    assert all("via" in step for step in result["path"][1:])


def test_cli_query_persists_across_separate_process_invocations(tmp_path):
    """The whole point of the stateless-per-call design (cli.py's own comment on the
    query subcommand): index once, then query in a *separate* process, relying purely
    on the durable RocksDB snapshot being rehydrated — no daemon, no shared memory."""
    rocks = tmp_path / "rocks"
    _run(["index", str(ROOT)], rocks)
    result = _run(["query", "blast-radius", "parse_config"], rocks)
    assert result["origin"]["qualified_name"] == "src.utils.parse_config"
