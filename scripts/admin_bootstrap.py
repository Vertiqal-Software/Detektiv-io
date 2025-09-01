# scripts/admin_bootstrap.py
from __future__ import annotations

"""
Admin bootstrap CLI

Creates the first admin user idempotently (when there are no users yet), or
optionally forces creation/reset using flags. Safe to run multiple times.

Usage examples:
  # Basic bootstrap using env vars
  ADMIN_EMAIL=admin@example.com ADMIN_PASSWORD='Str0ngP@ss' python -m scripts.admin_bootstrap

  # Or with flags
  python -m scripts.admin_bootstrap --email admin@example.com --password 'Str0ngP@ss' --name 'Site Admin'

  # If users already exist, create/ensure this admin anyway
  python -m scripts.admin_bootstrap --email admin@example.com --password 'Str0ngP@ss' --force

  # Reset password for an existing admin (bumps token_version = revokes tokens)
  python -m scripts.admin_bootstrap --email admin@example.com --password 'NewStr0ngP@ss' --reset-password

Environment variables (used as defaults):
  ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_NAME
Exit codes:
  0  success / no-op (already present)
  1  invalid arguments / runtime error
"""

import argparse
import json
import logging
import os
import sys
from typing import Optional

# ------------------------------------------------------------------------------
# Import project modules, adding the repo root to sys.path if needed
# ------------------------------------------------------------------------------
try:
    # When executed via `python -m scripts.admin_bootstrap`, package imports work.
    from app.core.session import session_scope
    from app.models.user import User
    from app.services.user_service import UserService
except Exception:
    # Fallback: add repository root (parent of 'scripts') to sys.path
    this_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(this_dir, os.pardir))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    # Retry imports
    from app.core.session import session_scope  # type: ignore
    from app.models.user import User  # type: ignore
    from app.services.user_service import UserService  # type: ignore


LOG = logging.getLogger("scripts.admin_bootstrap")


def _setup_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity >= 2:
        level = logging.DEBUG
    elif verbosity == 1:
        level = logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Create or update an admin account")
    p.add_argument(
        "--email", default=os.getenv("ADMIN_EMAIL"), help="Admin email (or ADMIN_EMAIL)"
    )
    p.add_argument(
        "--password",
        default=os.getenv("ADMIN_PASSWORD"),
        help="Admin password (or ADMIN_PASSWORD)",
    )
    p.add_argument(
        "--name",
        default=os.getenv("ADMIN_NAME"),
        help="Admin full name (or ADMIN_NAME)",
    )
    p.add_argument(
        "--tenant-id", type=int, default=None, help="Optional tenant id to assign"
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Create admin even if other users already exist",
    )
    p.add_argument(
        "--reset-password",
        action="store_true",
        help="If user exists, reset its password",
    )
    p.add_argument("--json", action="store_true", help="Emit JSON output")
    p.add_argument(
        "-v", "--verbose", action="count", default=0, help="Increase logging verbosity"
    )
    return p.parse_args(argv)


def _print(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    else:
        status = result.get("status", "unknown")
        msg = result.get("message", "")
        if msg:
            print(f"{status}: {msg}")
        else:
            print(status)


def _normalize_email(value: Optional[str]) -> str:
    if not value:
        return ""
    return value.strip().lower()


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    _setup_logging(args.verbose)

    email = _normalize_email(args.email)
    password = (args.password or "").strip()
    full_name = args.name or None
    tenant_id = args.tenant_id

    if not email:
        _print(
            {"status": "error", "message": "Missing --email or ADMIN_EMAIL"}, args.json
        )
        return 1

    # For initial bootstrap, a password is required unless only counting users.
    if not password and (args.force or args.reset_password or True):
        # We allow missing password only when we will *not* create or reset.
        # But since the standard flow creates the first admin, require it.
        # If there are already users and no --force/--reset, we won't use it.
        pass

    try:
        with session_scope() as db:
            svc = UserService(db)

            total_users = db.query(User).count()
            LOG.debug("Existing user count: %s", total_users)

            if total_users == 0:
                # True bootstrap path (idempotent): create the very first admin.
                if not password:
                    _print(
                        {
                            "status": "error",
                            "message": "Password required to create first admin",
                        },
                        args.json,
                    )
                    return 1

                created = svc.ensure_initial_admin(
                    email=email, password=password, full_name=full_name
                )
                if created is None:
                    # A concurrent creator may have raced; treat as success.
                    existing = svc.get_by_email(email)
                    if existing:
                        _print(
                            {
                                "status": "ok",
                                "message": "Admin already exists (race)",
                                "user_id": existing.id,
                                "email": existing.email,
                            },
                            args.json,
                        )
                        return 0
                    _print(
                        {"status": "ok", "message": "Users already present (no-op)"},
                        args.json,
                    )
                    return 0

                # Optionally assign tenant if requested
                if tenant_id is not None:
                    created.tenant_id = tenant_id
                    db.add(created)
                    db.commit()
                    db.refresh(created)

                _print(
                    {
                        "status": "created",
                        "message": "Initial admin created",
                        "user_id": created.id,
                        "email": created.email,
                    },
                    args.json,
                )
                return 0

            # Reaching here means users already exist
            existing = svc.get_by_email(email)

            if args.reset_password:
                if not existing:
                    _print(
                        {
                            "status": "error",
                            "message": "User not found for --reset-password",
                        },
                        args.json,
                    )
                    return 1
                if not password:
                    _print(
                        {
                            "status": "error",
                            "message": "Password required for --reset-password",
                        },
                        args.json,
                    )
                    return 1
                svc.set_password(existing, password, bump_token_version=True)
                _print(
                    {
                        "status": "updated",
                        "message": "Password reset and tokens revoked",
                        "user_id": existing.id,
                        "email": existing.email,
                    },
                    args.json,
                )
                return 0

            if args.force:
                if existing:
                    # Ensure flags are admin-ish; do not downgrade silently
                    changed = False
                    if not existing.is_active:
                        existing.is_active = True
                        changed = True
                    if not existing.is_superuser:
                        existing.is_superuser = True
                        changed = True
                    if getattr(existing, "role", None) != "admin":
                        existing.role = "admin"  # type: ignore[assignment]
                        changed = True
                    if (
                        tenant_id is not None
                        and getattr(existing, "tenant_id", None) != tenant_id
                    ):
                        existing.tenant_id = tenant_id  # type: ignore[assignment]
                        changed = True
                    if changed:
                        db.add(existing)
                        db.commit()
                        db.refresh(existing)
                        _print(
                            {
                                "status": "ok",
                                "message": "Existing admin ensured/updated",
                                "user_id": existing.id,
                                "email": existing.email,
                            },
                            args.json,
                        )
                    else:
                        _print(
                            {
                                "status": "ok",
                                "message": "Admin already present and up-to-date",
                                "user_id": existing.id,
                                "email": existing.email,
                            },
                            args.json,
                        )
                    return 0

                # Create new admin alongside existing users (explicit force)
                if not password:
                    _print(
                        {
                            "status": "error",
                            "message": "Password required for --force create",
                        },
                        args.json,
                    )
                    return 1
                payload = {
                    "email": email,
                    "password": password,
                    "full_name": full_name,
                    "role": "admin",
                    "is_active": True,
                    "is_superuser": True,
                    "tenant_id": tenant_id,
                }
                created2 = svc.create(
                    type("UserCreateLike", (), payload)()
                )  # quick shim; service uses attribute access
                _print(
                    {
                        "status": "created",
                        "message": "Admin created (force)",
                        "user_id": created2.id,
                        "email": created2.email,
                    },
                    args.json,
                )
                return 0

            # No force and users exist → no-op, but surface info about the requested email.
            if existing:
                _print(
                    {
                        "status": "ok",
                        "message": "Users exist; matching user already present",
                        "user_id": existing.id,
                        "email": existing.email,
                    },
                    args.json,
                )
            else:
                _print(
                    {"status": "ok", "message": "Users exist; no changes made"},
                    args.json,
                )
            return 0

    except Exception as e:
        LOG.exception("admin_bootstrap error: %s", e)
        _print({"status": "error", "message": str(e)}, args.json)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
