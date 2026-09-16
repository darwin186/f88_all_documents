def summarize_dataset(staging_rows):
    distinct = {key: set() for key in ("contracts", "shops", "areas", "regions", "customers", "employees")}
    counts = {"rows": 0, "folder": 0, "document": 0, "invalid": 0}
    for payload, errors in staging_rows.values_list("normalized_payload", "validation_errors").iterator(chunk_size=2000):
        counts["rows"] += 1
        counts["invalid"] += bool(errors)
        kind = payload.get("error_type")
        if kind in ("folder", "document"):
            counts[kind] += 1
        manager = payload.get("manager_snapshot") or {}
        values = {
            "contracts": payload.get("contract_code"),
            "shops": payload.get("shop_id") or payload.get("shop_code"),
            "areas": payload.get("area_manager_id") or manager.get("qlkv_email") or manager.get("qlkv_name"),
            "regions": manager.get("qlv_email") or manager.get("qlv_name"),
            "customers": payload.get("customer_code"),
            "employees": payload.get("employee_code"),
        }
        for key, value in values.items():
            if value is not None and str(value).strip():
                distinct[key].add(str(value).strip())
    return [
        {"label": label, "value": value}
        for label, value in (
            ("Tổng dòng dữ liệu", counts["rows"]),
            ("Mã hợp đồng duy nhất", len(distinct["contracts"])),
            ("PGD có lỗi", len(distinct["shops"])),
            ("Quản lý khu vực", len(distinct["areas"])),
            ("Quản lý vùng", len(distinct["regions"])),
            ("Mã khách hàng", len(distinct["customers"])),
            ("Mã nhân viên", len(distinct["employees"])),
            ("Dòng lỗi quyển chứng từ", counts["folder"]),
            ("Dòng lỗi chứng từ", counts["document"]),
            ("Dòng chưa đạt kiểm tra dữ liệu", counts["invalid"]),
        )
    ]
