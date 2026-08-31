"""Utilities used by the API controller."""


def parse_config(raw: str) -> dict:
    items = {}
    for line in raw.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            items[k.strip()] = v.strip()
    return items


def unused_helper() -> int:
    return 42
