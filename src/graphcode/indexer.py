from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from graphcode.config import settings
from graphcode.embed.encoder import embed_text, function_text
from graphcode.loader.memory import MemoryStore
from graphcode.loader.memgraph import MemgraphStore
from graphcode.loader.rocksdb_store import RocksStore, file_digest
from graphcode.parsers.base import ParseContext
from graphcode.parsers.registry import parser_for
from graphcode.resolver.calls import resolve_calls
from graphcode.resolver.imports import resolve_imports, resolve_inherits
from graphcode.scanner import scan_repo
from graphcode.schema import GraphBatch


class IndexService:
    def __init__(self, rocks_path: Path | str | None = None) -> None:
        self.memory = MemoryStore()
        self.rocks = RocksStore(rocks_path or settings.rocks_path)
        self.memgraph: MemgraphStore | None = None
        if settings.memgraph_uri:
            try:
                self.memgraph = MemgraphStore(
                    settings.memgraph_uri,
                    settings.memgraph_user,
                    settings.memgraph_password,
                )
                self.memgraph.ensure_indexes()
            except Exception:
                self.memgraph = None
        self.last_index: dict = {}
        self._hydrate()

    def _hydrate(self) -> None:
        snaps = self.rocks.all_snapshots()
        if not snaps:
            return
        if self.memory.counts().get("Module"):
            return
        for org_id, repo_id, batch in snaps:
            self.memory.load_batch(batch, org_id=org_id)
            if self.memgraph:
                try:
                    self.memgraph.load_batch(batch, org_id)
                except Exception:
                    pass
        self.rocks.set_meta("last_hydrate", datetime.now(timezone.utc).isoformat())

    def index_repo(
        self,
        root: Path | str,
        *,
        org_id: str = "local",
        repo_id: str | None = None,
        parallel: bool = True,
    ) -> dict:
        root = Path(root).resolve()
        files = scan_repo(root)
        repo_hash = hashlib.sha1(str(root).encode()).hexdigest()[:12]
        repo_id = repo_id or repo_hash
        jobs = []
        for rel, lang in files:
            path = root / rel
            source = path.read_bytes()
            jobs.append((rel, lang, source, repo_hash))

        batch = GraphBatch()
        if parallel and len(jobs) > 4:
            with ThreadPoolExecutor(max_workers=8) as pool:
                futs = [pool.submit(_parse_one, j) for j in jobs]
                for fut in as_completed(futs):
                    part = fut.result()
                    if part:
                        batch.merge(part)
        else:
            for j in jobs:
                part = _parse_one(j)
                if part:
                    batch.merge(part)

        resolve_imports(batch, repo_hash, root)
        resolve_inherits(batch)
        resolve_calls(batch)

        for n in batch.nodes:
            n.props["org_id"] = org_id
            n.props["repo_id"] = repo_id

        repo_node_props = {
            "name": root.name,
            "root_path": str(root),
            "indexed_at": datetime.now(timezone.utc).isoformat(),
            "org_id": org_id,
        }

        self.memory.clear_org(org_id)
        self.memory.load_batch(batch, org_id=org_id)
        self.memory.repo_meta = repo_node_props
        if self.memgraph:
            try:
                self.memgraph.clear_org(org_id)
                self.memgraph.load_batch(batch, org_id)
            except Exception:
                pass
        self.rocks.save_snapshot(org_id, repo_id, batch)
        for rel, lang, source, _ in jobs:
            self.rocks.set_hash(org_id, repo_id, rel, file_digest(source))
            text_map = {n.id: n for n in batch.nodes if n.props.get("path") == rel}

        # embeddings for functions
        sources = {rel: src for rel, lang, src, _ in jobs}
        for n in batch.nodes:
            if n.label != "Function":
                continue
            src = sources.get(n.props.get("path", ""), b"")
            text = function_text(n, src.decode("utf-8", errors="replace"))
            vec = embed_text(text)
            self.rocks.put_vector(n.id, org_id, vec)

        counts = self.memory.counts()
        self.last_index = {
            "org_id": org_id,
            "repo_id": repo_id,
            "repo_hash": repo_hash,
            "root": str(root),
            "files": len(files),
            "counts": counts,
            "indexed_at": repo_node_props["indexed_at"],
        }
        return self.last_index

    def reindex_file(
        self,
        root: Path | str,
        rel: str,
        *,
        org_id: str = "local",
        repo_id: str | None = None,
    ) -> dict:
        root = Path(root).resolve()
        repo_hash = hashlib.sha1(str(root).encode()).hexdigest()[:12]
        repo_id = repo_id or self.last_index.get("repo_id") or repo_hash
        path = root / rel
        if not path.is_file():
            self.memory.delete_module(rel, org_id)
            return {"deleted": rel}
        source = path.read_bytes()
        digest = file_digest(source)
        prev = self.rocks.get_hash(org_id, repo_id, rel)
        if prev == digest:
            return {"unchanged": rel}
        from graphcode.config import EXTENSION_LANGUAGE

        lang = EXTENSION_LANGUAGE.get(path.suffix.lower())
        if not lang:
            return {"skipped": rel}
        self.memory.delete_module(rel, org_id)
        if self.memgraph:
            try:
                self.memgraph.delete_module(rel, org_id)
            except Exception:
                pass
        part = _parse_one((rel, lang, source, repo_hash))
        if part:
            for n in part.nodes:
                n.props["org_id"] = org_id
                n.props["repo_id"] = repo_id
            resolve_imports(part, repo_hash, root)
            resolve_calls(part)
            self.memory.load_batch(part, org_id=org_id)
            if self.memgraph:
                try:
                    self.memgraph.load_batch(part, org_id)
                except Exception:
                    pass
            src_text = source.decode("utf-8", errors="replace")
            for n in part.nodes:
                if n.label == "Function":
                    self.rocks.put_vector(n.id, org_id, embed_text(function_text(n, src_text)))
        self.rocks.set_hash(org_id, repo_id, rel, digest)
        snap = GraphBatch(nodes=list(self.memory.nodes.values()), edges=[])
        for edges in self.memory.out.values():
            snap.edges.extend(edges)
        self.rocks.save_snapshot(org_id, repo_id, snap)
        return {"reindexed": rel, "digest": digest}


def _parse_one(job: tuple[str, str, bytes, str]) -> GraphBatch | None:
    rel, lang, source, repo_hash = job
    try:
        parser = parser_for(lang)
        ctx = ParseContext(repo_hash=repo_hash, path=rel, source=source, language=lang)
        return parser.parse_source(ctx)
    except Exception:
        return None


_SERVICE: IndexService | None = None


def get_index_service() -> IndexService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = IndexService()
    return _SERVICE
