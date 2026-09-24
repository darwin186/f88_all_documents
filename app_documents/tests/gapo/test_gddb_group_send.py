import json
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from app_documents.models import GapoScheduledMessage


@override_settings(GDDB_GAPO_COLLAB_ID="gddb-collab-test")
class GddbGapoGroupSendTests(TestCase):
    def setUp(self):
        admin_group = Group.objects.create(name="admin")
        self.user = User.objects.create_user(username="gddb_gapo_admin", password="test")
        self.user.groups.add(admin_group)
        self.client = Client()
        self.client.force_login(self.user)

    @patch("app_documents.views.send_gapo_scheduled_message.apply_async")
    def test_admin_can_queue_group_message(self, mocked_apply_async):
        response = self.client.post(
            reverse("api_gddb_gapo_group_send"),
            data=json.dumps({"message": "Thông báo nhóm GDĐB"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 202)
        schedule = GapoScheduledMessage.objects.get()
        self.assertEqual(schedule.collab_id, "gddb-collab-test")
        self.assertEqual(schedule.message, "Thông báo nhóm GDĐB")
        mocked_apply_async.assert_called_once_with(args=[schedule.pk])

    @override_settings(GDDB_GAPO_COLLAB_ID="")
    def test_missing_group_configuration_fails_closed(self):
        response = self.client.post(
            reverse("api_gddb_gapo_group_send"),
            data=json.dumps({"message": "Thông báo"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(GapoScheduledMessage.objects.count(), 0)
