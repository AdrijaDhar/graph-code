from __future__ import annotations

import shutil
import time
from pathlib import Path

from graphcode.indexer import IndexService

FIXTURE = Path(__file__).parent / "fixtures" / "mini_repo"


def _fresh_repo(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(FIXTURE, dest)
    return dest


def test_single_file_reindex_preserves_own_cross_file_edges(tmp_path):
    """Regression test for a real bug found while building this: a naive single-file
    reindex batch has no visibility into other modules, so IMPORTS/CALLS edges from
    the reindexed file used to silently vanish on every save, even with nothing about
    the relationship actually changing."""
    root = _fresh_repo(tmp_path)
    svc = IndexService(rocks_path=tmp_path / "rocks", snapshot_debounce_s=0.05)
    svc.index_repo(root, parallel=False)

    fn_id = next(
        nid for nid, n in svc.memory.nodes.items() if n.props.get("qualified_name", "").endswith("ApiController.handle_request")
    )
    assert any(e.type == "CALLS" for e in svc.memory.out.get(fn_id, []))

    p = root / "src/api/controller.py"
    p.write_text(p.read_text() + "\n# harmless comment to force a real reparse\n")
    result = svc.reindex_file(root, "src/api/controller.py")

    assert result["reindexed"] == "src/api/controller.py"
    calls = [e for e in svc.memory.out.get(fn_id, []) if e.type == "CALLS"]
    assert len(calls) == 1
    assert calls[0].to_id.endswith("src.utils.parse_config")


def test_ripple_updates_caller_metadata_without_touching_caller_file(tmp_path):
    """A change to the callee's line numbers (no rename) should ripple to the
    caller's edge automatically, since reindex_file detects and re-resolves direct
    CALLS neighbors — without the watcher ever touching the caller file."""
    root = _fresh_repo(tmp_path)
    svc = IndexService(rocks_path=tmp_path / "rocks", snapshot_debounce_s=0.05)
    svc.index_repo(root, parallel=False)

    utils_path = root / "src/utils.py"
    content = utils_path.read_text()
    utils_path.write_text(content.replace("def parse_config(", "\n\ndef parse_config("))

    result = svc.reindex_file(root, "src/utils.py")
    assert "src/api/controller.py" in result["rippled"]

    fn_id = next(
        nid for nid, n in svc.memory.nodes.items() if n.props.get("qualified_name", "").endswith("ApiController.handle_request")
    )
    calls = [e for e in svc.memory.out.get(fn_id, []) if e.type == "CALLS"]
    assert len(calls) == 1
    target = svc.memory.nodes[calls[0].to_id]
    assert target.props["qualified_name"].endswith("parse_config")
    assert target.props["start_line"] > 4  # shifted down by the inserted blank lines


def test_rename_without_updating_caller_correctly_breaks_the_call(tmp_path):
    """The flip side: if the callee is renamed and the caller's source genuinely still
    references the old name, that call really is broken — the graph should reflect
    that (edge dropped / unresolved), not silently keep pointing at a name-mismatched
    target."""
    root = _fresh_repo(tmp_path)
    svc = IndexService(rocks_path=tmp_path / "rocks", snapshot_debounce_s=0.05)
    svc.index_repo(root, parallel=False)

    utils_path = root / "src/utils.py"
    utils_path.write_text(utils_path.read_text().replace("def parse_config(", "def parse_config_v2("))
    svc.reindex_file(root, "src/utils.py")

    fn_id = next(
        nid for nid, n in svc.memory.nodes.items() if n.props.get("qualified_name", "").endswith("ApiController.handle_request")
    )
    calls = [e for e in svc.memory.out.get(fn_id, []) if e.type == "CALLS"]
    assert calls == []


def test_rename_then_reindexing_updated_caller_resolves_correctly(tmp_path):
    """If the caller's own source is updated too (and its own reindex_file runs, as
    the watcher would trigger on that save), the edge correctly re-resolves to the
    renamed target."""
    root = _fresh_repo(tmp_path)
    svc = IndexService(rocks_path=tmp_path / "rocks", snapshot_debounce_s=0.05)
    svc.index_repo(root, parallel=False)

    utils_path = root / "src/utils.py"
    utils_path.write_text(utils_path.read_text().replace("def parse_config(", "def parse_config_v2("))
    svc.reindex_file(root, "src/utils.py")

    ctrl_path = root / "src/api/controller.py"
    ctrl_path.write_text(ctrl_path.read_text().replace("parse_config(payload)", "parse_config_v2(payload)").replace(
        "import parse_config", "import parse_config_v2"
    ))
    svc.reindex_file(root, "src/api/controller.py")

    fn_id = next(
        nid for nid, n in svc.memory.nodes.items() if n.props.get("qualified_name", "").endswith("ApiController.handle_request")
    )
    calls = [e for e in svc.memory.out.get(fn_id, []) if e.type == "CALLS"]
    assert len(calls) == 1
    assert svc.memory.nodes[calls[0].to_id].props["qualified_name"].endswith("parse_config_v2")


def test_delete_module_still_works_and_schedules_snapshot(tmp_path):
    root = _fresh_repo(tmp_path)
    svc = IndexService(rocks_path=tmp_path / "rocks", snapshot_debounce_s=0.05)
    svc.index_repo(root, parallel=False)

    (root / "src/utils.py").unlink()
    result = svc.reindex_file(root, "src/utils.py")
    assert result == {"deleted": "src/utils.py"}
    assert not any(n.props.get("path") == "src/utils.py" for n in svc.memory.nodes.values())


def test_snapshot_writes_are_debounced_across_bursts(tmp_path):
    root = _fresh_repo(tmp_path)
    svc = IndexService(rocks_path=tmp_path / "rocks", snapshot_debounce_s=0.3)
    svc.index_repo(root, parallel=False)
    svc.flush_snapshot()  # clear the one from index_repo's own initial state if pending

    call_count = {"n": 0}
    orig_save = svc.rocks.save_snapshot

    def counting_save(*a, **kw):
        call_count["n"] += 1
        return orig_save(*a, **kw)

    svc.rocks.save_snapshot = counting_save

    for i in range(5):
        p = root / "src/utils.py"
        p.write_text(p.read_text() + f"\n# burst edit {i}\n")
        svc.reindex_file(root, "src/utils.py")

    assert call_count["n"] == 0, "snapshot should not have fired yet, still debounced"
    time.sleep(0.5)
    assert call_count["n"] == 1, "exactly one coalesced snapshot write after the debounce window"


def test_flush_snapshot_is_a_safe_noop_with_nothing_pending(tmp_path):
    svc = IndexService(rocks_path=tmp_path / "rocks", snapshot_debounce_s=5.0)
    svc.flush_snapshot()  # must not raise
