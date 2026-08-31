import time
from pathlib import Path

from graphcode.indexer import IndexService
from graphcode.watcher.daemon import WatchDaemon


def test_watcher_reindexes_on_touch(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    f = repo / "a.py"
    f.write_text("def foo():\n    return 1\n")
    svc = IndexService(rocks_path=tmp_path / "rocks2")
    svc.index_repo(repo, parallel=False)
    watch = WatchDaemon()
    watch.start(repo, svc)
    time.sleep(0.2)
    f.write_text("def foo():\n    return 2\n\ndef bar():\n    return 3\n")
    deadline = time.time() + 4
    found = False
    while time.time() < deadline:
        names = {n.props["name"] for n in svc.memory.nodes.values() if n.label == "Function"}
        if "bar" in names:
            found = True
            break
        time.sleep(0.15)
    watch.stop()
    assert found
