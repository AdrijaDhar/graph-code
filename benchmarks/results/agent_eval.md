# Task-level agent impact benchmark

| Condition | Pass rate | Tasks passed |
|---|---|---|
| baseline | 0/7 (0%) |  |
| graph | 7/7 (100%) | rename_function, add_required_param, change_return_type, remove_default_arg, rename_exception, rename_shared_constant, polymorphic_interface_change |
| embedding | 7/7 (100%) | rename_function, add_required_param, change_return_type, remove_default_arg, rename_exception, rename_shared_constant, polymorphic_interface_change |

## Per-task detail
| Task | baseline | graph | embedding |
|---|---|---|---|
| rename_function | FAIL | PASS | PASS |
| add_required_param | FAIL | PASS | PASS |
| change_return_type | FAIL | PASS | PASS |
| remove_default_arg | FAIL | PASS | PASS |
| rename_exception | FAIL | PASS | PASS |
| rename_shared_constant | FAIL | PASS | PASS |
| polymorphic_interface_change | FAIL | PASS | PASS |
