"""Manage accounts from the command line on the server.

  uv run python -m fantasy.auth create-admin you@example.com   asks for a password (twice)
  uv run python -m fantasy.auth invite friend@example.com      prints the one-time link to send
  uv run python -m fantasy.auth list

create-admin on an existing email resets that password and signs the account out everywhere.
"""

import argparse
import getpass
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime

from fantasy.auth import accounts
from fantasy.config import load_config


def _site_url() -> str:
    """The public address, from the host list the server already has (API_ALLOWED_HOSTS)."""
    hosts = [h.strip() for h in os.environ.get("API_ALLOWED_HOSTS", "").split(",") if h.strip()]
    return f"https://{hosts[0]}" if hosts else "https://<your site>"


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m fantasy.auth", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("create-admin").add_argument("email")
    commands.add_parser("invite").add_argument("email")
    commands.add_parser("list")
    args = parser.parse_args(argv)
    with accounts.open_db() as conn:
        if args.command == "create-admin":
            password = getpass.getpass("Password: ")
            if getpass.getpass("Again: ") != password:
                print("The two passwords differ.", file=sys.stderr)
                return 1
            try:
                admin_id = accounts.create_admin(conn, args.email, password)
            except ValueError as err:
                print(err, file=sys.stderr)
                return 1
            accounts.set_sleeper_user(conn, admin_id, load_config().user_id)  # the owner's team
            print(f"Admin {accounts.normalize_email(args.email)} is ready.")
        elif args.command == "invite":
            token = accounts.create_invite(conn, args.email, datetime.now(UTC))
            print(f"Send this link (valid {accounts.INVITE_DAYS} days, one use):")
            print(f"{_site_url()}/invite/{token}")
        else:
            for account in accounts.list_accounts(conn, datetime.now(UTC)):
                role = "admin" if account["is_admin"] else "user"
                state = "active" if account["has_password"] else "invited"
                print(f"{account['email']}\t{role}\t{state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
