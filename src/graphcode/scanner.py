from __future__ import annotations

from pathlib import Path

import pathspec

from graphcode.config import DEFAULT_IGNORE, EXTENSION_LANGUAGE, settings


def _load_gitignore(root: Path) -> pathspec.PathSpec:
    lines = list(DEFAULT_IGNORE)
    gi = root / ".gitignore"
    if gi.is_file():
        lines.extend(gi.read_text(encoding="utf-8", errors="ignore").splitlines())
    return pathspec.PathSpec.from_lines("gitignore", lines)


def scan_repo(root: Path | str) -> list[tuple[str, str]]:
    """Return (relative_path, language) for indexable source files."""
    root = Path(root).resolve()
    spec = _load_gitignore(root)
    out: list[tuple[str, str]] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if spec.match_file(rel):
            continue
        lang = EXTENSION_LANGUAGE.get(path.suffix.lower())
        if not lang:
            continue
        try:
            if path.stat().st_size > settings.max_file_bytes:
                continue
        except OSError:
            continue
        out.append((rel, lang))
    out.sort()
    return out
