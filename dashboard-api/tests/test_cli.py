"""CLI tests for app.cli commands."""

import sys

import pytest

from app import cli


def test_create_user_cli_success(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    monkeypatch.setattr(
        sys,
        "argv",
        ["app.cli", "create-user", "--username", "alice", "--role", "admin"],
    )
    prompts: list[str] = []

    def fake_getpass(prompt: str) -> str:
        prompts.append(prompt)
        return "StrongPass1234"

    def fake_create_user(*, username: str, password: str, role: str) -> dict[str, object]:
        assert username == "alice"
        assert password == "StrongPass1234"
        assert role == "admin"
        return {"id": 7, "username": "alice", "role": "admin"}

    monkeypatch.setattr(cli.getpass, "getpass", fake_getpass)
    monkeypatch.setattr("app.db.auth.create_user", fake_create_user)

    cli.main()

    out = capsys.readouterr().out
    assert "User created: id=7 username=alice role=admin" in out
    assert prompts == ["Password: ", "Confirm password: "]


def test_create_user_cli_rejects_password_mismatch(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr(
        sys,
        "argv",
        ["app.cli", "create-user", "--username", "alice"],
    )
    answers = iter(["StrongPass1234", "StrongPass12345"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: next(answers))

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "Password confirmation mismatch." in out


def test_create_user_cli_requires_username(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr(sys, "argv", ["app.cli", "create-user"])
    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "Missing required option: --username" in out
