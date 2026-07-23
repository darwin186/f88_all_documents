"""Local/backfill runner for the Oracle orgchart master-data intake flow."""
import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prefect_document_master_data import (  # noqa: E402
    load_oracle_orgchart,
    send_master_snapshot,
    transform_orgchart,
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--credentials", required=True)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--target-month", required=True, help="YYYY-MM")
    parser.add_argument("--token", default=os.environ.get("DOCUMENT_INTAKE_TOKEN"))
    parser.add_argument("--run-key", default="monthly")
    parser.add_argument("--rejection-file", default="tmp/oracle_master_data_rejections.csv")
    parser.add_argument("--skip-finalize", action="store_true")
    parser.add_argument(
        "--keep-missing-shops-active",
        action="store_true",
        help="Không deactivate PGD vắng khỏi snapshot (chỉ dùng khi chạy kiểm tra/partial).",
    )
    return parser.parse_args()


def main():
    options = parse_args()
    if not options.token:
        raise SystemExit("Thiếu --token hoặc DOCUMENT_INTAKE_TOKEN")
    target_month = datetime.strptime(options.target_month, "%Y-%m").date().replace(day=1)
    credential = yaml.safe_load(
        Path(options.credentials).read_text(encoding="utf-8")
    )["connectionf88dwh"]
    dsn = credential.get("dns") or f"{credential['host']}:{credential['port']}/{credential['sid']}"
    raw = load_oracle_orgchart(
        target_month, credential["user"], credential["pass"], dsn
    )
    records, rejected = transform_orgchart(
        raw, deactivate_missing_shops=not options.keep_missing_shops_active
    )
    if rejected:
        output = Path(options.rejection_file)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=["shop_code", "reason"])
            writer.writeheader()
            writer.writerows(rejected)
        raise SystemExit(
            f"Snapshot không được gửi: {len(rejected)} dòng lỗi. Xem {output}"
        )
    batch_key = f"oracle-orgchart-{target_month:%Y%m}-{options.run_key}"
    result = send_master_snapshot(
        options.api_url,
        options.token,
        batch_key,
        target_month,
        records,
        finalize=not options.skip_finalize,
    )
    print({
        "batch_key": batch_key,
        "oracle_rows": len(raw),
        "shop_rows": len(records) - 1,
        "result": result,
    })


if __name__ == "__main__":
    main()

