"""Preview and explicitly apply branch-manager contacts from a Gapo snapshot."""

import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core import signing
from django.db import transaction

from app_admindocuments.models import AdmParcelRecipientImportBatch
from .models import Shop
from .shop_manager import validate_shop_manager_contact


CONTACT_FIELDS = ("shop_manager_name", "shop_manager_employee_code", "shop_manager_email")
SALT = "gapo-shop-manager-preview-v1"


def branch_prefix(value):
    match = re.match(r"^([A-Z]{3}[0-9]{5})(?=$|[.\s_-])", (value or "").strip().upper())
    return match.group(1) if match else ""


def _is_manager(value):
    value = unicodedata.normalize("NFD", value.strip().casefold()).replace("đ", "d")
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(value.split()) == "truong phong giao dich"


def manager_preview(batch, *, lock=False):
    """Include blocked rows for review; never infer a manager from a fuzzy name."""
    shops_qs = Shop.objects.order_by("shop_name", "pk")
    people_qs = batch.recipients.order_by("pk")
    if lock:
        shops_qs = shops_qs.select_for_update()
        people_qs = people_qs.select_for_update()
    shops = list(shops_qs.values("pk", "shop_name", "is_shop_active", "for_borrow_only", *CONTACT_FIELDS))
    people = list(people_qs.values(
        "pk", "row_number", "full_name", "employee_code", "email",
        "department_name", "position_name", "is_active_member",
    ))
    fingerprint = hashlib.sha256(json.dumps({
        "batch": [batch.pk, batch.checksum, str(batch.updated_at), str(batch.activated_at),
                  batch.is_current, batch.has_errors],
        "shops": shops, "people": people,
    }, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    shop_groups, candidates = defaultdict(list), defaultdict(list)
    for shop in shops:
        shop_groups[branch_prefix(shop["shop_name"])].append(shop)
    for person in people:
        if person["is_active_member"] and _is_manager(person["position_name"]):
            candidates[branch_prefix(person["department_name"])].append(person)

    rows = []
    for shop in shops:
        prefix = branch_prefix(shop["shop_name"])
        matches = candidates.get(prefix, []) if prefix else []
        row = {
            "shop_id": shop["pk"], "shop_name": shop["shop_name"], "prefix": prefix,
            "before": dict(zip(CONTACT_FIELDS, (shop[field] or "" for field in CONTACT_FIELDS))),
            "after": {}, "candidates": matches, "status": "review", "reason": "",
        }
        if not prefix:
            row["reason"] = "Tên Shop chưa có mã PGD hợp lệ ở đầu."
        elif len(shop_groups[prefix]) > 1:
            row["reason"] = "Nhiều Shop cùng mã PGD; cần xác minh."
        elif not shop["is_shop_active"] or shop["for_borrow_only"]:
            row["reason"] = "PGD ngừng hoạt động hoặc chỉ phục vụ mượn chứng từ."
        elif not matches:
            row["reason"] = "Không tìm thấy Trưởng PGD đang hoạt động."
        elif len(matches) > 1:
            row["reason"] = "Nhiều Trưởng PGD cùng mã; cần xác minh."
        else:
            person = matches[0]
            try:
                contact = validate_shop_manager_contact(person["full_name"], person["employee_code"], person["email"])
                if not all(contact):
                    raise ValueError("Thiếu tên, mã nhân viên hoặc email Trưởng PGD.")
            except ValueError as exc:
                row["reason"] = str(exc)
            else:
                row["after"] = dict(zip(CONTACT_FIELDS, contact))
                if row["after"] == row["before"]:
                    row.update(status="unchanged", reason="Thông tin đã khớp.")
                else:
                    row.update(status="ready", reason="Khớp duy nhất, đủ thông tin.")
        rows.append(row)
    for prefix, matches in sorted(candidates.items()):
        if not prefix or prefix not in shop_groups:
            rows.append({
                "shop_id": None, "shop_name": "Chưa xác định Shop", "prefix": prefix,
                "before": {}, "after": {}, "candidates": matches, "status": "review",
                "reason": "Phòng ban chưa có mã PGD hợp lệ." if not prefix else "Không có Shop tương ứng với mã PGD.",
            })
    return {"batch_id": batch.pk, "rows": rows, "counts": Counter(row["status"] for row in rows), "fingerprint": fingerprint}


def sign_manager_preview(preview, user):
    return signing.dumps({"batch_id": preview["batch_id"], "fingerprint": preview["fingerprint"], "user_id": user.pk}, salt=SALT)


def apply_manager_preview(token, user):
    if not user.is_superuser or not user.is_active:
        raise ValueError("Chỉ super admin đang hoạt động được cập nhật Trưởng PGD.")
    try:
        payload = signing.loads(token, salt=SALT, max_age=1800)
    except signing.BadSignature as exc:
        raise ValueError("Bản đối chiếu hết hạn hoặc không hợp lệ. Vui lòng tải lại trang.") from exc
    if payload.get("user_id") != user.pk:
        raise ValueError("Bản đối chiếu thuộc phiên người dùng khác. Vui lòng tải lại trang.")
    with transaction.atomic():
        batch = AdmParcelRecipientImportBatch.objects.select_for_update().filter(pk=payload.get("batch_id")).first()
        if not batch or not batch.is_current or batch.has_errors:
            raise ValueError("File nguồn không còn hiện hành hoặc có lỗi. Vui lòng đối chiếu lại.")
        preview = manager_preview(batch, lock=True)
        if preview["fingerprint"] != payload.get("fingerprint"):
            raise ValueError("Dữ liệu đã thay đổi sau khi đối chiếu. Vui lòng tải lại trang và kiểm tra trước khi áp dụng.")
        changed = [row for row in preview["rows"] if row["status"] == "ready"]
        content_type = ContentType.objects.get_for_model(Shop)
        for row in changed:
            Shop.objects.filter(pk=row["shop_id"]).update(**row["after"])
            person = row["candidates"][0]
            LogEntry.objects.log_action(
                user_id=user.pk, content_type_id=content_type.pk,
                object_id=row["shop_id"], object_repr=row["shop_name"], action_flag=CHANGE,
                change_message=json.dumps({
                    "source": "gapo_shop_manager_enrichment", "batch_id": batch.pk,
                    "filename": batch.original_name, "checksum": batch.checksum,
                    "source_row": person["row_number"], "recipient_id": person["pk"],
                    "branch_prefix": row["prefix"], "before": row["before"], "after": row["after"],
                }, ensure_ascii=False),
            )
    return len(changed)
