"""CLI for migrations and admin operations."""

import getpass
import sys


def _print_usage() -> None:
    print(
        "Usage: python -m app.cli migrate | purge-audit [days] | "
        "create-user --username <value> [--role admin|viewer] | "
        "unlock-user --username <value>"
    )


def _parse_create_user_args(argv: list[str]) -> tuple[str, str]:
    username = ""
    role = "viewer"
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--username":
            if index + 1 >= len(argv):
                raise ValueError("missing_username")
            username = argv[index + 1]
            index += 2
            continue
        if arg == "--role":
            if index + 1 >= len(argv):
                raise ValueError("missing_role")
            role = argv[index + 1]
            index += 2
            continue
        raise ValueError(f"unknown_option:{arg}")
    if not username:
        raise ValueError("missing_username")
    return username, role


def _handle_create_user(argv: list[str]) -> int:
    try:
        username, role = _parse_create_user_args(argv)
    except ValueError as exc:
        reason = str(exc)
        if reason == "missing_username":
            print("Missing required option: --username")
        elif reason == "missing_role":
            print("Missing value for option: --role")
        elif reason.startswith("unknown_option:"):
            print(f"Unknown option: {reason.split(':', 1)[1]}")
        _print_usage()
        return 1

    password = getpass.getpass("Password: ")
    password_confirmation = getpass.getpass("Confirm password: ")
    if password != password_confirmation:
        print("Password confirmation mismatch.")
        return 1
    if not password:
        print("Password cannot be empty.")
        return 1

    from app.db.auth import create_user

    try:
        created = create_user(username=username, password=password, role=role)
    except ValueError as exc:
        reason = str(exc)
        if reason == "username_taken":
            print("Username already exists.")
        elif reason == "weak_password":
            print("Weak password: minimum 12 chars, with letters and digits.")
        elif reason == "invalid_role":
            print("Invalid role. Allowed values: admin, viewer.")
        elif reason == "invalid_username":
            print("Invalid username. Allowed pattern: 3-120 chars [A-Za-z0-9._-].")
        else:
            print(f"Unable to create user: {reason}")
        return 1

    print(f"User created: id={created['id']} username={created['username']} role={created['role']}")
    return 0


def main() -> None:
    if len(sys.argv) < 2:
        _print_usage()
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "migrate":
        from app.db.init import migrate

        migrate()
        print("Migrations applied.")
    elif cmd == "purge-audit":
        from app.config import settings
        from app.db.audit import purge_audit_logs

        if len(sys.argv) >= 3:
            try:
                days = int(sys.argv[2])
            except ValueError:
                print("days must be an integer")
                sys.exit(1)
        else:
            days = settings.audit_retention_days
        deleted = purge_audit_logs(older_than_days=days)
        print(f"Purged {deleted} audit rows older than {days} days.")
    elif cmd == "create-user":
        exit_code = _handle_create_user(sys.argv[2:])
        if exit_code != 0:
            sys.exit(exit_code)
    elif cmd == "unlock-user":
        if "--username" not in sys.argv or sys.argv.index("--username") + 1 >= len(sys.argv):
            print("Missing --username <value>")
            _print_usage()
            sys.exit(1)
        idx = sys.argv.index("--username") + 1
        username = sys.argv[idx]
        from app.db.auth import reset_user_lockout

        if reset_user_lockout(username=username):
            print(f"Lockout reset for user: {username}")
        else:
            print(f"User not found: {username}")
            sys.exit(1)
    else:
        print(f"Unknown command: {cmd}")
        _print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
