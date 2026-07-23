"""Idempotent, staged ingestion for data sent by the data-cleaning platform.

The public HTTP handlers only write chunks to staging.  This module is invoked
by Celery after ``finalize`` so retries never repeat a partially written batch.
"""
from collections import Counter
from datetime import date

from django.db import connection, transaction
from django.db.models import Max, Q
from django.utils import timezone

from .models import (
    AreaManager, BusinessType, ContractDetail, DocumentType, DocumentsDetail,
    ExternalDocumentIntakeBatch, ExternalDocumentIntakeRejection, Employee, Folder,
    FolderGroup, FolderStatus, FolderType, Gender, LoanCustomer, LoanDetail, Manager,
    Region, RegionManager, Shop,
)


def _as_date(value):
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _reject(batch, chunk, row_no, record, code, message):
    safe_record = dict(record)
    for field in ("customer_code", "customer_name", "employee_code", "employee_name"):
        if field in safe_record:
            safe_record[field] = "[REDACTED]"
    ExternalDocumentIntakeRejection.objects.create(
        batch=batch, chunk=chunk, row_no=row_no,
        source_record_id=str(record.get("source_record_id", ""))[:100],
        error_code=code, message=message, raw_record=safe_record,
    )


def _clean(value):
    return str(value or "").strip()


def _process_orgchart_snapshot(batch, records):
    """Apply one complete Oracle orgchart snapshot atomically.

    Missing shops are deactivated only when an explicit manifest confirms that
    Prefect sent the complete snapshot and every row passed validation.
    """
    manifests = [(chunk, row_no, record) for chunk, row_no, record in records
                 if isinstance(record, dict) and record.get("entity") == "orgchart_snapshot"]
    rows = [(chunk, row_no, record) for chunk, row_no, record in records
            if not (isinstance(record, dict) and record.get("entity") == "orgchart_snapshot")]
    rejected = 0
    valid = []
    seen_shop_codes = set()
    if len(manifests) != 1:
        chunk, row_no, record = (records[0] if records else (None, 1, {}))
        rejected += 1
        _reject(batch, chunk, row_no, record if isinstance(record, dict) else {},
                "INVALID_ORGCHART_SNAPSHOT", "Batch phải có đúng một entity=orgchart_snapshot")
    manifest = manifests[0][2] if len(manifests) == 1 else {}
    if manifest and manifest.get("snapshot_complete") is not True:
        chunk, row_no, record = manifests[0]
        rejected += 1
        _reject(batch, chunk, row_no, record, "INVALID_ORGCHART_SNAPSHOT",
                "snapshot_complete phải là true")

    regions = {x.region_code: x for x in Region.objects.all()}
    genders = {x.description.casefold(): x for x in Gender.objects.all()}
    for chunk, row_no, record in rows:
        try:
            if not isinstance(record, dict) or record.get("entity") != "orgchart_shop":
                raise ValueError("Snapshot chỉ hỗ trợ entity=orgchart_shop")
            shop_code = int(record["shop_code"])
            if shop_code <= 0 or shop_code > 32767:
                raise ValueError("shop_code phải nằm trong khoảng 1..32767")
            if shop_code in seen_shop_codes:
                raise ValueError("shop_code bị lặp trong snapshot")
            seen_shop_codes.add(shop_code)
            required = {
                "shop_name": _clean(record.get("shop_name")),
                "manager_code": _clean(record.get("manager_code")),
                "region_manager_code": _clean(record.get("region_manager_code")),
                "region_manager_name": _clean(record.get("region_manager_name")),
                "area_manager_code": _clean(record.get("area_manager_code")),
                "area_manager_name": _clean(record.get("area_manager_name")),
                "region_code": _clean(record.get("region_code")),
            }
            missing = [field for field, value in required.items() if not value]
            if missing:
                raise ValueError(f"Thiếu trường bắt buộc: {', '.join(missing)}")
            length_limits = {
                "shop_name": 255, "manager_code": 100,
                "region_manager_code": 10, "region_manager_name": 255,
                "area_manager_code": 10, "area_manager_name": 255,
                "region_code": 10,
            }
            too_long = [
                field for field, limit in length_limits.items()
                if len(required[field]) > limit
            ]
            if too_long:
                raise ValueError(f"Trường vượt quá độ dài cho phép: {', '.join(too_long)}")
            for email_field in ("region_manager_email", "area_manager_email"):
                if len(_clean(record.get(email_field))) > 100:
                    raise ValueError(f"{email_field} vượt quá 100 ký tự")
            region = regions.get(required["region_code"])
            if not region:
                raise ValueError(f"Không tìm thấy region_code={required['region_code']}")
            status = _clean(record.get("status")).lower()
            if status not in {"active", "closed"}:
                raise ValueError("status chỉ nhận active hoặc closed")
            closed_date = _as_date(record["shop_closed_date"]) if record.get("shop_closed_date") else None
            valid.append({
                **required,
                "shop_code": shop_code,
                "region": region,
                "region_manager_email": _clean(record.get("region_manager_email")) or None,
                "area_manager_email": _clean(record.get("area_manager_email")) or None,
                "region_manager_gender": genders.get(_clean(record.get("region_manager_gender")).casefold()),
                "area_manager_gender": genders.get(_clean(record.get("area_manager_gender")).casefold()),
                "status": status,
                "shop_closed_date": closed_date,
            })
        except (KeyError, TypeError, ValueError) as exc:
            rejected += 1
            _reject(batch, chunk, row_no, record if isinstance(record, dict) else {},
                    "INVALID_ORGCHART_ROW", str(exc))

    # A partial or invalid snapshot must not change any production master data.
    if rejected:
        return {
            "created": 0, "updated": 0, "rejected": rejected,
            "snapshot_applied": False, "deactivated_missing": 0,
        }

    region_manager_payloads = {}
    area_manager_payloads = {}
    for row in valid:
        region_manager_payloads.setdefault(row["region_manager_code"], row)
        area_manager_payloads.setdefault(row["area_manager_code"], row)
    existing_region_managers = {
        x.regionManager_code: x for x in RegionManager.objects.filter(
            regionManager_code__in=region_manager_payloads
        )
    }
    existing_area_managers = {
        x.areaManager_code: x for x in AreaManager.objects.filter(
            areaManager_code__in=area_manager_payloads
        )
    }
    RegionManager.objects.bulk_create([
        RegionManager(
            regionManager_code=code,
            regionManager_name=row["region_manager_name"],
            regionManager_email=row["region_manager_email"],
            gender=row["region_manager_gender"],
            is_active=True,
        )
        for code, row in region_manager_payloads.items()
        if code not in existing_region_managers
    ], ignore_conflicts=True, batch_size=500)
    missing_area_manager_rows = [
        (code, row) for code, row in area_manager_payloads.items()
        if code not in existing_area_managers
    ]
    if missing_area_manager_rows:
        # Production's legacy d_AreaManager.area_manager_id has no identity
        # default, which is why the original script assigns IDs manually.
        # Serialize this small critical section to avoid concurrent max+1 use.
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ["d_AreaManager-id"])
        max_area_manager_id = (
            AreaManager.objects.aggregate(value=Max("areaManager_id"))["value"] or 0
        )
        AreaManager.objects.bulk_create([
            AreaManager(
                areaManager_id=max_area_manager_id + index,
                areaManager_code=code,
                areaManager_name=row["area_manager_name"],
                areaManager_email=row["area_manager_email"],
                gender=row["area_manager_gender"],
                is_active=True,
            )
            for index, (code, row) in enumerate(missing_area_manager_rows, start=1)
        ], ignore_conflicts=True, batch_size=500)
        # Keep a sequence in sync in environments where one exists.
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT setval(
                    pg_get_serial_sequence('"d_AreaManager"', 'area_manager_id'),
                    %s,
                    true
                )
                WHERE pg_get_serial_sequence('"d_AreaManager"', 'area_manager_id') IS NOT NULL
                """,
                [max_area_manager_id + len(missing_area_manager_rows)],
            )
    region_managers = {
        x.regionManager_code: x for x in RegionManager.objects.filter(
            regionManager_code__in=region_manager_payloads
        )
    }
    area_managers = {
        x.areaManager_code: x for x in AreaManager.objects.filter(
            areaManager_code__in=area_manager_payloads
        )
    }

    manager_payloads = {}
    for row in valid:
        manager_payloads.setdefault(row["manager_code"], row)
    existing_managers = {
        x.manager_code: x for x in Manager.objects.filter(manager_code__in=manager_payloads)
    }
    Manager.objects.bulk_create([
        Manager(
            manager_code=code,
            regionManager=region_managers[row["region_manager_code"]],
            areaManager=area_managers[row["area_manager_code"]],
            qlkv_code=row["area_manager_code"],
            qlkv_name=row["area_manager_name"],
            qlkv_email=row["area_manager_email"],
            qlv_code=row["region_manager_code"],
            qlv_name=row["region_manager_name"],
            qlv_email=row["region_manager_email"],
            valid_from=batch.business_date,
            is_valid=True,
        )
        for code, row in manager_payloads.items()
        if code not in existing_managers
    ], ignore_conflicts=True, batch_size=500)
    managers = {
        x.manager_code: x for x in Manager.objects.filter(manager_code__in=manager_payloads)
    }

    existing_shops = {
        x.shop_code: x for x in Shop.objects.filter(shop_code__in=seen_shop_codes)
    }
    new_shops = []
    shop_updates = []
    for row in valid:
        shop = existing_shops.get(row["shop_code"])
        is_active = row["status"] == "active"
        closed_date = None if is_active else row["shop_closed_date"]
        if shop is None:
            new_shops.append(Shop(
                shop_code=row["shop_code"],
                shop_name=row["shop_name"],
                shop_email="bosungsau@f88.vn",
                is_shop_active=is_active,
                manager_id=managers[row["manager_code"]],
                region_id=row["region"],
                shop_closed_date=closed_date,
                for_borrow_only=False,
            ))
        else:
            shop.shop_name = row["shop_name"]
            shop.is_shop_active = is_active
            shop.manager_id = managers[row["manager_code"]]
            shop.region_id = row["region"]
            # Active shops clear a stale closure date. Closed rows without a
            # date preserve the last known date instead of erasing it.
            if is_active or closed_date is not None:
                shop.shop_closed_date = closed_date
            shop.for_borrow_only = False
            shop_updates.append(shop)
    Shop.objects.bulk_create(new_shops, ignore_conflicts=True, batch_size=500)
    if shop_updates:
        Shop.objects.bulk_update(
            shop_updates,
            ["shop_name", "is_shop_active", "manager_id", "region_id",
             "shop_closed_date", "for_borrow_only"],
            batch_size=500,
        )

    deactivated_missing = 0
    if manifest.get("deactivate_missing_shops") is True:
        missing = Shop.objects.exclude(shop_code__in=seen_shop_codes).filter(is_shop_active=True)
        deactivated_missing = missing.update(is_shop_active=False)
    return {
        "created": len(new_shops),
        "updated": len(shop_updates),
        "rejected": 0,
        "snapshot_applied": True,
        "region_managers_created": len(region_manager_payloads) - len(existing_region_managers),
        "area_managers_created": len(area_manager_payloads) - len(existing_area_managers),
        "managers_created": len(manager_payloads) - len(existing_managers),
        "deactivated_missing": deactivated_missing,
    }


def _process_master_data(batch):
    """Safe master-data mode: upsert explicit shops or apply a full snapshot.

    Legacy ``entity=shop`` payloads never deactivate an absent PGD. Schema v2
    orgchart snapshots can do so only with an explicit complete manifest.
    """
    records = []
    for chunk in batch.chunks.order_by("chunk_no"):
        records.extend((chunk, row_no, record)
                       for row_no, record in enumerate(chunk.records, start=1))
    if any(isinstance(record, dict) and record.get("entity") in {
        "orgchart_shop", "orgchart_snapshot"
    } for _, _, record in records):
        return _process_orgchart_snapshot(batch, records)

    created = updated = rejected = 0
    seen = set()
    for chunk, row_no, record in records:
        try:
            if not isinstance(record, dict) or record.get("entity", "shop") != "shop":
                raise ValueError("Chỉ hỗ trợ entity=shop trong schema v1")
            code = int(record["shop_code"])
            if code in seen:
                raise ValueError("shop_code bị lặp trong cùng batch")
            seen.add(code)
            name = str(record["shop_name"]).strip()
            manager_code = str(record["manager_code"]).strip()
            if not name or not manager_code:
                raise ValueError("shop_name và manager_code là bắt buộc")
            manager = Manager.objects.filter(manager_code=manager_code).first()
            if not manager:
                raise ValueError(f"Không tìm thấy manager_code={manager_code}")
            defaults = {
                "shop_name": name, "manager_id": manager,
                "is_shop_active": bool(record.get("is_shop_active", True)),
            }
            closed_date = record.get("closed_date")
            if closed_date:
                defaults["shop_closed_date"] = _as_date(closed_date)
            shop, was_created = Shop.objects.update_or_create(shop_code=code, defaults=defaults)
            created += int(was_created)
            updated += int(not was_created)
        except (KeyError, TypeError, ValueError) as exc:
            rejected += 1
            _reject(batch, chunk, row_no, record if isinstance(record, dict) else {}, "INVALID_MASTER_DATA", str(exc))
    return {"created": created, "updated": updated, "rejected": rejected}


def _process_documents(batch):
    records = []
    for chunk in batch.chunks.order_by("chunk_no"):
        records.extend((chunk, row_no, record) for row_no, record in enumerate(chunk.records, start=1))

    raw_codes = [str(record.get("source_record_id", "")).strip() for _, _, record in records if isinstance(record, dict)]
    existing_docs = set(DocumentsDetail.objects.filter(documents_code__in=raw_codes).values_list("documents_code", flat=True))
    shop_codes = {str(r.get("shop_code", "")).strip() for _, _, r in records if isinstance(r, dict)}
    shops = {str(x.shop_code): x for x in Shop.objects.filter(
        shop_code__in=[x for x in shop_codes if x.isdigit()], for_borrow_only=False
    ).select_related("manager_id", "region_id")}
    manager_codes = {str(r.get("manager_code", "")).strip() for _, _, r in records if isinstance(r, dict)}
    managers = {x.manager_code: x for x in Manager.objects.filter(manager_code__in=manager_codes)}
    region_names = {str(r.get("region_name", "")).strip() for _, _, r in records if isinstance(r, dict)}
    regions = {x.region_name: x for x in Region.objects.filter(region_name__in=region_names)}
    doc_type_codes = {str(r.get("document_type_code", "")).strip() for _, _, r in records if isinstance(r, dict)}
    doc_types = {x.document_type_code: x for x in DocumentType.objects.filter(document_type_code__in=doc_type_codes)}
    folder_type_codes = {str(r.get("folder_type_code", "")).strip() for _, _, r in records if isinstance(r, dict)}
    folder_types = {x.folder_type_code: x for x in FolderType.objects.filter(folder_type_code__in=folder_type_codes)}
    status = FolderStatus.objects.filter(pk=1).first()
    if not status:
        status = FolderStatus.objects.filter(is_not_received_yet=True, is_valid=True).order_by("folder_status_id").first()
    if not status:
        raise RuntimeError("Thiếu FolderStatus chưa nhận; không thể tạo folder an toàn")
    folder_group = FolderGroup.objects.filter(
        is_active=True, day_from__lte=batch.business_date.day, day_to__gte=batch.business_date.day
    ).order_by("group_id").first()

    # Legacy job does not filter reference rows by is_valid.
    business_types = list(BusinessType.objects.all())
    contracts = {x.contract_code: x for x in ContractDetail.objects.filter(contract_code__in={str(r.get("contract_code", "")).strip() for _, _, r in records if isinstance(r, dict) and r.get("contract_code")})}
    loans = {x.loan_code: x for x in LoanDetail.objects.filter(loan_code__in={str(r.get("loan_code", "")).strip() for _, _, r in records if isinstance(r, dict) and r.get("loan_code")})}
    seen = set()
    folder_payloads, valid, dimension_records = {}, [], []
    rejected = skipped = 0

    for chunk, row_no, record in records:
        try:
            if not isinstance(record, dict):
                raise ValueError("Record phải là JSON object")
            code = str(record["source_record_id"]).strip()
            if not code or len(code) > 50:
                raise ValueError("source_record_id bắt buộc, tối đa 50 ký tự")
            if code in seen:
                skipped += 1
                continue
            seen.add(code)
            already_exists = code in existing_docs
            if already_exists:
                skipped += 1
            created_date = _as_date(record.get("documents_created_date", batch.business_date))
            if created_date != batch.business_date:
                raise ValueError("documents_created_date phải đúng business_date của batch")
            shop = shops.get(str(record["shop_code"]).strip())
            if not shop:
                raise ValueError("Không tìm thấy PGD hoặc PGD chỉ dùng cho mượn chứng từ")
            if not shop.manager_id:
                raise ValueError("PGD chưa được gán manager")
            manager = managers.get(str(record.get("manager_code", "")).strip()) or shop.manager_id
            region = regions.get(str(record.get("region_name", "")).strip()) or shop.region_id
            if not manager or not region:
                raise ValueError("Không map được manager hoặc region từ Oracle/shop")
            if record.get("contract_code") and len(str(record["contract_code"]).strip()) > 30:
                raise ValueError("contract_code vượt quá 30 ký tự")
            if record.get("loan_code") and len(str(record["loan_code"]).strip()) > 15:
                raise ValueError("loan_code vượt quá 15 ký tự")
            for field, max_length in (("customer_code", 100), ("customer_name", 255),
                                      ("employee_code", 100), ("employee_name", 255)):
                if record.get(field) is not None and len(str(record[field]).strip()) > max_length:
                    raise ValueError(f"{field} vượt quá {max_length} ký tự")
            if record.get("record_type") == "dimension_only":
                dimension_records.append((chunk, row_no, record, code, shop, created_date, manager))
                continue
            doc_type = doc_types.get(str(record["document_type_code"]).strip())
            folder_type = folder_types.get(str(record["folder_type_code"]).strip())
            if not doc_type or not folder_type:
                raise ValueError("Không tìm thấy document_type_code hoặc folder_type_code")
            business_type = None
            business_code = str(record.get("business_type_code", "")).strip()
            if business_code:
                action = str(record.get("action_code", "")).strip().upper()
                candidates = [
                    x for x in business_types
                    if x.business_type_code == business_code
                    and (not x.need_action_code or str(x.action_code or "").strip().upper() == action)
                ]
                if len(candidates) != 1:
                    raise ValueError("business_type_code/action_code không xác định duy nhất")
                business_type = candidates[0]
            folder_code = f"{created_date:%Y%m%d}{shop.shop_code}{folder_type.folder_type_code}"
            folder_payloads.setdefault(folder_code, (shop, folder_type, created_date, manager))
            valid.append((chunk, row_no, record, code, shop, doc_type, folder_type,
                          business_type, folder_code, created_date, manager, already_exists))
        except (KeyError, TypeError, ValueError) as exc:
            rejected += 1
            _reject(batch, chunk, row_no, record if isinstance(record, dict) else {}, "INVALID_DOCUMENT", str(exc))

    # Create only missing folders in bulk; never overwrite receiving/note fields.
    existing_folders = {x.folder_code: x for x in Folder.objects.filter(folder_code__in=folder_payloads).select_related("shop_id", "folder_type_id")}
    new_folders = [Folder(folder_code=code, shop_id=shop, folder_type_id=folder_type, folder_status_id=status,
                          manager_id=manager, folder_created_date=created_date, is_original=True,
                          is_issue=True, group=folder_group, is_out_of_group=folder_group is None)
                   for code, (shop, folder_type, created_date, manager) in folder_payloads.items() if code not in existing_folders]
    Folder.objects.bulk_create(new_folders, ignore_conflicts=True, batch_size=1000)
    # Reconcile system-owned folder fields while preserving receiving/package/note fields.
    actual_folder_updates = []
    for code, (_, _, _, manager) in folder_payloads.items():
        obj = existing_folders.get(code)
        if obj:
            obj.manager_id = manager
            obj.is_original = True
            obj.is_issue = True
            obj.group = folder_group
            obj.is_out_of_group = folder_group is None
            actual_folder_updates.append(obj)
    if actual_folder_updates:
        Folder.objects.bulk_update(
            actual_folder_updates,
            ["manager_id", "is_original", "is_issue", "group", "is_out_of_group"],
            batch_size=1000,
        )

    # Legacy parity: for every non-borrow-only shop, create daily virtual folders
    # for Operations (1) and Bank (3), excluding dates after shop closure.
    virtual_types = {x.folder_type_code: x for x in FolderType.objects.filter(folder_type_code__in=["1", "3"])}
    eligible_shops = Shop.objects.filter(
        for_borrow_only=False, manager_id__isnull=False, region_id__isnull=False
    ).filter(Q(shop_closed_date__isnull=True) | Q(shop_closed_date__gte=batch.business_date)).select_related("manager_id")
    virtual_payloads = {}
    for virtual_shop in eligible_shops.iterator():
        for type_code, virtual_type in virtual_types.items():
            code = f"{batch.business_date:%Y%m%d}{virtual_shop.shop_code}{type_code}"
            if code not in folder_payloads:
                virtual_payloads[code] = (virtual_shop, virtual_type)
    existing_virtual_codes = set(Folder.objects.filter(folder_code__in=virtual_payloads).values_list("folder_code", flat=True))
    Folder.objects.bulk_create([
        Folder(folder_code=code, shop_id=virtual_shop, folder_type_id=virtual_type,
               folder_status_id=status, manager_id=virtual_shop.manager_id,
               folder_created_date=batch.business_date, is_original=True, is_issue=False,
               group=folder_group, is_out_of_group=folder_group is None)
        for code, (virtual_shop, virtual_type) in virtual_payloads.items()
        if code not in existing_virtual_codes
    ], ignore_conflicts=True, batch_size=1000)
    all_folder_codes = set(folder_payloads) | set(virtual_payloads)
    folders = {x.folder_code: x for x in Folder.objects.filter(folder_code__in=all_folder_codes)}

    # Maintain customer and employee dimensions before linking contracts/loans.
    metadata_records = valid + dimension_records
    customer_payloads, employee_payloads = {}, {}
    for _, _, record, *_ in metadata_records:
        customer_code = str(record.get("customer_code") or "").strip()
        employee_code = str(record.get("employee_code") or "").strip()
        if customer_code and customer_code not in customer_payloads:
            customer_payloads[customer_code] = str(record.get("customer_name") or "").strip() or None
        if employee_code and employee_code not in employee_payloads:
            employee_payloads[employee_code] = str(record.get("employee_name") or "").strip() or None
    existing_customers = {x.customer_code: x for x in LoanCustomer.objects.filter(customer_code__in=customer_payloads)}
    existing_employees = {x.employee_code: x for x in Employee.objects.filter(employee_code__in=employee_payloads)}
    LoanCustomer.objects.bulk_create([
        LoanCustomer(customer_code=code, customer_name=name)
        for code, name in customer_payloads.items() if code not in existing_customers
    ], ignore_conflicts=True, batch_size=1000)
    Employee.objects.bulk_create([
        Employee(employee_code=code, employee_name=name)
        for code, name in employee_payloads.items() if code not in existing_employees
    ], ignore_conflicts=True, batch_size=1000)
    customers = {x.customer_code: x for x in LoanCustomer.objects.filter(customer_code__in=customer_payloads)}
    employees = {x.employee_code: x for x in Employee.objects.filter(employee_code__in=employee_payloads)}
    customer_updates, employee_updates = [], []
    for code, name in customer_payloads.items():
        obj = customers.get(code)
        if obj and name and not obj.customer_name:
            obj.customer_name = name
            customer_updates.append(obj)
    for code, name in employee_payloads.items():
        obj = employees.get(code)
        if obj and name and not obj.employee_name:
            obj.employee_name = name
            employee_updates.append(obj)
    if customer_updates:
        LoanCustomer.objects.bulk_update(customer_updates, ["customer_name"], batch_size=1000)
    if employee_updates:
        Employee.objects.bulk_update(employee_updates, ["employee_name"], batch_size=1000)

    missing_contracts = {str(r.get("contract_code")).strip() for _, _, r, *_ in metadata_records if r.get("contract_code")} - set(contracts)
    ContractDetail.objects.bulk_create([ContractDetail(contract_code=x) for x in missing_contracts], ignore_conflicts=True, batch_size=1000)
    if missing_contracts:
        contracts.update({x.contract_code: x for x in ContractDetail.objects.filter(contract_code__in=missing_contracts)})
    missing_loans = {str(r.get("loan_code")).strip() for _, _, r, *_ in metadata_records if r.get("loan_code")} - set(loans)
    LoanDetail.objects.bulk_create([LoanDetail(loan_code=x) for x in missing_loans], ignore_conflicts=True, batch_size=1000)
    if missing_loans:
        loans.update({x.loan_code: x for x in LoanDetail.objects.filter(loan_code__in=missing_loans)})

    # Match the legacy script's dimension links while only filling blank fields.
    contract_records, loan_records = {}, {}
    for _, _, record, *_ in metadata_records:
        contract_code = str(record.get("contract_code") or "").strip()
        loan_code = str(record.get("loan_code") or "").strip()
        if contract_code and contract_code not in contract_records:
            contract_records[contract_code] = record
        if loan_code and loan_code not in loan_records:
            loan_records[loan_code] = record
    contract_updates = []
    for code, record in contract_records.items():
        obj = contracts.get(code)
        changed = False
        customer = customers.get(str(record.get("customer_code") or "").strip())
        employee = employees.get(str(record.get("employee_code") or "").strip())
        if obj and customer and not obj.customer_id:
            obj.customer_id = customer
            changed = True
        if obj and employee and not obj.employee_id:
            obj.employee_id = employee
            changed = True
        if changed:
            contract_updates.append(obj)
    if contract_updates:
        ContractDetail.objects.bulk_update(contract_updates, ["customer_id", "employee_id"], batch_size=1000)
    loan_updates = []
    for code, record in loan_records.items():
        obj = loans.get(code)
        if not obj:
            continue
        customer_code = str(record.get("customer_code") or "").strip()
        employee_code = str(record.get("employee_code") or "").strip()
        customer_name = str(record.get("customer_name") or "").strip()
        employee_name = str(record.get("employee_name") or "").strip()
        customer, employee = customers.get(customer_code), employees.get(employee_code)
        changed = False
        for field, value in (("customer_id", customer), ("employee_id", employee),
                             ("customer_code", customer_code), ("customer_name", customer_name),
                             ("employee_code", employee_code), ("employee_name", employee_name)):
            if value and not getattr(obj, field):
                setattr(obj, field, value)
                changed = True
        if changed:
            loan_updates.append(obj)
    if loan_updates:
        LoanDetail.objects.bulk_update(loan_updates, ["customer_id", "employee_id", "customer_code",
                                                       "customer_name", "employee_code", "employee_name"], batch_size=1000)

    new_documents = []
    for _, _, record, code, shop, doc_type, _, business_type, folder_code, created_date, manager, already_exists in valid:
        if already_exists:
            continue
        new_documents.append(DocumentsDetail(
            documents_code=code, document_type_id=doc_type, shop_id=shop,
            loan_id=loans.get(str(record.get("loan_code", "")).strip()),
            contract_id=contracts.get(str(record.get("contract_code", "")).strip()),
            documents_created_date=created_date, folder_id=folders[folder_code],
            business_type_id=business_type, manager_id=manager,
            is_pending_metadata=bool(record.get("is_pending_metadata", False)),
            note=str(record.get("pending_metadata_note") or "").strip() or None,
        ))
    DocumentsDetail.objects.bulk_create(new_documents, ignore_conflicts=True, batch_size=1000)
    return {"created": len(new_documents), "skipped": skipped, "rejected": rejected,
            "customers_maintained": len(customer_payloads), "employees_maintained": len(employee_payloads),
            "contracts_maintained": len(contract_records), "loans_maintained": len(loan_records),
            "dimension_only_records": len(dimension_records),
            "real_folders": len(folder_payloads),
            "virtual_folders_created": len(virtual_payloads) - len(existing_virtual_codes)}


def process_batch(batch_key):
    """Called by the Celery task. Returns summary and is safe to retry after completion."""
    with transaction.atomic():
        batch = ExternalDocumentIntakeBatch.objects.select_for_update().get(batch_key=batch_key)
        if batch.status in {batch.Status.COMPLETED, batch.Status.COMPLETED_WITH_REJECTIONS}:
            return batch.summary
        batch.status = batch.Status.PROCESSING
        batch.error_message = ""
        batch.save(update_fields=["status", "error_message", "updated_at"])
        ExternalDocumentIntakeRejection.objects.filter(batch=batch).delete()
        summary = _process_documents(batch) if batch.kind == batch.Kind.DOCUMENTS else _process_master_data(batch)
        summary.update({"received_records": batch.received_records, "received_chunks": batch.received_chunks})
        batch.summary = summary
        batch.processed_at = timezone.now()
        batch.status = batch.Status.COMPLETED_WITH_REJECTIONS if summary.get("rejected") else batch.Status.COMPLETED
        batch.save(update_fields=["summary", "processed_at", "status", "updated_at"])
        return summary


def fail_batch(batch_key, error):
    ExternalDocumentIntakeBatch.objects.filter(batch_key=batch_key).update(
        status=ExternalDocumentIntakeBatch.Status.FAILED, error_message=str(error)[:4000], updated_at=timezone.now()
    )
