import json
from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    CollateralRegistration,
    CollateralRegistrationExternalIdentity,
    CollateralRegistrationImportBatch,
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
        })
        self.assertEqual(owner_edit_response.status_code, 200)

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

    def test_bulk_claim_rejects_mixed_sources_or_batches(self):
        first_batch = CollateralRegistrationImportBatch.objects.create(source_type="api")
        second_batch = CollateralRegistrationImportBatch.objects.create(source_type="api")
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

    def test_default_list_prioritizes_held_cases_then_old_batches(self):
        self.registration.delete()
        old_batch = CollateralRegistrationImportBatch.objects.create(source_type="api")
        new_batch = CollateralRegistrationImportBatch.objects.create(source_type="api")
        held_batch = CollateralRegistrationImportBatch.objects.create(source_type="api")
        now = timezone.now()
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
        held_case = CollateralRegistration.objects.create(
            contract_code="HD-ORDER-HELD",
            import_batch=held_batch,
            processing_by=self.checker_one,
            processing_started_at=now,
            processing_expires_at=now + timedelta(minutes=10),
        )

        client = Client()
        client.force_login(self.checker_one)
        response = client.get(reverse("gddb_registration_v2"))

        self.assertEqual(response.status_code, 200)
        listed_ids = [item.pk for item in response.context["page_obj"].object_list]
        self.assertEqual(listed_ids, [held_case.pk, old_case.pk, new_case.pk])
