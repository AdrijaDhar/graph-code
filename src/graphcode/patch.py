"""Shared convention for an LLM to propose whole-file edits as plain text, and for a
diff to be shown to a human before it's applied to disk.

Used by both benchmarks/agent_eval/runner.py (grading, auto-applied to a throwaway
temp dir) and mcp/client.py (the interactive agent, applied only after confirmation).
"""

from __future__ import annotations

import difflib
import re

FILE_BLOCK_RE = re.compile(r"<<<FILE (.+?)>>>\n(.*?)<<<END>>>", re.DOTALL)


def parse_file_blocks(text: str) -> list[tuple[str, str]]:
    """Extract (path, content) pairs from '<<<FILE path>>>\\n...\\n<<<END>>>' blocks."""
    return [(path.strip(), content) for path, content in FILE_BLOCK_RE.findall(text)]


def unified_diff(old: str, new: str, path: str) -> str:
    diff = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    )
    return "".join(diff)
