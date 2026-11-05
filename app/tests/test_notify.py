import json

import responses

from pulse import config, notify


def test_split_message_respects_limit_and_lines():
    text = "\n".join(f"line {i} " + "x" * 50 for i in range(100))
    chunks = notify.split_message(text, limit=500)
    assert all(len(c) <= 500 for c in chunks)
    assert "\n".join(chunks).replace("\n", "") == text.replace("\n", "")


def test_split_message_handles_very_long_line():
    chunks = notify.split_message("a" * 1200, limit=500)
    assert [len(c) for c in chunks] == [500, 500, 200]


def test_slack_formatting():
    md = "## Summary\n**Good** week, see [PR 1](https://github.com/a/b/pull/1)"
    assert notify.to_slack_mrkdwn(md) == "*Summary*\n*Good* week, see <https://github.com/a/b/pull/1|PR 1>"


@responses.activate
def test_notify_sends_discord_in_chunks_and_survives_failing_channel(monkeypatch):
    monkeypatch.setattr(config, "DISCORD_WEBHOOK_URL", "https://discord.test/hook")
    monkeypatch.setattr(config, "SLACK_WEBHOOK_URL", "https://slack.test/hook")
    monkeypatch.setattr(config, "SMTP_HOST", None)
    responses.post("https://discord.test/hook", status=204)
    responses.post("https://slack.test/hook", status=500)

    body = "\n".join("- item " + "y" * 80 for _ in range(60))
    result = notify.notify("Weekly report", body)

    assert result["discord"] == "sent"
    assert result["slack"].startswith("failed")
    discord_calls = [c for c in responses.calls if "discord" in c.request.url]
    assert len(discord_calls) >= 3
    assert all(len(json.loads(c.request.body)["content"]) <= 2000 for c in discord_calls)


def test_no_channels_configured(monkeypatch):
    for name in ("DISCORD_WEBHOOK_URL", "SLACK_WEBHOOK_URL", "SMTP_HOST"):
        monkeypatch.setattr(config, name, None)
    assert notify.notify("t", "b") == {}
