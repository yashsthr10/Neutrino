"""CLI: neutrino-auth list|set|remove."""

from __future__ import annotations

import argparse
import getpass
import sys

from src.credentials.env import KIND_FOR_PROVIDER
from src.credentials.errors import CredentialError
from src.credentials.manager import CredentialManager
from src.credentials.models import KNOWN_PROVIDERS, CredentialRecord
from src.credentials.store import default_store


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="neutrino-auth",
        description="Manage Neutrino inference credentials (never printed in list).",
    )
    parser.add_argument("--profile", default="default", help="Credential profile name")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="Show which providers have credentials configured")

    p_set = sub.add_parser("set", help="Store a credential interactively")
    p_set.add_argument("provider_id", choices=KNOWN_PROVIDERS)

    p_rm = sub.add_parser("remove", help="Delete a stored credential")
    p_rm.add_argument("provider_id", choices=KNOWN_PROVIDERS)

    args = parser.parse_args(argv)
    mgr = CredentialManager(store=default_store())

    try:
        if args.cmd == "list":
            _cmd_list(mgr, args.profile)
        elif args.cmd == "set":
            _cmd_set(mgr, args.provider_id, args.profile)
        elif args.cmd == "remove":
            mgr.delete(args.provider_id, profile=args.profile)
            print(f"Removed {args.profile}:{args.provider_id}")
    except CredentialError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def _cmd_list(mgr: CredentialManager, profile: str) -> None:
    print(f"Profile: {profile}")
    print("Configured Providers")
    print()
    for st in mgr.list_status(profile=profile):
        mark = "[x]" if st.configured else "[ ]"
        src = f" ({st.source})" if st.source else ""
        print(f"{mark} {st.provider_id}{src}")


def _cmd_set(mgr: CredentialManager, provider_id: str, profile: str) -> None:
    kind = KIND_FOR_PROVIDER.get(provider_id, "api_key")
    fields: dict[str, str] = {}
    if kind == "aws":
        print("Bedrock credentials (leave blank to rely on AWS profile/env chain).")
        access = getpass.getpass("AWS Access Key ID (blank to skip): ").strip()
        if not access:
            print("No keys stored. Set aws_profile in config to use the AWS chain.")
            return
        secret = getpass.getpass("AWS Secret Access Key: ").strip()
        session = getpass.getpass("AWS Session Token (optional): ").strip()
        fields = {"access_key_id": access, "secret_access_key": secret}
        if session:
            fields["session_token"] = session
        record = CredentialRecord(kind="aws", fields=fields)
    elif kind == "azure":
        key = getpass.getpass("Azure OpenAI API Key: ").strip()
        if not key:
            raise SystemExit("api key required")
        record = CredentialRecord(kind="azure", fields={"api_key": key})
    else:
        key = getpass.getpass(f"{provider_id} API Key: ").strip()
        if not key:
            raise SystemExit("api key required")
        record = CredentialRecord(kind="api_key", fields={"api_key": key})
    mgr.set(provider_id, record, profile=profile)
    print(f"Stored credential for {profile}:{provider_id}")


if __name__ == "__main__":
    main()
