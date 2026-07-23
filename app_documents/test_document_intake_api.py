import hashlib

from django.contrib.auth.models import User
from django.test import TestCase

from .document_intake import process_batch
from .models import (
    AreaManager, BusinessType, DocumentType, ExternalDocumentIntakeBatch,
    ExternalDocumentIntakeToken, Folder, FolderGroup, FolderStatus, FolderType,
    Manager, Region, RegionManager, Shop,
)


class DocumentIntakeApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("intake-test")
        self.raw_token = "doc_test_token"
        ExternalDocumentIntakeToken.objects.create(
            name="test", token_prefix="doc_test", token_hash=hashlib.sha256(self.raw_token.encode()).hexdigest(),
            scopes=["documents:write"], created_by=self.user,
        )
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {self.raw_token}"}
        self.manager = Manager.objects.create(manager_code="M1", qlkv_code="A", qlkv_name="A", qlv_code="B", qlv_name="B")
        self.region = Region.objects.create(region_code="R1", region_name="Miền Test")
        Shop.objects.create(shop_code=1, shop_name="PGD 1", manager_id=self.manager, region_id=self.region)
        Shop.objects.create(shop_code=2, shop_name="PGD 2", manager_id=self.manager, region_id=self.region)
        DocumentType.objects.create(document_type_code="HD", document_type_name="HĐ", created_by=self.user)
        FolderType.objects.create(folder_type_code="1", folder_type_name="Gốc", created_by=self.user)
        FolderType.objects.create(folder_type_code="3", folder_type_name="Ngân hàng", created_by=self.user)
        FolderStatus.objects.create(folder_status_code="1", folder_status_name="Chưa nhận", created_by=self.user,
                                    is_not_received_yet=True)
        FolderGroup.objects.create(group_name="Ngày 20-25", day_from=20, day_to=25, is_active=True)

    def test_chunk_is_idempotent_and_processing_creates_document(self):
        create = self.client.post("/api/integrations/v1/batches/", data={
            "batch_key": "docs-2026-07-22", "kind": "documents", "business_date": "2026-07-22",
            "expected_records": 1, "expected_chunks": 1,
        }, content_type="application/json", **self.headers)
        self.assertEqual(create.status_code, 201)
        payload = {"chunk_no": 1, "records": [{
            "source_record_id": "source-1", "documents_created_date": "2026-07-22", "shop_code": 1,
            "document_type_code": "HD", "folder_type_code": "1",
            "contract_code": "contract-1", "loan_code": "loan-1",
            "customer_code": "customer-1", "customer_name": "Khách hàng thử nghiệm",
            "employee_code": "employee-1", "employee_name": "Nhân viên thử nghiệm",
        }]}
        first = self.client.post("/api/integrations/v1/batches/docs-2026-07-22/chunks/", data=payload,
                                 content_type="application/json", **self.headers)
        second = self.client.post("/api/integrations/v1/batches/docs-2026-07-22/chunks/", data=payload,
                                  content_type="application/json", **self.headers)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        batch = ExternalDocumentIntakeBatch.objects.get(batch_key="docs-2026-07-22")
        self.assertEqual(batch.received_records, 1)
        process_batch(batch.batch_key)
        batch.refresh_from_db()
        self.assertEqual(batch.status, batch.Status.COMPLETED)
        self.assertEqual(batch.summary["created"], 1)
        document = __import__("app_documents.models", fromlist=["DocumentsDetail"]).DocumentsDetail.objects.select_related(
            "loan_id", "contract_id__customer_id", "contract_id__employee_id"
        ).get(documents_code="source-1")
        self.assertEqual(document.loan_id.customer_name, "Khách hàng thử nghiệm")
        self.assertEqual(document.loan_id.employee_name, "Nhân viên thử nghiệm")
        self.assertEqual(document.contract_id.customer_id.customer_code, "customer-1")
        self.assertEqual(document.contract_id.employee_id.employee_code, "employee-1")
        self.assertTrue(Folder.objects.filter(folder_code="2026072223", is_issue=False, group__isnull=False).exists())

    def test_rejects_chunk_content_changed_for_same_number(self):
        self.client.post("/api/integrations/v1/batches/", data={
            "batch_key": "conflict", "kind": "documents", "business_date": "2026-07-22",
        }, content_type="application/json", **self.headers)
        self.client.post("/api/integrations/v1/batches/conflict/chunks/", data={"chunk_no": 1, "records": [{"source_record_id": "a"}]},
                         content_type="application/json", **self.headers)
        response = self.client.post("/api/integrations/v1/batches/conflict/chunks/", data={"chunk_no": 1, "records": [{"source_record_id": "b"}]},
                                    content_type="application/json", **self.headers)
        self.assertEqual(response.status_code, 409)

    def test_catalog_returns_production_mapping_fields(self):
        response = self.client.get("/api/integrations/v1/catalog/", **self.headers)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["folder_types"][0]["folder_type_code"], "1")
        self.assertEqual(payload["document_types"][0]["document_type_code"], "HD")
        self.assertEqual(payload["shops"][0]["shop_code"], 1)

    def test_dimension_only_record_maintains_legacy_dimensions_without_document(self):
        batch = ExternalDocumentIntakeBatch.objects.create(
            batch_key="dimension-only", kind="documents", business_date="2026-07-22",
            status="uploading", received_records=1, received_chunks=1,
        )
        batch.chunks.create(chunk_no=1, payload_hash="x" * 64, record_count=1, records=[{
            "record_type": "dimension_only", "source_record_id": "DIM-source-2",
            "documents_created_date": "2026-07-22", "shop_code": 1,
            "contract_code": "contract-2", "loan_code": "loan-2",
            "customer_code": "customer-2", "customer_name": "Khách hàng 2",
            "employee_code": "employee-2", "employee_name": "Nhân viên 2",
        }])
        summary = process_batch(batch.batch_key)
        self.assertEqual(summary["dimension_only_records"], 1)
        self.assertFalse(__import__("app_documents.models", fromlist=["DocumentsDetail"]).DocumentsDetail.objects.filter(
            documents_code="DIM-source-2"
        ).exists())
        loan = __import__("app_documents.models", fromlist=["LoanDetail"]).LoanDetail.objects.get(loan_code="loan-2")
        self.assertEqual(loan.customer_name, "Khách hàng 2")

    def test_oracle_transform_explodes_doc_group_and_uses_legacy_code_formula(self):
        second_type = DocumentType.objects.create(
            document_type_code="PC", document_type_name="Phiếu chi", created_by=self.user
        )
        business = BusinessType.objects.create(
            business_type_code="BT1", business_type_name="Giải ngân", action_code="GN",
            need_action_code=True, created_by=self.user,
        )
        catalog = self.client.get("/api/integrations/v1/catalog/", **self.headers).json()
        from scripts.prefect_document_intake import transform_rows
        records, rejected = transform_rows([{
            "parent_document_code": "SRC1", "shop_code": "1",
            "folder_type": "Gốc", "doc_grp": "HĐ, Phiếu chi",
            "business_type": "Giải ngân", "action_code": "GN",
            "qlv_user_code": "M", "qlkv_user_code": "1", "region": "Miền Test",
        }], catalog, __import__("datetime").date(2026, 7, 22))
        self.assertEqual(rejected, [])
        self.assertEqual(len(records), 2)
        expected_codes = {
            f"202607221SRC1{business.business_type_id}{document_type_id}"
            for document_type_id in DocumentType.objects.filter(
                document_type_code__in=["HD", "PC"]
            ).values_list("document_type_id", flat=True)
        }
        self.assertEqual({record["source_record_id"] for record in records}, expected_codes)

    def test_oracle_transform_keeps_repeated_parent_code_until_final_document_dedup(self):
        second_type = DocumentType.objects.create(
            document_type_code="PC", document_type_name="Phiếu chi", created_by=self.user
        )
        business = BusinessType.objects.create(
            business_type_code="BT1", business_type_name="Giải ngân", action_code="GN",
            need_action_code=True, created_by=self.user,
        )
        catalog = self.client.get("/api/integrations/v1/catalog/", **self.headers).json()
        from scripts.prefect_document_intake import transform_rows
        common = {
            "parent_document_code": "SRC-DUP", "shop_code": "1",
            "folder_type": "Gốc", "business_type": "Giải ngân", "action_code": "GN",
            "qlv_user_code": "M", "qlkv_user_code": "1", "region": "Miền Test",
        }
        rows = [{**common, "doc_grp": "HĐ"}, {**common, "doc_grp": "Phiếu chi"}]
        records, rejected = transform_rows(
            rows, catalog, __import__("datetime").date(2026, 7, 22)
        )
        self.assertEqual(rejected, [])
        self.assertEqual(len(records), 2)
        self.assertEqual(
            {record["source_record_id"] for record in records},
            {
                f"202607221SRC-DUP{business.business_type_id}{document_type_id}"
                for document_type_id in [
                    DocumentType.objects.get(document_type_code="HD").document_type_id,
                    second_type.document_type_id,
                ]
            },
        )

    def test_catalog_keeps_inactive_reference_rows_for_legacy_intake_parity(self):
        inactive = FolderType.objects.create(
            folder_type_code="2", folder_type_name="Chứng từ CIMB hàng ngày",
            is_valid=False, created_by=self.user,
        )
        payload = self.client.get("/api/integrations/v1/catalog/", **self.headers).json()
        self.assertIn(
            inactive.folder_type_id,
            {item["folder_type_id"] for item in payload["folder_types"]},
        )

    def test_complete_orgchart_snapshot_creates_hierarchy_and_deactivates_missing_shop(self):
        batch = ExternalDocumentIntakeBatch.objects.create(
            batch_key="orgchart-2026-06", kind="master_data",
            business_date="2026-06-01", schema_version="v2",
            expected_records=2, expected_chunks=1, received_records=2,
            received_chunks=1, status="uploading",
        )
        batch.chunks.create(
            chunk_no=1, payload_hash="m" * 64, record_count=2,
            records=[{
                "entity": "orgchart_shop", "shop_code": 1, "shop_name": "PGD 1 mới",
                "manager_code": "RM-AM", "region_manager_code": "RM",
                "region_manager_name": "QLV mới", "region_manager_email": "rm@example.com",
                "area_manager_code": "AM", "area_manager_name": "QLKV mới",
                "area_manager_email": "am@example.com", "region_code": "R1",
                "status": "active", "shop_closed_date": None,
            }, {
                "entity": "orgchart_snapshot", "snapshot_complete": True,
                "deactivate_missing_shops": True,
            }],
        )
        summary = process_batch(batch.batch_key)
        self.assertTrue(summary["snapshot_applied"])
        self.assertEqual(summary["region_managers_created"], 1)
        self.assertEqual(summary["area_managers_created"], 1)
        self.assertEqual(summary["managers_created"], 1)
        self.assertTrue(RegionManager.objects.filter(regionManager_code="RM").exists())
        self.assertTrue(AreaManager.objects.filter(areaManager_code="AM").exists())
        shop = Shop.objects.get(shop_code=1)
        self.assertEqual(shop.shop_name, "PGD 1 mới")
        self.assertEqual(shop.manager_id.manager_code, "RM-AM")
        self.assertFalse(Shop.objects.get(shop_code=2).is_shop_active)

    def test_invalid_orgchart_snapshot_changes_nothing(self):
        batch = ExternalDocumentIntakeBatch.objects.create(
            batch_key="orgchart-invalid", kind="master_data",
            business_date="2026-06-01", schema_version="v2",
            expected_records=2, expected_chunks=1, received_records=2,
            received_chunks=1, status="uploading",
        )
        batch.chunks.create(
            chunk_no=1, payload_hash="n" * 64, record_count=2,
            records=[{
                "entity": "orgchart_shop", "shop_code": 1, "shop_name": "Không được lưu",
                "manager_code": "RM-BAD", "region_manager_code": "RM",
                "region_manager_name": "QLV", "area_manager_code": "AM",
                "area_manager_name": "", "region_code": "R1", "status": "active",
            }, {
                "entity": "orgchart_snapshot", "snapshot_complete": True,
                "deactivate_missing_shops": True,
            }],
        )
        summary = process_batch(batch.batch_key)
        self.assertFalse(summary["snapshot_applied"])
        self.assertGreater(summary["rejected"], 0)
        self.assertEqual(Shop.objects.get(shop_code=1).shop_name, "PGD 1")
        self.assertTrue(Shop.objects.get(shop_code=2).is_shop_active)
        self.assertFalse(Manager.objects.filter(manager_code="RM-BAD").exists())

    def test_orgchart_transform_adds_complete_manifest_and_closed_row_wins(self):
        from scripts.prefect_document_master_data import transform_orgchart
        common = {
            "shop_code": 10, "shop_name": "PGD 10", "manager_code": "RMAM",
            "region_manager_code": "RM", "region_manager_name": "QLV",
            "area_manager_code": "AM", "area_manager_name": "QLKV",
            "region_code": "R1",
        }
        records, rejected = transform_orgchart([
            {**common, "status": "Active"},
            {**common, "status": "Closed", "shop_closed_date": "2026-06-30"},
        ])
        self.assertEqual(rejected, [])
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["status"], "closed")
        self.assertEqual(records[0]["shop_closed_date"], "2026-06-30")
        self.assertTrue(records[-1]["snapshot_complete"])
        self.assertTrue(records[-1]["deactivate_missing_shops"])
