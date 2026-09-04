"""Task-level eval set: 'editing file A breaks file B in a different folder' scenarios,
the exact failure mode the product targets. Each task ships as a tiny synthetic Python
repo (kept small and self-contained so grading is deterministic and offline) with:

  - `files`: the starting repo state
  - `prompt`: what the user asked for (names only `primary_file`)
  - `primary_file`: the one file a "few open files" baseline agent would see
  - a `check_script` that imports the patched repo in a subprocess and asserts
    correct end-to-end behavior — it doesn't care *how* the fix was made, only
    whether the repo actually still works, which is the fairest, least gameable
    grading criterion.

If a caller file elsewhere in the repo isn't also updated, the check fails with a
clean, deterministic Python exception (ImportError/TypeError/AttributeError) —
exactly the kind of break a graph-context agent should catch and a same-file-only
agent should miss.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Task:
    id: str
    prompt: str
    primary_file: str
    files: dict[str, str]
    check_script: str

    def run_check(self, repo_dir: Path) -> tuple[bool, str]:
        try:
            proc = subprocess.run(
                [sys.executable, "-c", self.check_script],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except subprocess.TimeoutExpired:
            return False, "timeout"
        ok = proc.returncode == 0 and "OK" in proc.stdout
        return ok, (proc.stdout + proc.stderr).strip()


TASKS: list[Task] = [
    Task(
        id="rename_function",
        prompt=(
            "Rename `to_snake` in utils/format.py to `to_snake_case` for clarity. "
            "Update any code in the repo that calls it."
        ),
        primary_file="utils/format.py",
        files={
            "utils/__init__.py": "",
            "utils/format.py": (
                "def to_snake(s):\n"
                "    return s.strip().lower().replace(' ', '_')\n"
            ),
            "api/__init__.py": "",
            "api/handlers.py": (
                "from utils.format import to_snake\n\n\n"
                "def handle(name):\n"
                "    return to_snake(name)\n"
            ),
        },
        check_script=(
            "import sys; sys.path.insert(0, '.')\n"
            "from api.handlers import handle\n"
            "assert handle('Hello World') == 'hello_world'\n"
            "print('OK')\n"
        ),
    ),
    Task(
        id="add_required_param",
        prompt=(
            "Add a required `timeout` parameter to `connect` in db/connection.py, placed "
            "right after `host, port` (no default value — every caller must now pass it "
            "explicitly). Update any code in the repo that calls `connect`, passing 30 as "
            "a reasonable timeout."
        ),
        primary_file="db/connection.py",
        files={
            "db/__init__.py": "",
            "db/connection.py": (
                "class Connection:\n"
                "    def __init__(self, host, port, timeout):\n"
                "        self.host = host\n"
                "        self.port = port\n"
                "        self.timeout = timeout\n\n\n"
                "def connect(host, port):\n"
                "    return Connection(host, port, timeout=30)\n"
            ),
            "services/__init__.py": "",
            "services/query.py": (
                "from db.connection import connect\n\n\n"
                "def run_query(sql):\n"
                "    conn = connect('localhost', 5432)\n"
                "    return f'executed {sql} on {conn.host}:{conn.port}'\n"
            ),
        },
        check_script=(
            "import sys; sys.path.insert(0, '.')\n"
            "from services.query import run_query\n"
            "result = run_query('SELECT 1')\n"
            "assert result == 'executed SELECT 1 on localhost:5432', result\n"
            "print('OK')\n"
        ),
    ),
    Task(
        id="change_return_type",
        prompt=(
            "Change `full_name` in models/user.py to return a tuple `(first, last)` instead "
            "of a formatted string, so callers can format it however they like. Update any "
            "code in the repo that currently treats the return value as a string."
        ),
        primary_file="models/user.py",
        files={
            "models/__init__.py": "",
            "models/user.py": (
                "class User:\n"
                "    def __init__(self, first, last):\n"
                "        self.first = first\n"
                "        self.last = last\n\n"
                "    def full_name(self):\n"
                "        return f'{self.first} {self.last}'\n"
            ),
            "views/__init__.py": "",
            "views/profile.py": (
                "from models.user import User\n\n\n"
                "def render(first, last):\n"
                "    u = User(first, last)\n"
                "    return u.full_name().upper()\n"
            ),
        },
        check_script=(
            "import sys; sys.path.insert(0, '.')\n"
            "from views.profile import render\n"
            "result = render('Ada', 'Lovelace')\n"
            "assert result == 'ADA LOVELACE', result\n"
            "print('OK')\n"
        ),
    ),
    Task(
        id="remove_default_arg",
        prompt=(
            "Remove the default value for `path` in config/settings.py's `load` function — "
            "a config path should always be passed explicitly, never implicitly assumed. "
            "Update any code in the repo that currently relies on the default, passing "
            "'config.json'."
        ),
        primary_file="config/settings.py",
        files={
            "config/__init__.py": "",
            "config/settings.py": (
                "import json\n\n\n"
                "def load(path='config.json'):\n"
                "    with open(path) as f:\n"
                "        return json.load(f)\n"
            ),
            "bootstrap/__init__.py": "",
            "bootstrap/init.py": (
                "from config.settings import load\n\n\n"
                "def bootstrap():\n"
                "    return load()\n"
            ),
            "config.json": '{"env": "test"}',
        },
        check_script=(
            "import sys; sys.path.insert(0, '.')\n"
            "from bootstrap.init import bootstrap\n"
            "result = bootstrap()\n"
            "assert result == {'env': 'test'}, result\n"
            "print('OK')\n"
        ),
    ),
    Task(
        id="rename_exception",
        prompt=(
            "Rename `ClientError` to `NetworkError` in net/client.py to better reflect its "
            "scope. Update any code in the repo that imports or references `ClientError`."
        ),
        primary_file="net/client.py",
        files={
            "net/__init__.py": "",
            "net/client.py": (
                "class ClientError(Exception):\n"
                "    pass\n\n\n"
                "def fetch(url):\n"
                "    if not url.startswith('http'):\n"
                "        raise ClientError(f'bad url: {url}')\n"
                "    return f'fetched {url}'\n"
            ),
            "handlers/__init__.py": "",
            "handlers/retry.py": (
                "from net.client import ClientError, fetch\n\n\n"
                "def safe_fetch(url):\n"
                "    try:\n"
                "        return fetch(url)\n"
                "    except ClientError:\n"
                "        return 'error'\n"
            ),
        },
        check_script=(
            "import sys; sys.path.insert(0, '.')\n"
            "from handlers.retry import safe_fetch\n"
            "assert safe_fetch('not-a-url') == 'error'\n"
            "assert safe_fetch('http://x') == 'fetched http://x'\n"
            "print('OK')\n"
        ),
    ),
    Task(
        id="rename_shared_constant",
        prompt=(
            "Rename `MAX_RETRIES` in constants.py to `MAX_RETRY_ATTEMPTS` since 'RETRIES' "
            "was ambiguous with a different retry-count metric elsewhere in the codebase. "
            "Update any code in the repo that imports or uses it."
        ),
        primary_file="constants.py",
        files={
            "constants.py": "MAX_RETRIES = 3\n",
            "worker/__init__.py": "",
            "worker/pool.py": (
                "from constants import MAX_RETRIES\n\n\n"
                "def run_with_retries(fn):\n"
                "    attempts = 0\n"
                "    last_exc = None\n"
                "    while attempts < MAX_RETRIES:\n"
                "        try:\n"
                "            return fn()\n"
                "        except Exception as exc:\n"
                "            last_exc = exc\n"
                "            attempts += 1\n"
                "    raise last_exc\n"
            ),
        },
        check_script=(
            "import sys; sys.path.insert(0, '.')\n"
            "from worker.pool import run_with_retries\n"
            "calls = {'n': 0}\n"
            "def flaky():\n"
            "    calls['n'] += 1\n"
            "    if calls['n'] < 3:\n"
            "        raise ValueError('fail')\n"
            "    return 'success'\n"
            "result = run_with_retries(flaky)\n"
            "assert result == 'success' and calls['n'] == 3, (result, calls)\n"
            "print('OK')\n"
        ),
    ),
]
