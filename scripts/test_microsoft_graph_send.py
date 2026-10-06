
from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import sys
import uuid
from email.utils import parseaddr
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def email_address(value: str) -> str:
    address = parseaddr(value)[1]
    if not address or "@" not in address:
        raise argparse.ArgumentTypeError(f"Địa chỉ email không hợp lệ: {value!r}")
    return address


def token_claims(token: str) -> dict:
    try:
        encoded = token.split(".")[1]
        encoded += "=" * (-len(encoded) % 4)
        claims = json.loads(base64.urlsafe_b64decode(encoded))
    except (IndexError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("Access token không phải JWT hợp lệ.") from exc
    return {
        "aud": claims.get("aud"),
        "appid": claims.get("appid") or claims.get("azp"),
        "tenant_id": claims.get("tid"),
        "roles": claims.get("roles") or [],
        "scopes": claims.get("scp") or "",
        "expires_at": claims.get("exp"),
    }


def response_body(response: requests.Response):
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return response.text


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Gửi một email kiểm thử bằng Microsoft Graph và in response đầy đủ.",
    )
    result.add_argument("--tenant-id", default=env("MS_TENANT_ID"))
    result.add_argument("--client-id", default=env("MS_APPLICATION_ID"))
    result.add_argument(
        "--mailbox",
        type=email_address,
        default=env("MS_GRAPH_MAILBOX_EMAIL") or env("MS_GRAPH_SENDER_EMAIL") or env("DEFAULT_FROM_EMAIL"),
        help="Mailbox thật dùng trong /users/{mailbox}/sendMail.",
    )
    result.add_argument(
        "--from-address",
        type=email_address,
        default=env("MS_GRAPH_SENDER_EMAIL") or env("DEFAULT_FROM_EMAIL"),
        help="Địa chỉ hiển thị trong message.from.",
    )
    result.add_argument("--to", action="append", type=email_address, required=True)
    result.add_argument("--cc", action="append", type=email_address, default=[])
    result.add_argument("--bcc", action="append", type=email_address, default=[])
    result.add_argument("--subject", default="[TEST] Microsoft Graph email")
    result.add_argument(
        "--html",
        default="<p>Đây là email kiểm thử gửi qua Microsoft Graph.</p>",
    )
    result.add_argument("--timeout", type=float, default=30.0)
    result.add_argument(
        "--dry-run",
        action="store_true",
        help="Chỉ in endpoint và payload, không xin token hoặc gửi email.",
    )
    return result


def main() -> int:
    # Windows may inherit a legacy cp1252 console encoding, which cannot print
    # Vietnamese subjects or Microsoft error messages reliably.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    load_dotenv(PROJECT_ROOT / ".env")
    args = parser().parse_args()

    missing = [
        name
        for name, value in (
            ("MS_TENANT_ID", args.tenant_id),
            ("MS_APPLICATION_ID", args.client_id),
            ("mailbox", args.mailbox),
            ("from-address", args.from_address),
        )
        if not value
    ]
    if missing:
        print(f"Thiếu cấu hình: {', '.join(missing)}", file=sys.stderr)
        return 2

    endpoint = (
        "https://graph.microsoft.com/v1.0/users/"
        f"{quote(args.mailbox, safe='@.')}/sendMail"
    )
    payload = {
        "message": {
            "subject": args.subject,
            "body": {"contentType": "HTML", "content": args.html},
            "from": {"emailAddress": {"address": args.from_address}},
            "toRecipients": [
                {"emailAddress": {"address": address}} for address in args.to
            ],
            "ccRecipients": [
                {"emailAddress": {"address": address}} for address in args.cc
            ],
            "bccRecipients": [
                {"emailAddress": {"address": address}} for address in args.bcc
            ],
        },
        "saveToSentItems": True,
    }

    print("REQUEST")
    print(json.dumps({"method": "POST", "url": endpoint, "json": payload}, ensure_ascii=False, indent=2))
    if args.dry_run:
        print("\nDRY RUN: chưa gửi email.")
        return 0

    client_secret = env("MS_VALUE")
    if not client_secret:
        client_secret = getpass.getpass("Nhập MS_VALUE (ký tự sẽ không hiển thị): ").strip()
    if not client_secret:
        print("Thiếu MS_VALUE (client secret value).", file=sys.stderr)
        return 2

    token_request_id = str(uuid.uuid4())
    token_response = requests.post(
        f"https://login.microsoftonline.com/{quote(args.tenant_id, safe='')}/oauth2/v2.0/token",
        data={
            "client_id": args.client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
        headers={"Accept": "application/json", "client-request-id": token_request_id},
        timeout=args.timeout,
    )
    if token_response.status_code != 200:
        print("\nTOKEN RESPONSE")
        print(json.dumps({
            "status": token_response.status_code,
            "client_request_id": token_request_id,
            "request_id": token_response.headers.get("request-id"),
            "body": response_body(token_response),
        }, ensure_ascii=False, indent=2))
        return 1

    token = token_response.json().get("access_token", "")
    if not token:
        print("Token response không có access_token.", file=sys.stderr)
        return 1
    print("\nTOKEN CLAIMS (đã lược bỏ token)")
    print(json.dumps(token_claims(token), ensure_ascii=False, indent=2))

    client_request_id = str(uuid.uuid4())
    response = requests.post(
        endpoint,
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "client-request-id": client_request_id,
            "return-client-request-id": "true",
        },
        timeout=args.timeout,
    )
    print("\nGRAPH RESPONSE")
    print(json.dumps({
        "status": response.status_code,
        "client_request_id": client_request_id,
        "request_id": response.headers.get("request-id"),
        "date": response.headers.get("date"),
        "body": response_body(response),
    }, ensure_ascii=False, indent=2))

    if response.status_code == 202:
        print("\nGraph đã nhận yêu cầu gửi email (202 Accepted).")
        return 0
    print("\nGraph đã từ chối yêu cầu; gửi toàn bộ phần GRAPH RESPONSE cho IT.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
