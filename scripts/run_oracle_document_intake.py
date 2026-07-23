"""One-off/local runner for the Prefect document transformer.

Production should use the ``oracle_document_intake`` Prefect flow. This runner
is useful for backfills and dev validation; it still writes through HTTP only.
"""
import argparse
import csv
import os
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

from prefect_document_intake import load_catalog, load_oracle_rows, send_batch, transform_rows


def args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--credentials", required=True)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--token", default=os.environ.get("DOCUMENT_INTAKE_TOKEN"))
    parser.add_argument("--run-key", default="backfill-v1")
    parser.add_argument("--rejection-file", default="tmp/oracle_intake_rejections.csv")
    parser.add_argument("--skip-finalize", action="store_true", help="Chỉ dùng khi local không chạy Celery worker.")
    return parser.parse_args()


def main():
    options = args()
    if not options.token:
        raise SystemExit("Thiếu --token hoặc DOCUMENT_INTAKE_TOKEN")
    credential = yaml.safe_load(Path(options.credentials).read_text(encoding="utf-8"))["connectionf88dwh"]
    dsn = credential.get("dns") or f"{credential['host']}:{credential['port']}/{credential['sid']}"
    catalog = load_catalog(options.api_url, options.token)
    start, end = (datetime.strptime(value, "%Y-%m-%d").date() for value in (options.start_date, options.end_date))
    rejection_rows, summaries = [], []
    current = start
    while current <= end:
        raw = load_oracle_rows(current, credential["user"], credential["pass"], dsn)
        records, rejected = transform_rows(raw, catalog, current)
        for item in rejected:
            item["business_date"] = current.isoformat()
        rejection_rows.extend(rejected)
        summary = {"date": current.isoformat(), "oracle_rows": len(raw), "valid": len(records), "rejected": len(rejected)}
        if raw:
            key = f"oracle-documents-{current:%Y%m%d}-{options.run_key}"
            send_batch(options.api_url, options.token, key, current, records, finalize=not options.skip_finalize)
            summary["batch_key"] = key
        summaries.append(summary)
        print(summary, flush=True)
        current += timedelta(days=1)
    if rejection_rows:
        output = Path(options.rejection_file)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=rejection_rows[0].keys())
            writer.writeheader()
            writer.writerows(rejection_rows)
        print(f"Rejection report: {output}")
    print({"days": len(summaries), "valid": sum(x["valid"] for x in summaries), "rejected": sum(x["rejected"] for x in summaries)})


if __name__ == "__main__":
    main()
