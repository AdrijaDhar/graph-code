# Task-level agent impact benchmark

| Condition | Pass rate | Tasks passed |
|---|---|---|
| baseline | 0/6 (0%) |  |
| graph | 6/6 (100%) | rename_function, add_required_param, change_return_type, remove_default_arg, rename_exception, rename_shared_constant |
| embedding | 6/6 (100%) | rename_function, add_required_param, change_return_type, remove_default_arg, rename_exception, rename_shared_constant |

## Per-task detail
| Task | baseline | graph | embedding |
|---|---|---|---|
| rename_function | FAIL | PASS | PASS |
| add_required_param | FAIL | PASS | PASS |
| change_return_type | FAIL | PASS | PASS |
| remove_default_arg | FAIL | PASS | PASS |
| rename_exception | FAIL | PASS | PASS |
| rename_shared_constant | FAIL | PASS | PASS |
