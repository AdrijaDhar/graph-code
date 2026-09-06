# Incremental reindex latency (M5)

| Files | Touches | before (sync snapshot every save) p50/p95 (ms) | after (debounced) p50/p95 (ms) |
|---|---|---|---|
| 2000 | 30 | 42.43/123.69 | 9.61/88.35 |

Target: p95 < 150ms.
- 2000 files (debounced): p95 88.35ms (PASS)
