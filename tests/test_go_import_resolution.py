from pathlib import Path

from graphcode.indexer import IndexService


def _write(root: Path, rel: str, content: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def test_go_cross_package_import_resolves_via_go_mod(tmp_path):
    """Real, previously-documented gap (eval/README.md's M2 results: "Go cross-package
    imports without a go.mod don't resolve"). Go imports a whole *package* (a
    directory), not a file — there's no per-symbol import list the way Python/JS have
    — so mapping an import spec like "example.com/app/pkg/util" back to the local
    directory it actually names requires reading go.mod's declared module path.
    Without this, main.go calling util.Parse() from a different package would show up
    as an unresolved CALLS edge, and blast_radius/call_chain would miss it entirely.

    `pkg/util` deliberately has *two* files: `util.go` (matches the package dir name,
    so resolve_imports picks it as the one representative structural edge — see
    imports.py::_go_import_paths) and `helpers.go` (does not). `Run` calls a function
    from *each*, so resolving Format correctly is the real test — it requires
    resolve_calls to expand the one resolved edge to its sibling directory rather than
    just checking the single linked file, which is the whole point of this fix."""
    root = tmp_path / "repo"
    _write(root, "go.mod", "module example.com/app\n\ngo 1.21\n")
    _write(root, "pkg/util/util.go", "package util\n\nfunc Parse(s string) string {\n\treturn s\n}\n")
    _write(root, "pkg/util/helpers.go", "package util\n\nfunc Format(s string) string {\n\treturn s\n}\n")
    _write(
        root,
        "main.go",
        'package main\n\nimport "example.com/app/pkg/util"\n\n'
        'func Run() string {\n\treturn util.Format(util.Parse("x"))\n}\n',
    )

    svc = IndexService(rocks_path=tmp_path / "rocks")
    svc.index_repo(root, parallel=False)

    run_node = svc.memory.find("Run")
    parse_node = svc.memory.find("Parse")
    format_node = svc.memory.find("Format")
    assert run_node is not None
    assert parse_node is not None
    assert format_node is not None
    callees = {e.to_id for e in svc.memory.out.get(run_node.id, []) if e.type == "CALLS"}
    assert parse_node.id in callees, "Run() -> util.Parse() (the representative file) should resolve"
    assert format_node.id in callees, "Run() -> util.Format() (a sibling file in the same package) should resolve too"


def test_go_import_without_go_mod_falls_back_gracefully(tmp_path):
    """No go.mod present (matches tests/fixtures/mini_repo/go, which has none) must
    not crash — just fall through to the pre-existing generic stem-matching fallback,
    same behavior as before this fix."""
    root = tmp_path / "repo"
    _write(root, "pkg/util/util.go", "package util\n\nfunc Parse(s string) string {\n\treturn s\n}\n")
    _write(
        root,
        "main.go",
        'package main\n\nimport "example.com/app/pkg/util"\n\nfunc Run() string {\n\treturn util.Parse("x")\n}\n',
    )

    svc = IndexService(rocks_path=tmp_path / "rocks")
    result = svc.index_repo(root, parallel=False)  # must not raise
    assert result["counts"]["Function"] == 2
