"""
Server commands, run inside the container:

    docker exec -it current python -m app.cli clear-lock <username>

clear-lock      Lets the account sign in from a new device again while
                sign-in is paused after wrong passwords (services/lockout.py).
                The owner and household admins can also do this in Account
                security.
reset-password  Sets a new password for an account (asked twice, not shown),
                signs it out everywhere and lifts any pause. With --link it
                prints a one-time reset link (an hour) instead, for when the
                terminal can't take typing (no -it). The only way to reset the
                instance owner; admins and members can also get a reset link
                in Account security (services/password_resets.py).

    docker exec -it current python -m app.cli reset-password <username>
"""
import argparse
import getpass
import sys

from app.database import SessionLocal, engine
from app.migrations import run_lightweight_migrations


def clear_lock(username: str) -> int:
    from app.models import LoginAuditLog, User
    from app.services import lockout

    with SessionLocal() as db:
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            print(f"No account named {username!r}.")
            return 1
        lockout.clear(db, user)
        db.add(LoginAuditLog(user_id=user.id, username_attempted="server command", event="lock_cleared",
                             ip_address="server", user_agent="app.cli"))
        db.commit()
    print(f"{username} can sign in from new devices again.")
    return 0


def reset_password(username: str, link: bool = False) -> int:
    from app.models import LoginAuditLog, User
    from app.services import password_resets

    with SessionLocal() as db:
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            print(f"No account named {username!r}.")
            return 1
        if not user.is_active:
            print(f"{username}'s account is turned off. A household admin can turn it back on first.")
            return 1
        if link:
            row, token = password_resets.create(db, user, created_by_id=None)
            db.add(LoginAuditLog(user_id=user.id, username_attempted="server command", event="reset_link_created",
                                 ip_address="server", user_agent="app.cli"))
            db.commit()
            address = password_resets.url(db, token)
            print(f"One-time reset link for {username}, valid for an hour:")
            print(address or f"  <your Current address>/?reset={token}")
            return 0
        if not sys.stdin.isatty():
            print("Run this with docker exec -it so the password can be typed, or add --link for a reset link.")
            return 2
        first = getpass.getpass(f"New password for {username}: ")
        if first != getpass.getpass("Type it again: "):
            print("Those didn't match. Nothing changed.")
            return 1
        try:
            password_resets.set_password(db, user, first)
        except password_resets.ResetError as e:
            print(f"{e} Nothing changed.")
            return 1
        db.add(LoginAuditLog(user_id=user.id, username_attempted="server command", event="password_reset",
                             ip_address="server", user_agent="app.cli"))
        db.commit()
    print(f"{username}'s password is set and every device is signed out. Two-step verification is unchanged.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Current server commands.")
    commands = parser.add_subparsers(dest="command", required=True)
    clear = commands.add_parser("clear-lock", help="let an account sign in from new devices again")
    clear.add_argument("username")
    reset = commands.add_parser("reset-password", help="set a new password for an account")
    reset.add_argument("username")
    reset.add_argument("--link", action="store_true", help="print a one-time reset link instead")
    args = parser.parse_args(argv)
    run_lightweight_migrations(engine)
    if args.command == "clear-lock":
        return clear_lock(args.username)
    if args.command == "reset-password":
        return reset_password(args.username, link=args.link)
    return 2


if __name__ == "__main__":
    sys.exit(main())
