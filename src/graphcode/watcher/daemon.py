from __future__ import annotations

import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from graphcode.config import EXTENSION_LANGUAGE
from graphcode.indexer import IndexService


class _Handler(FileSystemEventHandler):
    def __init__(self, svc: IndexService, root: Path, org_id: str, debounce_s: float = 0.4) -> None:
        self.svc = svc
        self.root = root
        self.org_id = org_id
        self.debounce_s = debounce_s
        self._pending: dict[str, float] = {}
        self._lock = threading.Lock()
        self.last_event: dict | None = None
        threading.Thread(target=self._flusher, daemon=True).start()

    def _queue(self, src: str) -> None:
        p = Path(src)
        try:
            rel = p.relative_to(self.root).as_posix()
        except ValueError:
            return
        if p.suffix.lower() not in EXTENSION_LANGUAGE and p.suffix:
            return
        with self._lock:
            self._pending[rel] = time.time()

    def on_modified(self, event):
        if not event.is_directory:
            self._queue(event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self._queue(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            self._queue(event.src_path)

    def _flusher(self) -> None:
        while True:
            time.sleep(self.debounce_s)
            now = time.time()
            due: list[str] = []
            with self._lock:
                for rel, ts in list(self._pending.items()):
                    if now - ts >= self.debounce_s:
                        due.append(rel)
                        del self._pending[rel]
            for rel in due:
                try:
                    self.last_event = self.svc.reindex_file(self.root, rel, org_id=self.org_id)
                except Exception as exc:
                    self.last_event = {"error": str(exc), "path": rel}


class WatchDaemon:
    def __init__(self) -> None:
        self._observer: Observer | None = None
        self.handler: _Handler | None = None
        self.root: str | None = None

    def start(self, root: Path | str, svc: IndexService, org_id: str = "local") -> dict:
        self.stop()
        root = Path(root).resolve()
        handler = _Handler(svc, root, org_id)
        obs = Observer()
        obs.schedule(handler, str(root), recursive=True)
        obs.start()
        self._observer = obs
        self.handler = handler
        self.root = str(root)
        return {"watching": self.root}

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=2)
            self._observer = None

    def status(self) -> dict:
        return {
            "watching": self.root,
            "last_event": self.handler.last_event if self.handler else None,
        }


_WATCH = WatchDaemon()


def get_watch() -> WatchDaemon:
    return _WATCH
