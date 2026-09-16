import json
from datetime import date, timedelta
from unittest.mock import patch

from django.core import mail
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from app_documents.models import (
    AreaManager,
    Manager,
    Region,
    RegionManager,
    Shop,
    UserProfile,
)
from app_document_campaigns.models import (
    Campaign,
    CampaignError,
    CampaignType,
    CampaignVersion,
    ChecklistQuestion,
    ChecklistTemplate,
    ShopResponse,
    ShopSubmission,
)
from app_document_campaigns.services.access_links import issue_shop_access_link, resolve_shop_access_link
from app_document_campaigns.tasks import process_shop_submission


class ShopResponseFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="campaign-admin", password="test-password")
        self.campaign_type = CampaignType.objects.get(code="hardcopy-document-error")
        self.region = Region.objects.create(region_code="TEST", region_name="Vùng test")
        self.area = AreaManager.objects.create(
            areaManager_code="AREA01",
            areaManager_name="QLKV test",
            areaManager_email="area@example.com",
        )
        self.region_manager = RegionManager.objects.create(
            regionManager_code="QLV01",
            regionManager_name="QLV test",
            regionManager_email="region@example.com",
        )
        self.manager = Manager.objects.create(
            manager_code="MANAGER01",
            areaManager=self.area,
            regionManager=self.region_manager,
            qlkv_code="QLKV01",
            qlkv_name="QLKV test",
            qlkv_email="area@example.com",
            qlv_code="QLV01",
            qlv_name="QLV test",
            qlv_email="region@example.com",
        )
        self.shop = Shop.objects.create(
            shop_code=9001,
            shop_name="PGD Test Autosave",
            shop_email="shop@example.com",
            manager_id=self.manager,
            region_id=self.region,
        )
        now = timezone.now()
        self.campaign = Campaign.objects.create(
            code="CT-2026-09",
            name="Chiến dịch tháng 09/2026",
            campaign_type=self.campaign_type,
            report_month=date(2026, 9, 1),
            status=Campaign.Status.ACTIVE,
            response_opens_at=now - timedelta(hours=1),
            response_deadline=now + timedelta(days=7),
            link_expires_at=now + timedelta(days=8),
            created_by=self.user,
        )
        self.version = CampaignVersion.objects.create(
            campaign=self.campaign,
            version_number=1,
            source_type=CampaignVersion.SourceType.EXCEL,
            status=CampaignVersion.Status.PUBLISHED,
            created_by=self.user,
        )
        self.campaign.current_version = self.version
        self.campaign.save(update_fields=["current_version"])
        self.checklist = ChecklistTemplate.objects.create(
            code="SHOP_CONFIRM",
            name="PGD xác nhận lỗi",
            created_by=self.user,
        )
        ChecklistQuestion.objects.create(
            template=self.checklist,
            code="CONFIRM",
            label="PGD phản hồi",
            question_type=ChecklistQuestion.QuestionType.SINGLE,
            options=["PGD xác nhận lỗi", "PGD hẹn bổ sung chứng từ"],
            is_required=True,
        )
        self.error_1 = self._create_error("document:1001", 1001)
        self.error_2 = self._create_error("document:1002", 1002)
        self.link, self.raw_token = issue_shop_access_link(
            campaign=self.campaign,
            shop=self.shop,
            allowed_email=self.shop.shop_email,
            created_by=self.user,
        )

    def _create_error(self, source_key, source_id):
        return CampaignError.objects.create(
            campaign=self.campaign,
            version=self.version,
            source_key=source_key,
            source_object_id=source_id,
            error_type=CampaignError.ErrorType.DOCUMENT,
            shop=self.shop,
            area_manager=self.area,
            region=self.region,
            contract_code=f"HD{source_id}",
            checking_issue="Thiếu chữ ký khách hàng",
            checklist_template=self.checklist,
            status=CampaignError.Status.WAITING_SHOP,
        )

    def _post_json(self, url, payload):
        return self.client.post(url, data=json.dumps(payload), content_type="application/json")

    def test_response_page_and_health_are_available(self):
        health = self.client.get(reverse("document_campaigns:health"))
        page = self.client.get(
            reverse("document_campaigns:shop_response", kwargs={"raw_token": self.raw_token})
        )

        self.assertEqual(health.status_code, 200)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "PGD Test Autosave")
        self.assertContains(page, "Thiếu chữ ký khách hàng", count=2)

    def test_response_dropdown_can_fall_back_to_campaign_type_checklist(self):
        self.campaign_type.shop_checklist_template = self.checklist
        self.campaign_type.save(update_fields=["shop_checklist_template"])
        CampaignError.objects.filter(pk__in=[self.error_1.pk, self.error_2.pk]).update(
            checklist_template=None
        )

        page = self.client.get(
            reverse("document_campaigns:shop_response", kwargs={"raw_token": self.raw_token})
        )

        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "PGD xác nhận lỗi")
        self.assertContains(page, "PGD hẹn bổ sung chứng từ")
        self.assertContains(page, '<option value="" selected>— Chọn phản hồi —</option>', count=2)
        self.assertNotContains(page, '<option value="PGD hẹn bổ sung chứng từ" selected>')

    def test_supplement_answer_is_valid_and_remains_selected_after_autosave(self):
        autosave = self._post_json(
            reverse("document_campaigns:autosave_batch", kwargs={"raw_token": self.raw_token}),
            {
                "changes": [{
                    "error_uid": str(self.error_1.error_uid),
                    "version_no": 0,
                    "answer_code": "PGD hẹn bổ sung chứng từ",
                    "note": "",
                }]
            },
        )

        page = self.client.get(
            reverse("document_campaigns:shop_response", kwargs={"raw_token": self.raw_token})
        )

        self.assertEqual(autosave.status_code, 200)
        self.assertContains(
            page,
            '<option value="PGD hẹn bổ sung chứng từ" selected>PGD hẹn bổ sung chứng từ</option>',
            count=1,
        )

    def test_response_table_header_does_not_overlap_first_invalid_row(self):
        page = self.client.get(
            reverse("document_campaigns:shop_response", kwargs={"raw_token": self.raw_token})
        )

        self.assertContains(page, '<thead class="bg-gray-50')
        self.assertNotContains(page, 'sticky top-[65px]')

    def _scoped_user(self, username, role, *, region=None, shop=None, email=""):
        user = get_user_model().objects.create_user(username=username, email=email)
        user.groups.add(Group.objects.get_or_create(name=role)[0])
        UserProfile.objects.create(
            user=user,
            department="Vận hành",
            region=region,
            shop=shop,
        )
        return user

    def _create_foreign_shop_error(self):
        region = Region.objects.create(region_code="OTHER", region_name="Vùng khác")
        area = AreaManager.objects.create(
            areaManager_code="AREA02",
            areaManager_name="QLKV khác",
            areaManager_email="other-area@example.com",
        )
        region_manager = RegionManager.objects.create(
            regionManager_code="QLV02",
            regionManager_name="QLV khác",
            regionManager_email="other-region@example.com",
        )
        manager = Manager.objects.create(
            manager_code="MANAGER02",
            areaManager=area,
            regionManager=region_manager,
            qlkv_code="QLKV02",
            qlkv_name="QLKV khác",
            qlkv_email="other-area@example.com",
            qlv_code="QLV02",
            qlv_name="QLV khác",
            qlv_email="other-region@example.com",
        )
        shop = Shop.objects.create(
            shop_code=9002,
            shop_name="PGD Ngoài phạm vi",
            shop_email="other-shop@example.com",
            manager_id=manager,
            region_id=region,
        )
        CampaignError.objects.create(
            campaign=self.campaign,
            version=self.version,
            source_key="document:foreign",
            source_object_id=2001,
            error_type=CampaignError.ErrorType.DOCUMENT,
            shop=shop,
            area_manager=area,
            region=region,
            contract_code="HD2001",
            checking_issue="Lỗi ngoài phạm vi",
            checklist_template=self.checklist,
            status=CampaignError.Status.WAITING_SHOP,
        )
        return shop

    def test_admin_monitor_lists_shops_and_opens_response_detail(self):
        admin = self._scoped_user("monitor-admin", "admin")
        self.client.force_login(admin)

        listing = self.client.get(
            reverse(
                "document_campaigns:campaign_response_monitor",
                kwargs={"campaign_id": self.campaign.pk},
            )
        )
        detail = self.client.get(
            reverse(
                "document_campaigns:shop_response_monitor_detail",
                kwargs={"campaign_id": self.campaign.pk, "shop_id": self.shop.pk},
            )
        )

        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, "PGD Test Autosave")
        self.assertContains(listing, "Chưa phản hồi")
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Thiếu chữ ký khách hàng", count=2)

    def test_admin_can_issue_and_copy_a_new_shop_link_from_response_monitor(self):
        admin = self._scoped_user("link-admin", "admin")
        self.client.force_login(admin)
        monitor = self.client.get(
            reverse(
                "document_campaigns:campaign_response_monitor",
                kwargs={"campaign_id": self.campaign.pk},
            )
        )
        issue_url = reverse(
            "document_campaigns:issue_campaign_shop_link",
            kwargs={"campaign_id": self.campaign.pk, "shop_id": self.shop.pk},
        )

        response = self.client.post(issue_url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

        self.assertContains(monitor, "Phát hành tới PGD")
        self.assertContains(monitor, "PGD Test Autosave")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        raw_token = response.json()["url"].rstrip("/").split("/")[-1]
        self.assertEqual(resolve_shop_access_link(raw_token).shop, self.shop)
        old_link = self.client.get(
            reverse("document_campaigns:shop_response", kwargs={"raw_token": self.raw_token})
        )
        self.assertEqual(old_link.status_code, 410)

    def test_admin_can_publish_all_shop_links_without_sending_email(self):
        admin = self._scoped_user("publish-admin", "admin")
        self.client.force_login(admin)

        response = self.client.post(
            reverse(
                "document_campaigns:publish_campaign_to_shops",
                kwargs={"campaign_id": self.campaign.pk},
            ),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["links"][0]["shop_code"], self.shop.shop_code)
        self.assertIn("/respond/", response.json()["links"][0]["url"])
        self.assertEqual(len(mail.outbox), 0)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, Campaign.Status.ACTIVE)
        self.assertIsNotNone(self.campaign.response_opens_at)
        old_link = self.client.get(
            reverse("document_campaigns:shop_response", kwargs={"raw_token": self.raw_token})
        )
        self.assertEqual(old_link.status_code, 410)

    def test_non_admin_cannot_issue_shop_link(self):
        shop_user = self._scoped_user("link-shop", "shop", shop=self.shop)
        self.client.force_login(shop_user)

        response = self.client.post(
            reverse(
                "document_campaigns:issue_campaign_shop_link",
                kwargs={"campaign_id": self.campaign.pk, "shop_id": self.shop.pk},
            )
        )

        self.assertEqual(response.status_code, 403)

    def test_admin_can_configure_deadline_for_existing_campaign(self):
        admin = self._scoped_user("deadline-admin", "admin")
        self.client.force_login(admin)
        new_deadline = timezone.now() + timedelta(days=14)

        response = self.client.post(
            reverse(
                "document_campaigns:update_campaign_deadline",
                kwargs={"campaign_id": self.campaign.pk},
            ),
            {"response_deadline": new_deadline.strftime("%Y-%m-%dT%H:%M")},
        )

        self.assertRedirects(
            response,
            reverse("document_campaigns:campaign_detail", kwargs={"campaign_id": self.campaign.pk}),
        )
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.link_expires_at - self.campaign.response_deadline, timedelta(days=31))

    def test_admin_can_edit_campaign_name_and_deadline_from_settings_popup(self):
        admin = self._scoped_user("settings-admin", "admin")
        self.client.force_login(admin)
        new_deadline = timezone.now() + timedelta(days=20)

        response = self.client.post(
            reverse(
                "document_campaigns:update_campaign_settings",
                kwargs={"campaign_id": self.campaign.pk},
            ),
            {
                "name": "Book lỗi chứng từ tháng 09 - Đã cập nhật",
                "response_deadline": new_deadline.strftime("%Y-%m-%dT%H:%M"),
            },
        )

        self.assertRedirects(
            response,
            reverse("document_campaigns:campaign_detail", kwargs={"campaign_id": self.campaign.pk}),
        )
        self.campaign.refresh_from_db()
        self.link.refresh_from_db()
        self.assertEqual(self.campaign.name, "Book lỗi chứng từ tháng 09 - Đã cập nhật")
        self.assertEqual(self.link.response_deadline, self.campaign.response_deadline)
        self.assertEqual(self.link.expires_at, self.campaign.link_expires_at)

    def test_campaign_settings_popup_is_admin_only(self):
        shop_user = self._scoped_user("settings-shop", "shop", shop=self.shop)
        self.client.force_login(shop_user)

        detail = self.client.get(
            reverse("document_campaigns:campaign_detail", kwargs={"campaign_id": self.campaign.pk})
        )
        update = self.client.post(
            reverse(
                "document_campaigns:update_campaign_settings",
                kwargs={"campaign_id": self.campaign.pk},
            ),
            {
                "name": "Không được phép",
                "response_deadline": (timezone.now() + timedelta(days=10)).strftime("%Y-%m-%dT%H:%M"),
            },
        )

        self.assertNotContains(detail, "Cài đặt chiến dịch")
        self.assertEqual(update.status_code, 403)

    def test_region_and_shop_monitor_cannot_view_outside_scope(self):
        foreign_shop = self._create_foreign_shop_error()
        region_user = self._scoped_user(
            "region-monitor", "supervisor", region=self.region, email="region@example.com"
        )
        self.client.force_login(region_user)
        listing = self.client.get(
            reverse(
                "document_campaigns:campaign_response_monitor",
                kwargs={"campaign_id": self.campaign.pk},
            )
        )
        self.assertContains(listing, "PGD Test Autosave")
        self.assertNotContains(listing, "PGD Ngoài phạm vi")

        profile_region_only = self._scoped_user(
            "profile-region-only", "checker", region=self.region
        )
        self.client.force_login(profile_region_only)
        no_manager_scope = self.client.get(
            reverse(
                "document_campaigns:campaign_response_monitor",
                kwargs={"campaign_id": self.campaign.pk},
            )
        )
        self.assertNotContains(no_manager_scope, "PGD Test Autosave")

        shop_user = self._scoped_user("shop-monitor", "shop", shop=self.shop)
        self.client.force_login(shop_user)
        forbidden_detail = self.client.get(
            reverse(
                "document_campaigns:shop_response_monitor_detail",
                kwargs={"campaign_id": self.campaign.pk, "shop_id": foreign_shop.pk},
            )
        )
        self.assertEqual(forbidden_detail.status_code, 404)

    def test_area_monitor_is_derived_from_manager_email(self):
        self._create_foreign_shop_error()
        area_user = self._scoped_user(
            "area-monitor",
            "supervisor",
            email="area@example.com",
        )
        self.client.force_login(area_user)

        listing = self.client.get(
            reverse(
                "document_campaigns:campaign_response_monitor",
                kwargs={"campaign_id": self.campaign.pk},
            )
        )

        self.assertContains(listing, "Phạm vi: QLKV test")
        self.assertContains(listing, "PGD Test Autosave")
        self.assertNotContains(listing, "PGD Ngoài phạm vi")

    def test_autosave_batches_rows_and_increments_versions(self):
        url = reverse("document_campaigns:autosave_batch", kwargs={"raw_token": self.raw_token})
        response = self._post_json(
            url,
            {
                "changes": [
                    {
                        "error_uid": str(self.error_1.error_uid),
                        "version_no": 0,
                        "answer_code": "PGD xác nhận lỗi",
                        "note": "Dòng một",
                    },
                    {
                        "error_uid": str(self.error_2.error_uid),
                        "version_no": 0,
                        "answer_code": "PGD hẹn bổ sung chứng từ",
                        "note": "Dòng hai",
                    },
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ShopResponse.objects.count(), 2)
        self.assertEqual({item["version_no"] for item in response.json()["saved"]}, {1})

    def test_stale_autosave_returns_conflict_without_overwriting(self):
        url = reverse("document_campaigns:autosave_batch", kwargs={"raw_token": self.raw_token})
        first = {
            "changes": [{
                "error_uid": str(self.error_1.error_uid),
                "version_no": 0,
                "answer_code": "PGD xác nhận lỗi",
                "note": "Bản mới",
            }]
        }
        self.assertEqual(self._post_json(url, first).status_code, 200)
        stale = dict(first)
        stale["changes"] = [dict(first["changes"][0], note="Bản ghi đè")]
        response = self._post_json(url, stale)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(ShopResponse.objects.get(error=self.error_1).note, "Bản mới")

    def test_submit_is_idempotent_and_locks_future_autosave(self):
        autosave_url = reverse("document_campaigns:autosave_batch", kwargs={"raw_token": self.raw_token})
        changes = [
            {"error_uid": str(error.error_uid), "version_no": 0, "answer_code": "PGD xác nhận lỗi"}
            for error in [self.error_1, self.error_2]
        ]
        self.assertEqual(self._post_json(autosave_url, {"changes": changes}).status_code, 200)
        submit_url = reverse("document_campaigns:submit_responses", kwargs={"raw_token": self.raw_token})

        first = self._post_json(submit_url, {"idempotency_key": "stable-submit-key"})
        second = self._post_json(submit_url, {"idempotency_key": "stable-submit-key"})
        locked = self._post_json(
            autosave_url,
            {"changes": [{"error_uid": str(self.error_1.error_uid), "version_no": 1, "answer_code": "Khác"}]},
        )

        self.assertEqual(first.status_code, 200)
        self.assertFalse(first.json()["idempotent"])
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["idempotent"])
        self.assertEqual(ShopSubmission.objects.count(), 1)
        self.assertEqual(locked.status_code, 423)

    def test_submit_reports_exact_rows_missing_required_dropdown(self):
        autosave_url = reverse("document_campaigns:autosave_batch", kwargs={"raw_token": self.raw_token})
        self.assertEqual(
            self._post_json(
                autosave_url,
                {
                    "changes": [{
                        "error_uid": str(self.error_1.error_uid),
                        "version_no": 0,
                        "answer_code": "PGD xác nhận lỗi",
                        "note": "",
                    }]
                },
            ).status_code,
            200,
        )

        response = self._post_json(
            reverse("document_campaigns:submit_responses", kwargs={"raw_token": self.raw_token}),
            {"idempotency_key": "missing-dropdown-key"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["missing_uids"], [str(self.error_2.error_uid)])
        self.assertIn("1 dòng chưa chọn", response.json()["error"])

    @patch("app_document_campaigns.tasks.process_shop_submission.delay")
    def test_submit_enqueues_post_submit_task_only_after_commit(self, delay):
        autosave_url = reverse("document_campaigns:autosave_batch", kwargs={"raw_token": self.raw_token})
        changes = [
            {"error_uid": str(error.error_uid), "version_no": 0, "answer_code": "PGD xác nhận lỗi"}
            for error in [self.error_1, self.error_2]
        ]
        self.assertEqual(self._post_json(autosave_url, {"changes": changes}).status_code, 200)
        submit_url = reverse("document_campaigns:submit_responses", kwargs={"raw_token": self.raw_token})

        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            response = self._post_json(submit_url, {"idempotency_key": "async-submit-key"})
            self.assertEqual(response.status_code, 200)
            delay.assert_not_called()

        self.assertEqual(len(callbacks), 1)
        callbacks[0]()
        submission = ShopSubmission.objects.get()
        delay.assert_called_once_with(submission.pk)

        with self.captureOnCommitCallbacks(execute=True) as duplicate_callbacks:
            duplicate = self._post_json(submit_url, {"idempotency_key": "async-submit-key"})
        self.assertTrue(duplicate.json()["idempotent"])
        self.assertEqual(duplicate_callbacks, [])
        delay.assert_called_once_with(submission.pk)

    @patch("app_document_campaigns.services.responses.logger.exception")
    @patch("app_document_campaigns.tasks.process_shop_submission.delay", side_effect=RuntimeError("broker down"))
    def test_broker_outage_does_not_break_committed_submission(self, delay, log_exception):
        autosave_url = reverse("document_campaigns:autosave_batch", kwargs={"raw_token": self.raw_token})
        changes = [
            {"error_uid": str(error.error_uid), "version_no": 0, "answer_code": "PGD xác nhận lỗi"}
            for error in [self.error_1, self.error_2]
        ]
        self.assertEqual(self._post_json(autosave_url, {"changes": changes}).status_code, 200)

        with self.captureOnCommitCallbacks(execute=True):
            response = self._post_json(
                reverse("document_campaigns:submit_responses", kwargs={"raw_token": self.raw_token}),
                {"idempotency_key": "broker-outage-key"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ShopSubmission.objects.count(), 1)
        delay.assert_called_once()
        log_exception.assert_called_once()

        read_only_page = self.client.get(
            reverse("document_campaigns:shop_response", kwargs={"raw_token": self.raw_token})
        )
        self.assertEqual(read_only_page.status_code, 200)
        self.assertNotContains(read_only_page, 'id="submit-responses"')
        self.assertEqual(read_only_page.content.count(b" disabled"), 4)

    def test_document_types_are_rendered_as_bullet_list(self):
        self.error_1.document_type_name = "Giấy đề nghị\nPhiếu chi giải ngân\nỦy quyền epay"
        self.error_1.save(update_fields=["document_type_name"])

        page = self.client.get(
            reverse("document_campaigns:shop_response", kwargs={"raw_token": self.raw_token})
        )

        self.assertContains(page, '<ul class="dec-document-types">')
        self.assertContains(page, "<li>Giấy đề nghị</li>")
        self.assertContains(page, "<li>Phiếu chi giải ngân</li>")
        self.assertContains(page, "<li>Ủy quyền epay</li>")

    def test_post_submit_task_sends_confirmation_without_access_token(self):
        autosave_url = reverse("document_campaigns:autosave_batch", kwargs={"raw_token": self.raw_token})
        changes = [
            {"error_uid": str(error.error_uid), "version_no": 0, "answer_code": "PGD xác nhận lỗi"}
            for error in [self.error_1, self.error_2]
        ]
        self.assertEqual(self._post_json(autosave_url, {"changes": changes}).status_code, 200)
        with self.captureOnCommitCallbacks(execute=False):
            self._post_json(
                reverse("document_campaigns:submit_responses", kwargs={"raw_token": self.raw_token}),
                {"idempotency_key": "email-submit-key"},
            )
        submission = ShopSubmission.objects.get()

        result = process_shop_submission.run(submission.pk)

        self.assertEqual(result["status"], "sent")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.shop.shop_email])
        self.assertNotIn(self.raw_token, mail.outbox[0].body)

    def test_expired_link_is_rejected(self):
        self.link.expires_at = timezone.now() - timedelta(seconds=1)
        self.link.save(update_fields=["expires_at"])
        response = self.client.get(
            reverse("document_campaigns:shop_response", kwargs={"raw_token": self.raw_token})
        )
        self.assertEqual(response.status_code, 410)
