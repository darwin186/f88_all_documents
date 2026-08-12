from django.test import TestCase

from app_documents.gddb import import_collateral_registrations
from app_documents.models import CollateralRegistration


class CollateralRegistrationContractDedupeTests(TestCase):
    def test_dedupe_key_uses_contract_code_only(self):
        first_key = CollateralRegistration.build_dedupe_key(
            " HD 001 ", "30A-111", "CHASSIS-1", "ENGINE-1"
        )
        second_key = CollateralRegistration.build_dedupe_key(
            "hd001", "51A-222", "CHASSIS-2", "ENGINE-2"
        )

        self.assertEqual(first_key, second_key)

    def test_import_updates_same_contract_instead_of_creating_second_row(self):
        batch = import_collateral_registrations([
            {
                "contract_code": "HD001",
                "license_plate": "30A-111",
                "chassis_number": "CHASSIS-1",
                "engine_number": "ENGINE-1",
            },
            {
                "contract_code": " hd 001 ",
                "license_plate": "51A-222",
                "chassis_number": "CHASSIS-2",
                "engine_number": "ENGINE-2",
            },
        ])

        self.assertEqual(CollateralRegistration.objects.count(), 1)
        self.assertEqual(batch.created_rows, 1)
        self.assertEqual(batch.updated_rows, 1)
        registration = CollateralRegistration.objects.get()
        self.assertEqual(registration.license_plate, "51A-222")
        self.assertEqual(registration.chassis_number, "CHASSIS-2")
        self.assertEqual(registration.engine_number, "ENGINE-2")
