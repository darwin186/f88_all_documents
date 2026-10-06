import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# Đọc trực tiếp từ nhóm GRAPH API SETTINGS trong .env.
TENANT_ID = (os.getenv("MS_TENANT_ID") or "").strip()
CLIENT_ID = (os.getenv("MS_APPLICATION_ID") or "").strip()
CLIENT_SECRET = (os.getenv("MS_VALUE") or "").strip()
MAILBOX = (os.getenv("MS_GRAPH_MAILBOX_EMAIL") or "vanhanh_chungtu@f88.vn").strip()
FROM_EMAIL = (os.getenv("MS_GRAPH_TEST_FROM_EMAIL") or MAILBOX).strip()
TO_EMAIL = (os.getenv("MS_GRAPH_TEST_TO_EMAIL") or "datnm@f88.vn").strip()

missing = [
    name
    for name, value in (
        ("MS_TENANT_ID", TENANT_ID),
        ("MS_APPLICATION_ID", CLIENT_ID),
        ("MS_VALUE", CLIENT_SECRET),
    )
    if not value
]
if missing:
    raise SystemExit("Thiếu biến trong .env: " + ", ".join(missing))

token_response = requests.post(
    f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token",
    data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    },
    timeout=30,
)

if token_response.status_code != 200:
    print("TOKEN ERROR:", token_response.status_code, token_response.text)
    raise SystemExit(1)

payload = {
    "message": {
        "subject": "[TEST] Microsoft Graph",
        "body": {
            "contentType": "HTML",
            "content": f"<p>Test Graph: {FROM_EMAIL} gửi tới {TO_EMAIL}</p>",
        },
        "from": {"emailAddress": {"address": FROM_EMAIL}},
        "toRecipients": [
            {"emailAddress": {"address": TO_EMAIL}},
        ],
    },
    "saveToSentItems": True,
}

response = requests.post(
    f"https://graph.microsoft.com/v1.0/users/{MAILBOX}/sendMail",
    headers={
        "Authorization": f"Bearer {token_response.json()['access_token']}",
        "Content-Type": "application/json",
    },
    json=payload,
    timeout=30,
)

print("HTTP STATUS:", response.status_code)
print("REQUEST ID:", response.headers.get("request-id"))
print("RESPONSE:", response.text or "<empty body>")
print("PAYLOAD:", json.dumps(payload, ensure_ascii=False, indent=2))

if response.status_code == 202:
    print("SUCCESS: Graph đã nhận yêu cầu gửi email.")
else:
    print("FAILED: Gửi kết quả trên cho IT kiểm tra.")
