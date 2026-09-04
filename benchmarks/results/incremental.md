# Incremental reindex latency (M5)

| Files | Touches | before (sync snapshot every save) p50/p95 (ms) | after (debounced) p50/p95 (ms) |
|---|---|---|---|
| 10 | 30 | 7.01/62.22 | 6.44/60.75 |
| 100 | 30 | 14.76/108.6 | 13.04/107.18 |
| 500 | 30 | 15.87/103.77 | 7.96/96.49 |
| 2000 | 30 | 48.27/190.47 | 13.25/158.6 |

Target: p95 < 150ms.
- 10 files (debounced): p95 60.75ms (PASS)
- 100 files (debounced): p95 107.18ms (PASS)
- 500 files (debounced): p95 96.49ms (PASS)
- 2000 files (debounced): p95 158.6ms (FAIL)
