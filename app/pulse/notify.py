from __future__ import annotations

import logging
import re
import smtplib
from email.message import EmailMessage

import markdown as md_lib
import requests

from pulse import config

log = logging.getLogger(__name__)

DISCORD_LIMIT = 1900


def split_message(text: str, limit: int = DISCORD_LIMIT) -> list[str]:
    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) > limit:
            chunks.append(current)
            current = ""
        current += line
    if current.strip():
        chunks.append(current)
    return [c.rstrip("\n") for c in chunks]


def to_slack_mrkdwn(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"<\2|\1>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    text = re.sub(r"^#{1,6}\s*(.+)$", r"*\1*", text, flags=re.MULTILINE)
    return text


def send_discord(title: str, body: str) -> None:
    for chunk in split_message(f"**{title}**\n\n{body}"):
        requests.post(config.DISCORD_WEBHOOK_URL, json={"content": chunk}, timeout=15).raise_for_status()


def send_slack(title: str, body: str) -> None:
    text = to_slack_mrkdwn(f"*{title}*\n\n{body}")
    requests.post(config.SLACK_WEBHOOK_URL, json={"text": text}, timeout=15).raise_for_status()


def send_email(title: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = title
    msg["From"] = config.EMAIL_FROM
    msg["To"] = ", ".join(config.EMAIL_TO)
    msg.set_content(body)
    msg.add_alternative(md_lib.markdown(body, extensions=["tables"]), subtype="html")
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as smtp:
        smtp.starttls()
        if config.SMTP_USER:
            smtp.login(config.SMTP_USER, config.SMTP_PASSWORD or "")
        smtp.send_message(msg)


def configured_channels() -> dict[str, callable]:
    channels = {}
    if config.DISCORD_WEBHOOK_URL:
        channels["discord"] = send_discord
    if config.SLACK_WEBHOOK_URL:
        channels["slack"] = send_slack
    if config.SMTP_HOST and config.EMAIL_TO:
        channels["email"] = send_email
    return channels


def notify(title: str, body: str) -> dict[str, str]:
    results = {}
    for name, send in configured_channels().items():
        try:
            send(title, body)
            results[name] = "sent"
        except Exception as exc:
            log.error("Sending report to %s failed: %s", name, exc)
            results[name] = f"failed: {exc}"
    if not results:
        log.info("No notification channel configured - report only saved to file and database.")
    return results
