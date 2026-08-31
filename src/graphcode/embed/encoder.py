from __future__ import annotations

import hashlib
import math
from typing import Iterable

import numpy as np

from graphcode.schema import GraphNode

_DIM = 384
_MODEL = None


def _hash_vec(text: str) -> list[float]:
    vec = np.zeros(_DIM, dtype=np.float32)
    tokens = text.lower().replace("_", " ").replace(".", " ").split()
    if not tokens:
        tokens = [text.lower()]
    for tok in tokens:
        h = int(hashlib.sha256(tok.encode()).hexdigest(), 16)
        vec[h % _DIM] += 1.0
        vec[(h // _DIM) % _DIM] += 0.5
    n = float(np.linalg.norm(vec))
    if n:
        vec /= n
    return vec.tolist()


def embed_text(text: str) -> list[float]:
    global _MODEL
    if _MODEL is False:
        return _hash_vec(text)
    if _MODEL is None:
        try:
            from fastembed import TextEmbedding

            _MODEL = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
        except Exception:
            _MODEL = False
            return _hash_vec(text)
    try:
        vecs = list(_MODEL.embed([text[:4000]]))
        return [float(x) for x in vecs[0]]
    except Exception:
        return _hash_vec(text)


def function_text(node: GraphNode, source: str) -> str:
    start = max(int(node.props.get("start_line") or 1) - 1, 0)
    end = int(node.props.get("end_line") or start + 1)
    lines = source.splitlines()
    body = "\n".join(lines[start : min(end, start + 40)])
    qn = node.props.get("qualified_name", "")
    return f"{qn}\n{body}"


def cosine(a: list[float], b: list[float]) -> float:
    va = np.asarray(a, dtype=np.float32)
    vb = np.asarray(b, dtype=np.float32)
    n = float(np.linalg.norm(va) * np.linalg.norm(vb))
    if not n:
        return 0.0
    return float(np.dot(va, vb) / n)


def knn(query: list[float], items: Iterable[tuple[str, list[float]]], k: int = 8) -> list[tuple[str, float]]:
    scored = [(fid, cosine(query, vec)) for fid, vec in items]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:k]
