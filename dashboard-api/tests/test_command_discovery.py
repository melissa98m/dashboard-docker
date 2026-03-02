"""Command discovery service tests."""

from app.services.command_discovery import discover_commands


class _FakeExecResult:
    def __init__(self, exit_code: int, output):
        self.exit_code = exit_code
        self.output = output


class _DjangoContainer:
    name = "django-api"

    def exec_run(self, cmd, workdir=None, demux=True):  # noqa: ANN001
        assert demux is True
        if cmd == ["cat", "/app/manage.py"]:
            return _FakeExecResult(0, (b"#!/usr/bin/env python", b""))
        if cmd[:3] == ["python", "/app/manage.py", "help"] and workdir == "/app":
            return _FakeExecResult(0, (b"check\nmigrate\nshowmigrations\n", b""))
        if cmd[:3] == ["python3", "/app/manage.py", "help"] and workdir == "/app":
            return _FakeExecResult(1, (b"", b"python3 missing"))
        return _FakeExecResult(1, (b"", b"missing"))


class _SymfonyContainer:
    name = "symfony-api"

    def exec_run(self, cmd, workdir=None, demux=True):  # noqa: ANN001
        assert demux is True
        if cmd == ["cat", "/app/bin/console"]:
            return _FakeExecResult(0, (b"#!/usr/bin/env php", b""))
        if cmd == ["php", "/app/bin/console", "list", "--raw"] and workdir == "/app":
            return _FakeExecResult(0, (b"cache:clear\ncache:warmup\ndebug:router\n", b""))
        return _FakeExecResult(1, (b"", b"missing"))


def test_discover_commands_includes_django_base_and_project_commands():
    service_name, commands = discover_commands(_DjangoContainer())
    assert service_name == "django-api"
    names = {item["name"] for item in commands}
    assert "django:check" in names
    assert "django:migrate" in names
    assert "django:showmigrations" in names
    command_map = {item["name"]: item["argv"] for item in commands}
    assert command_map["django:migrate"] == ["python", "/app/manage.py", "migrate"]


def test_discover_commands_includes_symfony_base_and_listed_commands():
    service_name, commands = discover_commands(_SymfonyContainer())
    assert service_name == "symfony-api"
    names = {item["name"] for item in commands}
    assert "symfony:cache:clear" in names
    assert "symfony:cache:warmup" in names
    assert "symfony:debug:router" in names
