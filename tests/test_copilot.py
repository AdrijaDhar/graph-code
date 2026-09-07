"""Real end-to-end checks for the NL copilot (queries/copilot.py) against the actual
mini_repo fixture — verifies intent classification and answer phrasing hold up on
genuine paraphrases, not just the exact anchor example strings."""

from pathlib import Path

from graphcode.indexer import IndexService
from graphcode.queries.copilot import ask, classify_intent

ROOT = Path(__file__).parent / "fixtures" / "mini_repo"


def test_classify_intent_generalizes_to_paraphrases_not_just_keywords():
    # None of these share exact wording with the anchor examples in copilot.py — this
    # is the actual claim being tested: real semantic similarity, not string overlap.
    assert classify_intent("if I touch this, what else stops working")[0] == "impact"
    assert classify_intent("do I have any coverage for this at all")[0] == "tests"
    assert classify_intent("walk me through what runs after this is called")[0] == "chain"


def test_ask_impact_question_resolves_symbol_and_reports_dependents(tmp_path):
    svc = IndexService(rocks_path=tmp_path / "rocks")
    svc.index_repo(ROOT, parallel=False)
    result = ask(svc, "what breaks if I change parse_config?")
    assert result["intent"] == "impact"
    assert "parse_config" in result["symbols"][0]
    assert "depend" in result["answer"]
    assert "blast" in result["data"] and "tests" in result["data"]


def test_ask_tests_question_reports_coverage(tmp_path):
    svc = IndexService(rocks_path=tmp_path / "rocks")
    svc.index_repo(ROOT, parallel=False)
    result = ask(svc, "which tests cover parse_config")
    assert result["intent"] == "tests"
    assert "data" in result and "tests" in result["data"]


def test_ask_falls_back_to_semantic_when_no_symbol_resolves(tmp_path):
    svc = IndexService(rocks_path=tmp_path / "rocks")
    svc.index_repo(ROOT, parallel=False)
    result = ask(svc, "find code that reads key value pairs from a string")
    assert result["intent"] == "semantic"
    assert "hits" in result["data"]


def test_ask_scoped_by_org_id(tmp_path):
    svc = IndexService(rocks_path=tmp_path / "rocks")
    svc.index_repo(ROOT, org_id="org_a", repo_id="a", parallel=False)
    result = ask(svc, "what breaks if I change parse_config?", org_id="org_b")
    # org_b never indexed anything — the symbol must not resolve across tenants
    assert result["symbols"] == [] or "parse_config" not in "".join(result["symbols"])
