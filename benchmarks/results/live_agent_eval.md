# Live autonomous-agent benchmark (real tool-calling, not pre-built context)

| Condition | Pass rate | Avg tool calls | Avg latency (s) |
|---|---|---|---|
| graph | 7/7 (100%) | 6.1 | 105.4 |
| baseline_toolagent | 7/7 (100%) | 6.0 | 26.3 |

## Per-task detail
| Task | graph (pass/calls) | baseline_toolagent (pass/calls) |
|---|---|---|
| rename_function | PASS / 8 | PASS / 6 |
| add_required_param | PASS / 5 | PASS / 6 |
| change_return_type | PASS / 5 | PASS / 6 |
| remove_default_arg | PASS / 6 | PASS / 6 |
| rename_exception | PASS / 8 | PASS / 5 |
| rename_shared_constant | PASS / 4 | PASS / 6 |
| polymorphic_interface_change | PASS / 7 | PASS / 7 |
