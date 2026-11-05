import pytest

from pulse import ask


class FakeLLM:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.prompts = []

    def __call__(self, system, user, max_tokens=1500):
        self.prompts.append(user)
        return self.answers.pop(0)


def test_extract_sql_from_code_block_or_plain_text():
    assert ask.extract_sql("Here:\n```sql\nSELECT 1\n```\nbye") == "SELECT 1"
    assert ask.extract_sql("SELECT 2") == "SELECT 2"


def test_ask_happy_path(monkeypatch):
    fake = FakeLLM("```sql\nSELECT person, open_prs FROM workload\n```", "Alice has 3 open PRs.")
    monkeypatch.setattr(ask.llm, "complete", fake)
    monkeypatch.setattr(ask, "run_query", lambda sql: (["person", "open_prs"], [["alice", 3]]))

    result = ask.ask("Who has the most open PRs?")

    assert result["answer"] == "Alice has 3 open PRs."
    assert result["rows"] == [["alice", 3]]
    assert result["executed_sql"].endswith("LIMIT 200")
    assert result["attempts"] == []


def test_unsafe_sql_is_never_executed_and_model_gets_feedback(monkeypatch):
    fake = FakeLLM("DELETE FROM pull_requests", "SELECT count(*) AS n FROM pr_metrics", "There are 5.")
    executed = []
    monkeypatch.setattr(ask.llm, "complete", fake)
    monkeypatch.setattr(ask, "run_query", lambda sql: executed.append(sql) or (["n"], [[5]]))

    result = ask.ask("How many PRs?")

    assert len(executed) == 1 and "DELETE" not in executed[0]
    assert "Rejected by the validator" in fake.prompts[1]
    assert len(result["attempts"]) == 1


def test_gives_up_after_max_attempts(monkeypatch):
    monkeypatch.setattr(ask.llm, "complete", FakeLLM("SELECT * FROM pull_requests", "SELECT pg_sleep(9)"))
    monkeypatch.setattr(ask, "run_query", lambda sql: pytest.fail("must not run"))
    result = ask.ask("Show me everything")
    assert "error" in result and len(result["attempts"]) == 2


def test_rejects_empty_and_too_long_questions():
    with pytest.raises(ValueError):
        ask.ask("   ")
    with pytest.raises(ValueError):
        ask.ask("x" * 501)
