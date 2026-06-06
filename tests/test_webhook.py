from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from meridian.api import routes_tasks
from meridian.persistence.db import get_session


class _FakeSession:
    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None


async def _yield_session() -> Any:
    yield _FakeSession()


@pytest.fixture
def store() -> dict[tuple[str, str], str]:
    return {}


@pytest.fixture
def client(monkeypatch, store) -> TestClient:
    app = FastAPI()
    app.include_router(routes_tasks.webhook_router)
    app.state.redis = object()  # never reached by the fakes
    app.dependency_overrides[get_session] = _yield_session

    class _Task:
        def __init__(self, task_id: str) -> None:
            self.id = task_id

    async def fake_submit(session, redis, *, repo, issue_ref, goal):  # noqa: ANN001
        tid = f"task-{len(store)}"
        store[(repo, issue_ref)] = tid
        return tid

    async def fake_get_by_ref(session, *, repo, issue_ref):  # noqa: ANN001
        tid = store.get((repo, issue_ref))
        return _Task(tid) if tid else None

    monkeypatch.setattr(routes_tasks, "submit_task", fake_submit)
    monkeypatch.setattr(routes_tasks, "get_task_by_ref", fake_get_by_ref)
    return TestClient(app)


def _issue_payload(action: str = "opened", number: int = 7) -> dict:
    return {
        "action": action,
        "repository": {"clone_url": "https://github.com/acme/repo.git"},
        "issue": {"number": number, "title": "Bug", "body": "fix it"},
    }


def test_webhook_ignores_non_issues_event(client, store) -> None:
    r = client.post("/webhook/github", json={"zen": "x"}, headers={"X-GitHub-Event": "push"})
    assert r.status_code == 200
    assert not store


def test_webhook_ignores_non_opened_action(client, store) -> None:
    r = client.post(
        "/webhook/github",
        json=_issue_payload(action="closed"),
        headers={"X-GitHub-Event": "issues"},
    )
    assert r.status_code == 200
    assert not store


def test_webhook_creates_task_for_opened_issue(client, store) -> None:
    r = client.post(
        "/webhook/github", json=_issue_payload(), headers={"X-GitHub-Event": "issues"}
    )
    assert r.status_code == 200
    assert r.json()["status"] == "queued"
    assert store


def test_webhook_rejects_invalid_signature(client, monkeypatch) -> None:
    from meridian.config import Settings, get_settings

    get_settings.cache_clear()
    monkeypatch.setattr(
        "meridian.api.routes_tasks.get_settings",
        lambda: Settings(github_webhook_secret="topsecret"),
    )
    r = client.post(
        "/webhook/github",
        json=_issue_payload(),
        headers={"X-GitHub-Event": "issues", "X-Hub-Signature-256": "sha256=bad"},
    )
    assert r.status_code == 401


def test_webhook_idempotent(client, store) -> None:
    payload = _issue_payload()
    headers = {"X-GitHub-Event": "issues"}
    first = client.post("/webhook/github", json=payload, headers=headers)
    second = client.post("/webhook/github", json=payload, headers=headers)
    assert first.json()["status"] == "queued"
    assert second.json()["status"] == "already_queued"


def test_webhook_accepts_valid_signature(client, monkeypatch, store) -> None:
    from meridian.config import Settings

    secret = "topsecret"
    monkeypatch.setattr(
        "meridian.api.routes_tasks.get_settings",
        lambda: Settings(github_webhook_secret=secret),
    )
    body = json.dumps(_issue_payload()).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    r = client.post(
        "/webhook/github",
        content=body,
        headers={
            "X-GitHub-Event": "issues",
            "X-Hub-Signature-256": sig,
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 200
    assert r.json()["status"] == "queued"
