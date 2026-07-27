import json
from datetime import datetime, timedelta

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    CollateralRegistration,
    CollateralRegistrationExternalIdentity,
    CollateralRegistrationImportBatch,
    CollateralRegistrationLog,
    CollateralRegistrationReason,
    CollateralRegistrationReasonType,
    CollateralRegistrationStatus,
    UserProfile,
)


class CollateralRegistrationCaseClaimTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        checker_group = Group.objects.create(name="checker")
        admin_group = Group.objects.create(name="admin")
        cls.checker_one = User.objects.create_user(username="checker_one", password="test")
        cls.checker_two = User.objects.create_user(username="checker_two", password="test")
        cls.checker_one.groups.add(checker_group)
        cls.checker_two.groups.add(checker_group)
        UserProfile.objects.create(user=cls.checker_one, department="Vận hành")
        UserProfile.objects.create(user=cls.checker_two, department="Vận hành")
        cls.admin = User.objects.create_user(
            username="gddb_admin",
            password="test",
        )
        cls.admin.groups.add(admin_group)
        UserProfile.objects.create(user=cls.admin, department="Vận hành")
        cls.identity = CollateralRegistrationExternalIdentity.objects.create(
            external_code="ketoan_test",
            is_active=True,
        )

    def setUp(self):
        self.registration = CollateralRegistration.objects.create(contract_code="HD-CLAIM-001")

    def _post(self, user, url, payload):
        client = Client()
        client.force_login(user)
        return client.post(url, data=json.dumps(payload), content_type="application/json")

    def test_only_one_checker_can_claim_pending_case(self):
        claim_url = reverse("api_gddb_case_claim", args=[self.registration.pk])

        first_response = self._post(self.checker_one, claim_url, {"action": "claim"})
        second_response = self._post(self.checker_two, claim_url, {"action": "claim"})

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 409)
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.processing_by, self.checker_one)
        self.assertIsNotNone(self.registration.processing_expires_at)
        remaining = self.registration.processing_expires_at - timezone.now()
        self.assertGreater(remaining, timedelta(hours=3, minutes=59))
        self.assertLessEqual(remaining, timedelta(hours=4))

    def test_release_clears_current_owner_and_preserves_history(self):
        claim_url = reverse("api_gddb_case_claim", args=[self.registration.pk])
        self._post(self.checker_one, claim_url, {"action": "claim"})

        response = self._post(self.checker_one, claim_url, {"action": "release"})

        self.assertEqual(response.status_code, 200)
        self.registration.refresh_from_db()
        self.assertIsNone(self.registration.processing_by)
        self.assertIsNone(self.registration.processing_started_at)
        self.assertIsNone(self.registration.processing_expires_at)
        release_log = CollateralRegistrationLog.objects.get(
            registration=self.registration,
            action="case_release",
        )
        self.assertEqual(
            release_log.metadata["previous_owner_username"],
            self.checker_one.username,
        )

    def test_case_owner_can_edit_completed_case_but_other_checker_cannot(self):
        claim_url = reverse("api_gddb_case_claim", args=[self.registration.pk])
        update_url = reverse("api_gddb_update", args=[self.registration.pk])
        self._post(self.checker_one, claim_url, {"action": "claim"})

        register_response = self._post(self.checker_one, update_url, {
            "gddb_status": CollateralRegistrationStatus.REGISTERED,
            "registered_identity_id": self.identity.pk,
            "reason": "Đăng ký mới",
        })
        self.assertEqual(register_response.status_code, 200)
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.processing_by, self.checker_one)
        self.assertIsNone(self.registration.processing_expires_at)

        denied_response = self._post(self.checker_two, update_url, {
            "gddb_status": CollateralRegistrationStatus.NOT_REGISTERED,
            "reason": "Hợp đồng hết hiệu lực",
        })
        self.assertEqual(denied_response.status_code, 409)

        owner_edit_response = self._post(self.checker_one, update_url, {
            "gddb_status": CollateralRegistrationStatus.NOT_REGISTERED,
            "reason": "Hợp đồng hết hiệu lực",
            "status_change_reason": "Thao tác nhầm",
        })
        self.assertEqual(owner_edit_response.status_code, 200)

    def test_admin_configured_reason_is_used_by_popup_and_api(self):
        custom_reason = CollateralRegistrationReason.objects.create(
            reason_type=CollateralRegistrationReasonType.REGISTRATION,
            reason_text="Đăng ký theo yêu cầu kiểm soát",
            sort_order=5,
            created_by=self.admin,
            updated_by=self.admin,
        )
        client = Client()
        client.force_login(self.checker_one)
        page_response = client.get(reverse("gddb_registration_v2"))
        self.assertContains(page_response, custom_reason.reason_text)

        self._post(
            self.checker_one,
            reverse("api_gddb_case_claim", args=[self.registration.pk]),
            {"action": "claim"},
        )
        update_response = self._post(
            self.checker_one,
            reverse("api_gddb_update", args=[self.registration.pk]),
            {
                "gddb_status": CollateralRegistrationStatus.REGISTERED,
                "registered_identity_id": self.identity.pk,
                "reason": custom_reason.reason_text,
            },
        )
        self.assertEqual(update_response.status_code, 200)
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.reason, custom_reason.reason_text)

    def test_application_admin_can_create_and_disable_reason_catalog_item(self):
        client = Client()
        client.force_login(self.admin)
        create_response = client.post(
            reverse("gddb_reason_save"),
            {
                "reason_type": CollateralRegistrationReasonType.STATUS_CHANGE,
                "reason_text": "Điều chỉnh theo kiểm soát nội bộ",
                "sort_order": "15",
            },
        )
        self.assertEqual(create_response.status_code, 302)
        reason = CollateralRegistrationReason.objects.get(
            reason_type=CollateralRegistrationReasonType.STATUS_CHANGE,
            reason_text="Điều chỉnh theo kiểm soát nội bộ",
        )
        self.assertTrue(reason.is_active)
        self.assertEqual(reason.sort_order, 15)
        self.assertEqual(reason.created_by, self.admin)

        update_response = client.post(
            reverse("gddb_reason_save"),
            {
                "reason_id": reason.pk,
                "sort_order": "25",
            },
        )
        self.assertEqual(update_response.status_code, 302)
        reason.refresh_from_db()
        self.assertFalse(reason.is_active)
        self.assertEqual(reason.sort_order, 25)
        self.assertEqual(reason.updated_by, self.admin)

        config_response = client.get(
            reverse("gddb_registration_v2"),
            {"tab": "configuration"},
        )
        self.assertContains(config_response, "Danh mục lý do GDĐB")
        self.assertContains(config_response, reason.reason_text)

        checker_client = Client()
        checker_client.force_login(self.checker_one)
        denied_response = checker_client.post(
            reverse("gddb_reason_save"),
            {
                "reason_type": CollateralRegistrationReasonType.REGISTRATION,
                "reason_text": "Không được tạo",
            },
        )
        self.assertEqual(denied_response.status_code, 403)

    def test_inactive_reason_is_hidden_and_rejected_for_new_decision(self):
        reason = CollateralRegistrationReason.objects.get(
            reason_type=CollateralRegistrationReasonType.NON_REGISTRATION,
            reason_text="Hợp đồng hết hiệu lực",
        )
        reason.is_active = False
        reason.save(update_fields=["is_active"])

        client = Client()
        client.force_login(self.checker_one)
        page_response = client.get(reverse("gddb_registration_v2"))
        self.assertNotContains(page_response, ">Hợp đồng hết hiệu lực</option>")

        self._post(
            self.checker_one,
            reverse("api_gddb_case_claim", args=[self.registration.pk]),
            {"action": "claim"},
        )
        update_response = self._post(
            self.checker_one,
            reverse("api_gddb_update", args=[self.registration.pk]),
            {
                "gddb_status": CollateralRegistrationStatus.NOT_REGISTERED,
                "reason": reason.reason_text,
            },
        )
        self.assertEqual(update_response.status_code, 400)
        self.assertIn("lý do không đăng ký", update_response.json()["error"])

    def test_status_correction_requires_a_tracked_reason(self):
        claim_url = reverse("api_gddb_case_claim", args=[self.registration.pk])
        update_url = reverse("api_gddb_update", args=[self.registration.pk])
        self._post(self.checker_one, claim_url, {"action": "claim"})
        self._post(self.checker_one, update_url, {
            "gddb_status": CollateralRegistrationStatus.REGISTERED,
            "registered_identity_id": self.identity.pk,
            "reason": "Đăng ký mới",
        })

        response = self._post(self.checker_one, update_url, {
            "gddb_status": CollateralRegistrationStatus.NOT_REGISTERED,
            "reason": "Hợp đồng hết hiệu lực",
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn("lý do điều chỉnh", response.json()["error"])
        self.registration.refresh_from_db()
        self.assertEqual(
            self.registration.gddb_status,
            CollateralRegistrationStatus.REGISTERED,
        )

    def test_status_correction_is_logged_and_visible_in_case_history(self):
        claim_url = reverse("api_gddb_case_claim", args=[self.registration.pk])
        update_url = reverse("api_gddb_update", args=[self.registration.pk])
        self._post(self.checker_one, claim_url, {"action": "claim"})
        self._post(self.checker_one, update_url, {
            "gddb_status": CollateralRegistrationStatus.REGISTERED,
            "registered_identity_id": self.identity.pk,
            "reason": "Đăng ký mới",
        })

        response = self._post(self.checker_one, update_url, {
            "gddb_status": CollateralRegistrationStatus.NOT_REGISTERED,
            "reason": "Hợp đồng hết hiệu lực",
            "status_change_reason": "TDTD/VH yêu cầu đăng ký bổ sung",
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["status_history_changed"])
        correction_log = CollateralRegistrationLog.objects.get(
            registration=self.registration,
            action="status_update",
            from_status=CollateralRegistrationStatus.REGISTERED,
            to_status=CollateralRegistrationStatus.NOT_REGISTERED,
        )
        self.assertEqual(
            correction_log.metadata["status_change_reason"],
            "TDTD/VH yêu cầu đăng ký bổ sung",
        )
        self.assertEqual(correction_log.created_by, self.checker_one)

        client = Client()
        client.force_login(self.checker_one)
        history_response = client.get(
            reverse("gddb_registration_v2"),
            {"queue": "mine", "mine_step": "registered_history"},
        )
        history_item = next(
            item
            for item in history_response.context["page_obj"].object_list
            if item.pk == self.registration.pk
        )
        self.assertEqual(len(history_item.case_status_history), 1)
        self.assertContains(history_response, "Lịch sử trạng thái case")
        self.assertContains(
            history_response,
            "TDTD/VH yêu cầu đăng ký bổ sung",
        )
        self.assertContains(history_response, "data-status-change-reason")
        self.assertContains(
            history_response,
            'name="gddb_register_postmini_status"',
        )

    def test_gear_update_can_restore_registration_and_update_postmini(self):
        CollateralRegistration.objects.filter(pk=self.registration.pk).update(
            gddb_status=CollateralRegistrationStatus.NOT_REGISTERED,
            reason="Hợp đồng hết hiệu lực",
            processing_by=self.checker_one,
            archived_at=timezone.now(),
        )

        response = self._post(
            self.checker_one,
            reverse("api_gddb_update", args=[self.registration.pk]),
            {
                "gddb_status": CollateralRegistrationStatus.REGISTERED,
                "registered_identity_id": self.identity.pk,
                "reason": "Đăng ký lại",
                "status_change_reason": "Điều chỉnh GDBD",
                "postmini_updated": "Đã cập nhật",
                "note": "Điều chỉnh đầy đủ trong răng cưa",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["archived"])
        self.registration.refresh_from_db()
        self.assertEqual(
            self.registration.gddb_status,
            CollateralRegistrationStatus.REGISTERED,
        )
        self.assertEqual(self.registration.postmini_updated, "Đã cập nhật")
        self.assertEqual(
            self.registration.note,
            "Điều chỉnh đầy đủ trong răng cưa",
        )
        correction_log = CollateralRegistrationLog.objects.get(
            registration=self.registration,
            action="status_update",
            from_status=CollateralRegistrationStatus.NOT_REGISTERED,
            to_status=CollateralRegistrationStatus.REGISTERED,
        )
        self.assertEqual(
            correction_log.metadata["from_postmini_status"],
            "Chưa cập nhật",
        )
        self.assertEqual(
            correction_log.metadata["to_postmini_status"],
            "Đã cập nhật",
        )

    def test_expired_pending_claim_can_be_taken_over(self):
        claim_url = reverse("api_gddb_case_claim", args=[self.registration.pk])
        update_url = reverse("api_gddb_update", args=[self.registration.pk])
        self._post(self.checker_one, claim_url, {"action": "claim"})
        CollateralRegistration.objects.filter(pk=self.registration.pk).update(
            processing_expires_at=timezone.now() - timedelta(seconds=1)
        )

        takeover_response = self._post(self.checker_two, claim_url, {"action": "claim"})
        stale_owner_response = self._post(self.checker_one, update_url, {
            "gddb_status": CollateralRegistrationStatus.NOT_REGISTERED,
            "reason": "Hợp đồng hết hiệu lực",
        })

        self.assertEqual(takeover_response.status_code, 200)
        self.assertEqual(stale_owner_response.status_code, 409)
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.processing_by, self.checker_two)

    def test_admin_can_edit_case_owned_by_checker(self):
        claim_url = reverse("api_gddb_case_claim", args=[self.registration.pk])
        update_url = reverse("api_gddb_update", args=[self.registration.pk])
        self._post(self.checker_one, claim_url, {"action": "claim"})

        response = self._post(self.admin, update_url, {
            "gddb_status": CollateralRegistrationStatus.REGISTERED,
            "registered_identity_id": self.identity.pk,
            "reason": "Đăng ký mới",
        })

        self.assertEqual(response.status_code, 200)
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.processing_by, self.checker_one)
        self.assertEqual(self.registration.updated_by, self.admin)

    def test_other_checker_cannot_update_note_or_postmini(self):
        claim_url = reverse("api_gddb_case_claim", args=[self.registration.pk])
        update_url = reverse("api_gddb_update", args=[self.registration.pk])
        note_url = reverse("api_gddb_note_update", args=[self.registration.pk])
        postmini_url = reverse("api_gddb_postmini_update", args=[self.registration.pk])
        self._post(self.checker_one, claim_url, {"action": "claim"})
        self._post(self.checker_one, update_url, {
            "gddb_status": CollateralRegistrationStatus.REGISTERED,
            "registered_identity_id": self.identity.pk,
            "reason": "Đăng ký mới",
        })

        note_response = self._post(self.checker_two, note_url, {"note": "Không được lưu"})
        postmini_response = self._post(self.checker_two, postmini_url, {
            "postmini_updated": "Đã cập nhật",
            "note": "Không được lưu",
        })

        self.assertEqual(note_response.status_code, 409)
        self.assertEqual(postmini_response.status_code, 409)

    def test_bulk_claim_accepts_same_batch_and_source(self):
        batch = CollateralRegistrationImportBatch.objects.create(source_type="api")
        first = CollateralRegistration.objects.create(
            contract_code="HD-BULK-001",
            import_batch=batch,
            disbursement_source="CIMB Fund",
        )
        second = CollateralRegistration.objects.create(
            contract_code="HD-BULK-002",
            import_batch=batch,
            disbursement_source="CIMB",
        )

        response = self._post(self.checker_one, reverse("api_gddb_bulk_claim"), {
            "action": "claim",
            "registration_ids": [first.pk, second.pk],
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["claimed_count"], 2)
        self.assertEqual(
            CollateralRegistration.objects.filter(
                pk__in=[first.pk, second.pk],
                processing_by=self.checker_one,
                processing_expires_at__isnull=False,
            ).count(),
            2,
        )

    def test_bulk_claim_groups_imports_from_same_business_batch_slot(self):
        business_date = timezone.now().date()
        first_batch = CollateralRegistrationImportBatch.objects.create(
            source_type="api",
            business_date=business_date,
            slot_number=2,
        )
        second_batch = CollateralRegistrationImportBatch.objects.create(
            source_type="api",
            business_date=business_date,
            slot_number=2,
        )
        first = CollateralRegistration.objects.create(
            contract_code="HD-BUSINESS-BATCH-001",
            import_batch=first_batch,
            disbursement_source="F88 Fund",
        )
        second = CollateralRegistration.objects.create(
            contract_code="HD-BUSINESS-BATCH-002",
            import_batch=second_batch,
            disbursement_source="F88",
        )

        response = self._post(
            self.checker_one,
            reverse("api_gddb_bulk_claim"),
            {
                "action": "claim",
                "registration_ids": [first.pk, second.pk],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["claimed_count"], 2)

    def test_bulk_claim_rejects_mixed_sources_or_batches(self):
        first_batch = CollateralRegistrationImportBatch.objects.create(source_type="api")
        second_batch = CollateralRegistrationImportBatch.objects.create(
            source_type="api",
            business_date=first_batch.business_date,
            slot_number=(first_batch.slot_number % 4) + 1,
        )
        cimb = CollateralRegistration.objects.create(
            contract_code="HD-MIX-001",
            import_batch=first_batch,
            disbursement_source="CIMB Fund",
        )
        f88 = CollateralRegistration.objects.create(
            contract_code="HD-MIX-002",
            import_batch=first_batch,
            disbursement_source="F88 Fund",
        )
        other_batch_cimb = CollateralRegistration.objects.create(
            contract_code="HD-MIX-003",
            import_batch=second_batch,
            disbursement_source="CIMB Fund",
        )
        bulk_url = reverse("api_gddb_bulk_claim")

        mixed_source_response = self._post(self.checker_one, bulk_url, {
            "action": "claim",
            "registration_ids": [cimb.pk, f88.pk],
        })
        mixed_batch_response = self._post(self.checker_one, bulk_url, {
            "action": "claim",
            "registration_ids": [cimb.pk, other_batch_cimb.pk],
        })

        self.assertEqual(mixed_source_response.status_code, 409)
        self.assertEqual(mixed_batch_response.status_code, 409)

    def test_blank_source_is_grouped_as_mb(self):
        batch = CollateralRegistrationImportBatch.objects.create(source_type="api")
        blank_source = CollateralRegistration.objects.create(
            contract_code="HD-MB-001",
            import_batch=batch,
            disbursement_source=None,
        )
        explicit_mb = CollateralRegistration.objects.create(
            contract_code="HD-MB-002",
            import_batch=batch,
            disbursement_source="MB",
        )

        response = self._post(self.checker_one, reverse("api_gddb_bulk_claim"), {
            "action": "claim",
            "registration_ids": [blank_source.pk, explicit_mb.pk],
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn("MB", response.json()["group_label"])

    def test_list_can_filter_multiple_loan_sources(self):
        f88_case = CollateralRegistration.objects.create(
            contract_code="HD-FILTER-F88",
            disbursement_source="F88 Fund",
        )
        cimb_case = CollateralRegistration.objects.create(
            contract_code="HD-FILTER-CIMB",
            disbursement_source="CIMB",
        )
        client = Client()
        client.force_login(self.checker_one)

        response = client.get(
            reverse("gddb_registration_v2"),
            {
                "queue": "all",
                "loan_source": ["f88", "cimb"],
            },
        )

        listed_ids = [item.pk for item in response.context["page_obj"].object_list]
        self.assertIn(f88_case.pk, listed_ids)
        self.assertIn(cimb_case.pk, listed_ids)
        self.assertNotIn(self.registration.pk, listed_ids)
        self.assertEqual(response.context["filters"]["loan_sources"], ["f88", "cimb"])

    def test_checker_can_hold_cases_from_multiple_batch_source_groups(self):
        batch = CollateralRegistrationImportBatch.objects.create(source_type="api")
        first_cimb = CollateralRegistration.objects.create(
            contract_code="HD-GROUP-001",
            import_batch=batch,
            disbursement_source="CIMB Fund",
        )
        second_cimb = CollateralRegistration.objects.create(
            contract_code="HD-GROUP-002",
            import_batch=batch,
            disbursement_source="CIMB",
        )
        f88 = CollateralRegistration.objects.create(
            contract_code="HD-GROUP-003",
            import_batch=batch,
            disbursement_source="F88 Fund",
        )

        first_response = self._post(
            self.checker_one,
            reverse("api_gddb_case_claim", args=[first_cimb.pk]),
            {"action": "claim"},
        )
        same_group_response = self._post(
            self.checker_one,
            reverse("api_gddb_case_claim", args=[second_cimb.pk]),
            {"action": "claim"},
        )
        mixed_group_response = self._post(
            self.checker_one,
            reverse("api_gddb_case_claim", args=[f88.pk]),
            {"action": "claim"},
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(same_group_response.status_code, 200)
        self.assertEqual(mixed_group_response.status_code, 200)

    def test_separate_bulk_claims_can_hold_multiple_groups(self):
        cimb_batch = CollateralRegistrationImportBatch.objects.create(source_type="api")
        f88_batch = CollateralRegistrationImportBatch.objects.create(source_type="api")
        cimb_cases = [
            CollateralRegistration.objects.create(
                contract_code=f"HD-MULTI-CIMB-{index}",
                import_batch=cimb_batch,
                disbursement_source="CIMB Fund",
            )
            for index in range(2)
        ]
        f88_cases = [
            CollateralRegistration.objects.create(
                contract_code=f"HD-MULTI-F88-{index}",
                import_batch=f88_batch,
                disbursement_source="F88 Fund",
            )
            for index in range(2)
        ]
        bulk_url = reverse("api_gddb_bulk_claim")

        first_response = self._post(self.checker_one, bulk_url, {
            "action": "claim",
            "registration_ids": [case.pk for case in cimb_cases],
        })
        second_response = self._post(self.checker_one, bulk_url, {
            "action": "claim",
            "registration_ids": [case.pk for case in f88_cases],
        })

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(
            CollateralRegistration.objects.filter(
                pk__in=[case.pk for case in cimb_cases + f88_cases],
                processing_by=self.checker_one,
                processing_expires_at__gt=timezone.now(),
            ).count(),
            4,
        )

    def test_default_list_prioritizes_my_cases_and_pushes_other_users_cases_last(self):
        self.registration.delete()
        other_held_batch = CollateralRegistrationImportBatch.objects.create(source_type="api")
        old_batch = CollateralRegistrationImportBatch.objects.create(source_type="api")
        new_batch = CollateralRegistrationImportBatch.objects.create(source_type="api")
        held_batch = CollateralRegistrationImportBatch.objects.create(source_type="api")
        now = timezone.now()
        CollateralRegistrationImportBatch.objects.filter(pk=other_held_batch.pk).update(
            created_at=now - timedelta(days=4)
        )
        CollateralRegistrationImportBatch.objects.filter(pk=old_batch.pk).update(
            created_at=now - timedelta(days=3)
        )
        CollateralRegistrationImportBatch.objects.filter(pk=new_batch.pk).update(
            created_at=now - timedelta(days=1)
        )
        CollateralRegistrationImportBatch.objects.filter(pk=held_batch.pk).update(
            created_at=now,
        )
        old_case = CollateralRegistration.objects.create(
            contract_code="HD-ORDER-OLD",
            import_batch=old_batch,
        )
        new_case = CollateralRegistration.objects.create(
            contract_code="HD-ORDER-NEW",
            import_batch=new_batch,
        )
        other_held_case = CollateralRegistration.objects.create(
            contract_code="HD-ORDER-OTHER-HELD",
            import_batch=other_held_batch,
            processing_by=self.checker_two,
            processing_started_at=now,
            processing_expires_at=now + timedelta(minutes=10),
        )
        held_case = CollateralRegistration.objects.create(
            contract_code="HD-ORDER-HELD",
            import_batch=held_batch,
            processing_by=self.checker_one,
            processing_started_at=now,
            processing_expires_at=now + timedelta(minutes=10),
        )

        client = Client()
        client.force_login(self.checker_one)
        response = client.get(reverse("gddb_registration_v2"), {"queue": "all"})

        self.assertEqual(response.status_code, 200)
        listed_ids = [item.pk for item in response.context["page_obj"].object_list]
        self.assertEqual(listed_ids, [held_case.pk, old_case.pk, new_case.pk, other_held_case.pk])

        sorted_response = client.get(
            reverse("gddb_registration_v2"),
            {"queue": "all", "sort": "-created_at"},
        )
        sorted_ids = [item.pk for item in sorted_response.context["page_obj"].object_list]
        self.assertEqual(sorted_ids[0], held_case.pk)
        self.assertEqual(sorted_ids[-1], other_held_case.pk)

    def test_completed_postmini_archives_case_and_removes_it_from_work_queue(self):
        claim_response = self._post(
            self.checker_one,
            reverse("api_gddb_case_claim", args=[self.registration.pk]),
            {"action": "claim"},
        )
        register_response = self._post(
            self.checker_one,
            reverse("api_gddb_update", args=[self.registration.pk]),
            {
                "gddb_status": CollateralRegistrationStatus.REGISTERED,
                "registered_identity_id": self.identity.pk,
                "reason": "Đăng ký mới",
            },
        )
        postmini_response = self._post(
            self.checker_one,
            reverse("api_gddb_postmini_update", args=[self.registration.pk]),
            {"postmini_updated": "Đã cập nhật", "note": "Hoàn tất"},
        )

        self.assertEqual(claim_response.status_code, 200)
        self.assertEqual(register_response.status_code, 200)
        self.assertEqual(postmini_response.status_code, 200)
        self.assertTrue(postmini_response.json()["archived"])
        self.registration.refresh_from_db()
        self.assertIsNotNone(self.registration.archived_at)

        client = Client()
        client.force_login(self.checker_one)
        list_response = client.get(reverse("gddb_registration_v2"))
        listed_ids = [item.pk for item in list_response.context["page_obj"].object_list]
        self.assertNotIn(self.registration.pk, listed_ids)

    def test_checker_defaults_to_my_cases_while_admin_defaults_to_all_cases(self):
        mine = CollateralRegistration.objects.create(
            contract_code="HD-DEFAULT-MINE",
            processing_by=self.checker_one,
            processing_expires_at=timezone.now() + timedelta(minutes=10),
        )
        checker_client = Client()
        checker_client.force_login(self.checker_one)
        checker_response = checker_client.get(reverse("gddb_registration_v2"))

        checker_ids = [
            item.pk for item in checker_response.context["page_obj"].object_list
        ]
        self.assertEqual(checker_response.context["queue_scope"], "mine")
        self.assertEqual(checker_ids, [mine.pk])
        invalid_checker_response = checker_client.get(
            reverse("gddb_registration_v2"),
            {"queue": "invalid"},
        )
        self.assertEqual(invalid_checker_response.context["queue_scope"], "mine")

        admin_client = Client()
        admin_client.force_login(self.admin)
        admin_response = admin_client.get(reverse("gddb_registration_v2"))
        admin_ids = [
            item.pk for item in admin_response.context["page_obj"].object_list
        ]
        self.assertEqual(admin_response.context["queue_scope"], "all")
        self.assertIn(self.registration.pk, admin_ids)
        self.assertIn(mine.pk, admin_ids)
        invalid_admin_response = admin_client.get(
            reverse("gddb_registration_v2"),
            {"queue": "invalid"},
        )
        self.assertEqual(invalid_admin_response.context["queue_scope"], "all")

    def test_expired_claim_is_unassigned_and_no_longer_counted_as_mine(self):
        CollateralRegistration.objects.filter(pk=self.registration.pk).update(
            processing_by=self.checker_one,
            processing_expires_at=timezone.now() - timedelta(seconds=1),
        )
        client = Client()
        client.force_login(self.checker_one)

        mine_response = client.get(
            reverse("gddb_registration_v2"),
            {"queue": "mine"},
        )
        unassigned_response = client.get(
            reverse("gddb_registration_v2"),
            {"queue": "unassigned"},
        )

        mine_ids = [item.pk for item in mine_response.context["page_obj"].object_list]
        unassigned_ids = [
            item.pk for item in unassigned_response.context["page_obj"].object_list
        ]
        self.assertNotIn(self.registration.pk, mine_ids)
        self.assertEqual(mine_response.context["my_work_count"], 0)
        self.assertIn(self.registration.pk, unassigned_ids)
        self.assertEqual(unassigned_response.context["unassigned_count"], 1)
        self.registration.refresh_from_db()
        self.assertIsNone(self.registration.processing_by)
        self.assertTrue(
            CollateralRegistrationLog.objects.filter(
                registration=self.registration,
                action="case_expire",
                metadata__previous_owner_username=self.checker_one.username,
            ).exists()
        )

    def test_postmini_is_a_child_queue_of_my_cases(self):
        now = timezone.now()
        CollateralRegistration.objects.filter(pk=self.registration.pk).update(
            processing_by=self.checker_one,
            processing_expires_at=now + timedelta(hours=4),
        )
        postmini_case = CollateralRegistration.objects.create(
            contract_code="HD-MY-POSTMINI",
            gddb_status=CollateralRegistrationStatus.REGISTERED,
            postmini_updated="Chưa cập nhật",
            processing_by=self.checker_one,
            registered_by=self.checker_one,
        )
        other_checker_postmini = CollateralRegistration.objects.create(
            contract_code="HD-OTHER-POSTMINI",
            gddb_status=CollateralRegistrationStatus.REGISTERED,
            postmini_updated="Chưa cập nhật",
            processing_by=self.checker_two,
            registered_by=self.checker_two,
        )
        client = Client()
        client.force_login(self.checker_one)

        registration_response = client.get(
            reverse("gddb_registration_v2"),
            {"queue": "mine", "mine_step": "registration"},
        )
        postmini_response = client.get(
            reverse("gddb_registration_v2"),
            {"queue": "mine", "mine_step": "postmini"},
        )
        legacy_response = client.get(
            reverse("gddb_registration_v2"),
            {"queue": "postmini"},
        )

        registration_ids = [
            item.pk for item in registration_response.context["page_obj"].object_list
        ]
        postmini_ids = [
            item.pk for item in postmini_response.context["page_obj"].object_list
        ]
        self.assertEqual(registration_ids, [self.registration.pk])
        self.assertIn(postmini_case.pk, postmini_ids)
        self.assertNotIn(other_checker_postmini.pk, postmini_ids)
        self.assertEqual(postmini_response.context["queue_scope"], "mine")
        self.assertEqual(postmini_response.context["mine_step"], "postmini")
        self.assertEqual(postmini_response.context["my_pending_count"], 1)
        self.assertEqual(postmini_response.context["my_postmini_count"], 1)
        self.assertEqual(legacy_response.context["queue_scope"], "mine")
        self.assertEqual(legacy_response.context["mine_step"], "postmini")

    def test_registered_history_keeps_archived_cases_without_actions_or_counter(self):
        archived_case = CollateralRegistration.objects.create(
            contract_code="HD-MY-ARCHIVED",
            gddb_status=CollateralRegistrationStatus.REGISTERED,
            postmini_updated="Đã cập nhật",
            processing_by=self.checker_one,
            registered_by=self.checker_one,
            archived_at=timezone.now(),
        )
        other_checker_case = CollateralRegistration.objects.create(
            contract_code="HD-OTHER-ARCHIVED",
            gddb_status=CollateralRegistrationStatus.REGISTERED,
            postmini_updated="Đã cập nhật",
            processing_by=self.checker_two,
            registered_by=self.checker_two,
            archived_at=timezone.now(),
        )
        incomplete_archived_case = CollateralRegistration.objects.create(
            contract_code="HD-MY-INCOMPLETE-ARCHIVED",
            gddb_status=CollateralRegistrationStatus.REGISTERED,
            postmini_updated="Chưa cập nhật",
            processing_by=self.checker_one,
            registered_by=self.checker_one,
            archived_at=timezone.now(),
        )
        client = Client()
        client.force_login(self.checker_one)

        active_response = client.get(
            reverse("gddb_registration_v2"),
            {"queue": "mine"},
        )
        history_response = client.get(
            reverse("gddb_registration_v2"),
            {"queue": "mine", "mine_step": "registered_history"},
        )

        active_ids = [item.pk for item in active_response.context["page_obj"].object_list]
        history_items = list(history_response.context["page_obj"].object_list)
        history_ids = [item.pk for item in history_items]
        self.assertNotIn(archived_case.pk, active_ids)
        self.assertIn(archived_case.pk, history_ids)
        self.assertNotIn(other_checker_case.pk, history_ids)
        self.assertNotIn(incomplete_archived_case.pk, history_ids)
        self.assertEqual(history_response.context["mine_step"], "registered_history")
        self.assertFalse(history_items[0].can_mutate_case)
        self.assertTrue(history_items[0].can_edit_registration)
        self.assertContains(history_response, "Đã hoàn tất</a>")
        self.assertNotContains(
            history_response,
            'data-gddb-counter="mine-registered-history"',
        )

    def test_owner_can_edit_registration_of_completed_archived_case(self):
        archived_case = CollateralRegistration.objects.create(
            contract_code="HD-EDIT-COMPLETED",
            gddb_status=CollateralRegistrationStatus.REGISTERED,
            postmini_updated="Đã cập nhật",
            processing_by=self.checker_one,
            registered_by=self.checker_one,
            registered_identity=self.identity,
            archived_at=timezone.now(),
        )

        response = self._post(
            self.checker_one,
            reverse("api_gddb_update", args=[archived_case.pk]),
            {
                "gddb_status": CollateralRegistrationStatus.REGISTERED,
                "registered_identity_id": self.identity.pk,
                "reason": "Đăng ký mới",
            },
        )

        self.assertEqual(response.status_code, 200)
        archived_case.refresh_from_db()
        self.assertIsNotNone(archived_case.archived_at)
        self.assertEqual(archived_case.postmini_updated, "Đã cập nhật")

    def test_not_registered_case_is_archived_and_shown_as_completed(self):
        claim_url = reverse("api_gddb_case_claim", args=[self.registration.pk])
        self._post(self.checker_one, claim_url, {"action": "claim"})
        update_response = self._post(
            self.checker_one,
            reverse("api_gddb_update", args=[self.registration.pk]),
            {
                "gddb_status": CollateralRegistrationStatus.NOT_REGISTERED,
                "reason": "Hợp đồng hết hiệu lực",
            },
        )

        self.assertEqual(update_response.status_code, 200)
        self.assertTrue(update_response.json()["archived"])
        self.registration.refresh_from_db()
        self.assertIsNotNone(self.registration.archived_at)
        self.assertEqual(
            self.registration.gddb_status,
            CollateralRegistrationStatus.NOT_REGISTERED,
        )

        client = Client()
        client.force_login(self.checker_one)
        history_response = client.get(
            reverse("gddb_registration_v2"),
            {"queue": "mine", "mine_step": "registered_history"},
        )
        history_ids = [
            item.pk for item in history_response.context["page_obj"].object_list
        ]
        self.assertIn(self.registration.pk, history_ids)

    def test_batch_filter_supports_business_date_and_daily_slot(self):
        self.registration.delete()
        current_time = timezone.now()
        if timezone.is_aware(current_time):
            current_time = timezone.localtime(current_time)
        business_date = current_time.date()
        in_slot_batch = CollateralRegistrationImportBatch.objects.create(source_type="api")
        outside_slot_batch = CollateralRegistrationImportBatch.objects.create(source_type="api")
        CollateralRegistrationImportBatch.objects.filter(pk=in_slot_batch.pk).update(
            business_date=business_date,
            slot_number=1,
        )
        CollateralRegistrationImportBatch.objects.filter(pk=outside_slot_batch.pk).update(
            business_date=business_date,
            slot_number=2,
        )
        in_hour_case = CollateralRegistration.objects.create(
            contract_code="HD-HOUR-IN",
            import_batch=in_slot_batch,
        )
        outside_hour_case = CollateralRegistration.objects.create(
            contract_code="HD-HOUR-OUT",
            import_batch=outside_slot_batch,
        )

        client = Client()
        client.force_login(self.checker_one)
        response = client.get(reverse("gddb_registration_v2"), {
            "queue": "all",
            "filter_type": "batch",
            "batch_date": business_date.isoformat(),
            "batch_filter_mode": "time",
            "batch_slot": "1",
        })

        self.assertEqual(response.status_code, 200)
        listed_ids = [item.pk for item in response.context["page_obj"].object_list]
        self.assertEqual(listed_ids, [in_hour_case.pk])
        self.assertEqual(response.context["filters"]["batch_slot"], "1")

    def test_batch_slot_boundaries_do_not_overlap(self):
        classify = CollateralRegistrationImportBatch.classify_run_time
        run_date = timezone.now().date()

        self.assertEqual(classify(datetime.combine(run_date, datetime.min.time()).replace(hour=9)), (run_date, 1))
        self.assertEqual(classify(datetime.combine(run_date, datetime.min.time()).replace(hour=13)), (run_date, 2))
        self.assertEqual(classify(datetime.combine(run_date, datetime.min.time()).replace(hour=16)), (run_date, 3))
        self.assertEqual(classify(datetime.combine(run_date, datetime.min.time()).replace(hour=19)), (run_date, 4))
        self.assertEqual(
            classify(datetime.combine(run_date, datetime.min.time()).replace(hour=8, minute=59)),
            (run_date - timedelta(days=1), 4),
        )

    def test_date_filter_does_not_apply_batch_selection(self):
        current_time = timezone.now()
        if timezone.is_aware(current_time):
            current_time = timezone.localtime(current_time)
        current_date = current_time.date().isoformat()
        client = Client()
        client.force_login(self.checker_one)

        response = client.get(reverse("gddb_registration_v2"), {
            "queue": "all",
            "filter_type": "date",
            "date_from": current_date,
            "date_to": current_date,
            "batch_date": current_date,
            "batch_slot": "1",
        })

        self.assertEqual(response.status_code, 200)
        listed_ids = [item.pk for item in response.context["page_obj"].object_list]
        self.assertIn(self.registration.pk, listed_ids)
        self.assertEqual(response.context["filters"]["batch_slot"], "")
        self.assertEqual(response.context["filters"]["batch_date"], "")

    def test_all_queue_keeps_unarchived_backlog_older_than_seven_days(self):
        current_time = timezone.now()
        if timezone.is_aware(current_time):
            current_time = timezone.localtime(current_time)
        boundary_time = datetime.combine(current_time.date() - timedelta(days=30), datetime.min.time())
        if timezone.is_aware(timezone.now()):
            boundary_time = timezone.make_aware(boundary_time, timezone.get_current_timezone())
        CollateralRegistration.objects.filter(pk=self.registration.pk).update(
            created_at=boundary_time
        )
        client = Client()
        client.force_login(self.checker_one)

        response = client.get(reverse("gddb_registration_v2"), {"queue": "all"})

        self.assertEqual(response.status_code, 200)
        listed_ids = [item.pk for item in response.context["page_obj"].object_list]
        self.assertIn(self.registration.pk, listed_ids)

    def test_batch_filter_without_batch_date_does_not_hide_default_queue(self):
        client = Client()
        client.force_login(self.checker_one)

        response = client.get(reverse("gddb_registration_v2"), {
            "queue": "all",
            "filter_type": "batch",
            "batch_slot": "1",
        })

        self.assertEqual(response.status_code, 200)
        listed_ids = [item.pk for item in response.context["page_obj"].object_list]
        self.assertIn(self.registration.pk, listed_ids)
        self.assertEqual(response.context["filters"]["batch_slot"], "")

    def test_summary_counts_only_unfinished_cases(self):
        CollateralRegistration.objects.create(
            contract_code="HD-SUMMARY-POSMINI",
            gddb_status=CollateralRegistrationStatus.REGISTERED,
            postmini_updated="Chưa cập nhật",
        )
        CollateralRegistration.objects.create(
            contract_code="HD-SUMMARY-NOT-REGISTERED",
            gddb_status=CollateralRegistrationStatus.NOT_REGISTERED,
        )
        client = Client()
        client.force_login(self.checker_one)

        response = client.get(reverse("gddb_registration_v2"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_count"], 2)
        self.assertEqual(response.context["pending_count"], 1)
        self.assertEqual(response.context["processing_posmini_count"], 1)
