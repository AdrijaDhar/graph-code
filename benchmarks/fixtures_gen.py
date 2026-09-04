"""Generate synthetic Python repos with realistic layered cross-file call/import density,
for measuring index time and query latency at scale without depending on any real
external repo (keeps the perf benchmark offline and reproducible).

Layout: utils/ (leaf functions) <- services/ (import + call 2-3 utils, one class each)
        <- controllers/ (import + call 2-3 services).
"""

from __future__ import annotations

import random
from pathlib import Path


def generate_repo(root: Path, n_files: int, seed: int = 0) -> None:
    random.seed(seed)
    root.mkdir(parents=True, exist_ok=True)

    n_util = max(1, n_files // 5)
    n_service = max(1, (n_files - n_util) * 2 // 3)
    n_ctrl = max(1, n_files - n_util - n_service)

    util_dir = root / "utils"
    util_dir.mkdir(exist_ok=True)
    util_funcs: list[tuple[str, str]] = []
    for i in range(n_util):
        mod = f"util_{i}"
        funcs = [f"helper_{i}_{j}" for j in range(random.randint(2, 5))]
        body = "\n\n".join(f"def {fn}(x):\n    return x + {j}" for j, fn in enumerate(funcs))
        (util_dir / f"{mod}.py").write_text(body + "\n")
        util_funcs.extend((mod, fn) for fn in funcs)
    (util_dir / "__init__.py").write_text("")

    service_dir = root / "services"
    service_dir.mkdir(exist_ok=True)
    service_classes: list[tuple[int, str]] = []
    for i in range(n_service):
        picks = random.sample(util_funcs, k=min(3, len(util_funcs)))
        imports = "\n".join(f"from utils.{m} import {fn}" for m, fn in picks)
        calls = ", ".join(f"{fn}(1)" for _, fn in picks)
        cls = f"Service{i}"
        code = f"{imports}\n\n\nclass {cls}:\n    def run(self):\n        return [{calls}]\n"
        (service_dir / f"service_{i}.py").write_text(code)
        service_classes.append((i, cls))
    (service_dir / "__init__.py").write_text("")

    ctrl_dir = root / "controllers"
    ctrl_dir.mkdir(exist_ok=True)
    for i in range(n_ctrl):
        picks = random.sample(service_classes, k=min(3, len(service_classes)))
        imports = "\n".join(f"from services.service_{p} import {cls}" for p, cls in picks)
        calls = ", ".join(f"{cls}().run()" for _, cls in picks)
        code = f"{imports}\n\n\nclass Controller{i}:\n    def handle(self):\n        return [{calls}]\n"
        (ctrl_dir / f"controller_{i}.py").write_text(code)
    (ctrl_dir / "__init__.py").write_text("")


if __name__ == "__main__":
    import sys
    import tempfile

    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    out = Path(tempfile.mkdtemp(prefix=f"gc_synth_{n}_"))
    generate_repo(out, n)
    print(out)
