#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import HTTPException

from geovis_lm.dashboard.operations import (
    ACCOUNT_ROLES,
    DashboardConfig,
    ensure_storage,
    provision_user,
    public_user,
    set_user_active,
    set_user_password,
)


def password_prompt() -> str:
    password = getpass.getpass("Password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")
    return password


def parser() -> argparse.ArgumentParser:
    command_parser = argparse.ArgumentParser(description="Manage first-party GeoVisLM accounts offline.")
    commands = command_parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="Provision an account while public signup remains disabled.")
    create.add_argument("--email", required=True)
    create.add_argument("--display-name", default="")
    create.add_argument("--role", choices=sorted(ACCOUNT_ROLES), default="owner")

    reset = commands.add_parser("reset-password", help="Replace an account password.")
    reset.add_argument("--email", required=True)

    for command in ("activate", "deactivate"):
        account_state = commands.add_parser(command, help=f"{command.title()} an account.")
        account_state.add_argument("--email", required=True)

    return command_parser


def main() -> None:
    args = parser().parse_args()
    config = DashboardConfig.from_env()
    ensure_storage(config)

    try:
        if args.command == "create":
            user = provision_user(
                config,
                args.email,
                password_prompt(),
                display_name=args.display_name,
                role=args.role,
            )
        elif args.command == "reset-password":
            user = set_user_password(config, args.email, password_prompt())
        else:
            user = set_user_active(config, args.email, args.command == "activate")
    except HTTPException as exc:
        raise SystemExit(str(exc.detail)) from exc

    account = public_user(user)
    print(f"{args.command}: {account['email']} ({account['role']}), active={account['active']}")


if __name__ == "__main__":
    main()
