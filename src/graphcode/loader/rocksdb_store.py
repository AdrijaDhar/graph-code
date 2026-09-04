from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from graphcode.schema import GraphBatch, GraphEdge, GraphNode


class RocksStore:
    """Durable snapshots, file hashes, and embedding blobs.

    Uses rocksdict when installed; otherwise SQLite with the same API so tests
    and $0 VMs still persist across Memgraph restarts.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self._rocks = None
        # iter_vectors() is called on every semantic/hybrid query; without this cache
        # it re-reads and JSON-deserializes every stored vector from disk each time,
        # which measured ~200ms at ~3k functions (dominating the whole context-compile
        # latency budget). put_vector keeps this warm as functions are indexed; the
        # first iter_vectors() call in a fresh process still pays one disk scan to
        # pick up vectors from a prior run (dual-store hydrate).
        self._vector_cache: dict[str, tuple[str, list[float]]] = {}
        self._vector_cache_loaded = False
        try:
            from rocksdict import Rdict, Options

            opts = Options()
            opts.create_if_missing(True)
            self._rocks = Rdict(str(self.path / "rdict"), opts)
        except Exception:
            self._db = sqlite3.connect(self.path / "fallback.sqlite", check_same_thread=False)
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS kv (cf TEXT, k TEXT, v BLOB, PRIMARY KEY (cf, k))"
            )
            self._db.commit()

    def _put(self, cf: str, key: str, value: bytes) -> None:
        if self._rocks is not None:
            self._rocks[f"{cf}:{key}"] = value
            return
        self._db.execute(
            "INSERT OR REPLACE INTO kv (cf, k, v) VALUES (?, ?, ?)",
            (cf, key, value),
        )
        self._db.commit()

    def _get(self, cf: str, key: str) -> bytes | None:
        if self._rocks is not None:
            return self._rocks.get(f"{cf}:{key}")
        row = self._db.execute("SELECT v FROM kv WHERE cf=? AND k=?", (cf, key)).fetchone()
        return row[0] if row else None

    def _items(self, cf: str) -> Iterable[tuple[str, bytes]]:
        if self._rocks is not None:
            prefix = f"{cf}:"
            for k, v in self._rocks.items():
                ks = k.decode() if isinstance(k, bytes) else str(k)
                if ks.startswith(prefix):
                    yield ks[len(prefix) :], v
            return
        for k, v in self._db.execute("SELECT k, v FROM kv WHERE cf=?", (cf,)):
            yield k, v

    def save_snapshot(self, org_id: str, repo_id: str, batch: GraphBatch) -> None:
        payload = {
            "nodes": [{"id": n.id, "label": n.label, "props": n.props} for n in batch.nodes],
            "edges": [
                {"type": e.type, "from_id": e.from_id, "to_id": e.to_id, "props": e.props}
                for e in batch.edges
            ],
        }
        self._put("graph_snap", f"{org_id}:{repo_id}", json.dumps(payload).encode())

    def load_snapshot(self, org_id: str, repo_id: str) -> GraphBatch | None:
        raw = self._get("graph_snap", f"{org_id}:{repo_id}")
        if not raw:
            return None
        data = json.loads(raw)
        batch = GraphBatch()
        for n in data.get("nodes", []):
            batch.add_node(GraphNode(id=n["id"], label=n["label"], props=n.get("props") or {}))
        for e in data.get("edges", []):
            batch.add_edge(
                GraphEdge(type=e["type"], from_id=e["from_id"], to_id=e["to_id"], props=e.get("props") or {})
            )
        return batch

    def all_snapshots(self) -> list[tuple[str, str, GraphBatch]]:
        out = []
        for key, raw in self._items("graph_snap"):
            org_id, _, repo_id = key.partition(":")
            data = json.loads(raw)
            batch = GraphBatch()
            for n in data.get("nodes", []):
                batch.add_node(GraphNode(id=n["id"], label=n["label"], props=n.get("props") or {}))
            for e in data.get("edges", []):
                batch.add_edge(
                    GraphEdge(type=e["type"], from_id=e["from_id"], to_id=e["to_id"], props=e.get("props") or {})
                )
            out.append((org_id, repo_id, batch))
        return out

    def set_hash(self, org_id: str, repo_id: str, path: str, digest: str) -> None:
        self._put("file_hash", f"{org_id}:{repo_id}:{path}", digest.encode())

    def get_hash(self, org_id: str, repo_id: str, path: str) -> str | None:
        raw = self._get("file_hash", f"{org_id}:{repo_id}:{path}")
        return raw.decode() if raw else None

    def put_vector(self, function_id: str, org_id: str, vec: list[float]) -> None:
        payload = json.dumps({"org_id": org_id, "vec": vec}).encode()
        self._put("vectors", function_id, payload)
        self._vector_cache[function_id] = (org_id, vec)

    def iter_vectors(self, org_id: str | None = None) -> Iterable[tuple[str, list[float]]]:
        if not self._vector_cache_loaded:
            for key, raw in self._items("vectors"):
                data = json.loads(raw)
                self._vector_cache[key] = (data.get("org_id"), data["vec"])
            self._vector_cache_loaded = True
        for key, (vec_org_id, vec) in self._vector_cache.items():
            if org_id and vec_org_id != org_id:
                continue
            yield key, vec

    def set_meta(self, key: str, value: str) -> None:
        self._put("meta", key, value.encode())


def file_digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
