from __future__ import annotations

import hashlib
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from graphcode.config import EXTENSION_LANGUAGE, settings
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
    def __init__(self, rocks_path: Path | str | None = None, snapshot_debounce_s: float = 5.0) -> None:
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
        # reindex_file() updates self.memory immediately (queries always see fresh
        # state) but debounces the durable RocksDB snapshot write, since that write
        # re-serializes the *entire* graph and was measured costing real time on
        # every single save — coalesce bursts of saves into one write.
        self._snapshot_debounce_s = snapshot_debounce_s
        self._snapshot_lock = threading.Lock()
        self._snapshot_timer: threading.Timer | None = None
        self._pending_snapshot: tuple[str, str] | None = None
        self._hydrate()

    def _schedule_snapshot(self, org_id: str, repo_id: str) -> None:
        with self._snapshot_lock:
            self._pending_snapshot = (org_id, repo_id)
            if self._snapshot_timer is None or not self._snapshot_timer.is_alive():
                self._snapshot_timer = threading.Timer(self._snapshot_debounce_s, self.flush_snapshot)
                self._snapshot_timer.daemon = True
                self._snapshot_timer.start()

    def flush_snapshot(self) -> None:
        """Write the pending durable snapshot now, bypassing the debounce timer.
        Safe to call with nothing pending (no-op)."""
        with self._snapshot_lock:
            pending = self._pending_snapshot
            self._pending_snapshot = None
            if self._snapshot_timer is not None:
                self._snapshot_timer.cancel()
                self._snapshot_timer = None
        if not pending:
            return
        org_id, repo_id = pending
        snap = GraphBatch(nodes=list(self.memory.nodes.values()), edges=[])
        for edges in self.memory.out.values():
            snap.edges.extend(edges)
        self.rocks.save_snapshot(org_id, repo_id, snap)

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
            with ProcessPoolExecutor(max_workers=8) as pool:
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
        """Re-parses just `rel` (plus, for ripple correctness, any file with a CALLS
        edge directly into it) and re-resolves against the rest of the already-known
        graph as lookup context — NOT the whole repo. Two things this fixes vs. a naive
        "re-parse this one file in isolation" approach:

        1. resolve_imports/resolve_calls need visibility into *other* modules to
           resolve anything cross-file at all; a batch containing only the one
           reindexed file's fresh nodes has none, so every one of that file's
           IMPORTS/CALLS edges would silently vanish on every single-file save
           (confirmed via a manual repro before this fix — this was live-destructive,
           not just "doesn't ripple").
        2. A caller elsewhere whose CALLS edge pointed into this file gets a real
           chance to re-resolve against the file's new symbols, instead of that edge
           just disappearing until the next full reindex.

        A brand-new import to a file with *no prior relationship* to `rel` still needs
        a full `index_repo()` to be picked up — this only re-resolves relationships
        the graph already knew about, which is the common single-file-edit case.
        """
        root = Path(root).resolve()
        repo_hash = hashlib.sha1(str(root).encode()).hexdigest()[:12]
        repo_id = repo_id or self.last_index.get("repo_id") or repo_hash
        path = root / rel
        if not path.is_file():
            self.memory.delete_module(rel, org_id)
            if self.memgraph:
                try:
                    self.memgraph.delete_module(rel, org_id)
                except Exception:
                    pass
            self._schedule_snapshot(org_id, repo_id)
            return {"deleted": rel}
        source = path.read_bytes()
        digest = file_digest(source)
        prev = self.rocks.get_hash(org_id, repo_id, rel)
        if prev == digest:
            return {"unchanged": rel}
        lang = EXTENSION_LANGUAGE.get(path.suffix.lower())
        if not lang:
            return {"skipped": rel}

        old_ids = {
            n.id for n in self.memory.nodes.values() if n.props.get("path") == rel and n.props.get("org_id") == org_id
        }
        neighbor_paths: set[str] = set()
        for nid in old_ids:
            for e in self.memory.inn.get(nid, []):
                if e.type == "CALLS":
                    caller = self.memory.nodes.get(e.from_id)
                    if caller and caller.props.get("path") != rel:
                        neighbor_paths.add(caller.props["path"])

        changed_paths = [rel] + sorted(neighbor_paths)
        for p in changed_paths:
            self.memory.delete_module(p, org_id)
            if self.memgraph:
                try:
                    self.memgraph.delete_module(p, org_id)
                except Exception:
                    pass

        fresh = GraphBatch()
        src_texts: dict[str, str] = {}
        for p in changed_paths:
            fp = root / p
            if not fp.is_file():
                continue
            p_lang = EXTENSION_LANGUAGE.get(fp.suffix.lower())
            if not p_lang:
                continue
            p_source = fp.read_bytes()
            src_texts[p] = p_source.decode("utf-8", errors="replace")
            b = _parse_one((p, p_lang, p_source, repo_hash))
            if not b:
                continue
            for n in b.nodes:
                n.props["org_id"] = org_id
                n.props["repo_id"] = repo_id
            fresh.merge(b)

        fresh_ids = {n.id for n in fresh.nodes}
        context = GraphBatch(nodes=list(fresh.nodes), edges=list(fresh.edges))
        for n in self.memory.nodes.values():
            if n.id not in fresh_ids:
                context.nodes.append(n)

        resolve_imports(context, repo_hash, root)
        resolve_inherits(context)
        resolve_calls(context)
        new_edges = [e for e in context.edges if e.from_id in fresh_ids]

        self.memory.load_batch(GraphBatch(nodes=fresh.nodes, edges=new_edges), org_id=org_id)
        if self.memgraph:
            try:
                self.memgraph.load_batch(GraphBatch(nodes=fresh.nodes, edges=new_edges), org_id)
            except Exception:
                pass

        for n in fresh.nodes:
            if n.label == "Function":
                src = src_texts.get(n.props.get("path", ""), "")
                self.rocks.put_vector(n.id, org_id, embed_text(function_text(n, src)))

        for p in changed_paths:
            fp = root / p
            if fp.is_file():
                self.rocks.set_hash(org_id, repo_id, p, file_digest(fp.read_bytes()))

        self._schedule_snapshot(org_id, repo_id)
        return {"reindexed": rel, "digest": digest, "rippled": sorted(neighbor_paths)}


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
