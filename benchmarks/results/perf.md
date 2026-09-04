# Performance / scale benchmark

| Files | Functions | Edges | Index (s) | shortest_path p50/p95 (ms) | blast_radius p50/p95 (ms) | call_chain p50/p95 (ms) | context_compile p50/p95 (ms) |
|---|---|---|---|---|---|---|---|
| 500 | 746 | 3546 | 5.221 | 0.38/1.29 | 0.05/0.08 | 0.01/0.02 | 21.33/23.96 |
| 2000 | 2977 | 14177 | 20.614 | 2.12/4.17 | 0.06/0.09 | 0.01/0.01 | 53.37/56.66 |

Targets: index <30s @500 files, shortest_path <50ms, context_compile <200ms.
- 500-file index: 5.221s (PASS vs <30s target)
- 500-file shortest_path p95: 1.29ms (PASS vs <50ms), context_compile p95: 23.96ms (PASS vs <200ms)
- 2000-file index: 20.614s (PASS vs <30s target)
- 2000-file shortest_path p95: 4.17ms (PASS vs <50ms), context_compile p95: 56.66ms (PASS vs <200ms)
