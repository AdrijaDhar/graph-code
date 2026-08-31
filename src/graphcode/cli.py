from __future__ import annotations

import argparse
import json
from pathlib import Path

from graphcode.indexer import get_index_service
from graphcode.watcher.daemon import get_watch


def main() -> None:
    p = argparse.ArgumentParser(prog="graphcode")
    sub = p.add_subparsers(dest="cmd", required=True)
    idx = sub.add_parser("index")
    idx.add_argument("path")
    st = sub.add_parser("status")
    w = sub.add_parser("watch")
    w.add_argument("path")
    args = p.parse_args()
    svc = get_index_service()
    if args.cmd == "index":
        print(json.dumps(svc.index_repo(Path(args.path)), indent=2))
    elif args.cmd == "status":
        print(json.dumps(svc.last_index or {"error": "not indexed"}, indent=2))
    elif args.cmd == "watch":
        print(json.dumps(get_watch().start(args.path, svc), indent=2))
        try:
            import time

            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            get_watch().stop()


if __name__ == "__main__":
    main()
