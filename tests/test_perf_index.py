import time
from pathlib import Path

from graphcode.indexer import IndexService


def test_index_many_files_under_30s(tmp_path):
    repo = tmp_path / "big"
    (repo / "pkg").mkdir(parents=True)
    for i in range(120):
        (repo / "pkg" / f"m{i}.py").write_text(f"def f{i}():\n    return {i}\n")
    svc = IndexService(rocks_path=tmp_path / "rocks")
    t0 = time.time()
    result = svc.index_repo(repo, parallel=True)
    elapsed = time.time() - t0
    assert result["files"] >= 120
    assert elapsed < 30
