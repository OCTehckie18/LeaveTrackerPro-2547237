"""Operator commands:  python -m app.cli seed   |   python -m app.cli create-user ..."""

import argparse
import getpass

from sqlalchemy import select

from app.adapters.blobstore import build_blobstore
from app.core.config import get_settings
from app.core.security import hash_password, validate_new_password
from app.db import get_session_factory
from app.domain.types import Role
from app.models import User
from app.seed import seed


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed", help="load demo users and sample requests (needs DEMO_MODE=true)")
    cu = sub.add_parser("create-user", help="create a real user (there is no self-signup)")
    cu.add_argument("--email", required=True)
    cu.add_argument("--name", required=True)
    cu.add_argument("--role", required=True, choices=[r.value for r in Role])
    cu.add_argument("--manager-email", help="required for EMPLOYEE and MANAGER")
    args = parser.parse_args()

    settings = get_settings()
    with get_session_factory()() as session:
        if args.cmd == "seed":
            print(seed(session, build_blobstore(settings)))
            return
        manager_id = None
        if args.manager_email:
            manager = session.scalar(select(User).where(User.email == args.manager_email))
            if manager is None:
                raise SystemExit(f"No user with email {args.manager_email}")
            manager_id = manager.id
        elif args.role != Role.HOD.value:
            raise SystemExit("--manager-email is required for EMPLOYEE and MANAGER")
        password = getpass.getpass("Password (12+ characters): ")
        validate_new_password(password, args.email)
        session.add(
            User(
                email=args.email, name=args.name, role=args.role, manager_id=manager_id,
                password_hash=hash_password(password),
            )
        )  # fmt: skip
        session.commit()
        print(f"Created {args.role} {args.email}")


if __name__ == "__main__":
    main()
