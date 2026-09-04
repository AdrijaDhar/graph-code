from __future__ import annotations

from graphcode.queries.hybrid import fuse_rrf


def test_fuse_rrf_top_ranked_in_both_lists_wins():
    structural = ["a", "b", "c"]
    semantic = ["b", "a", "d"]
    fused = fuse_rrf(structural, semantic)
    ids = [nid for nid, _ in fused]
    # "a" and "b" each appear near the top of both lists, so should outrank
    # "c"/"d" which only appear in one list.
    assert set(ids[:2]) == {"a", "b"}
    assert ids.index("c") > ids.index("a")
    assert ids.index("d") > ids.index("a")


def test_fuse_rrf_single_list_preserves_order():
    fused = fuse_rrf(["x", "y", "z"])
    assert [nid for nid, _ in fused] == ["x", "y", "z"]


def test_fuse_rrf_empty_lists():
    assert fuse_rrf([], []) == []


def test_fuse_rrf_no_lists():
    assert fuse_rrf() == []


def test_fuse_rrf_disjoint_lists_ranked_by_position():
    fused = fuse_rrf(["a", "b"], ["c", "d"])
    ids = [nid for nid, _ in fused]
    # rank-1 items from each list should beat rank-2 items from each list
    assert ids.index("a") < ids.index("b")
    assert ids.index("c") < ids.index("d")
