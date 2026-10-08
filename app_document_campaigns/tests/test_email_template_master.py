import json
from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from app_document_campaigns.models import (
    Campaign,
    CampaignAreaEmailConfig,
    CampaignEmailConfig,
    CampaignType,
    EmailTemplateMaster,
    ShopResponseOption,
)
from app_documents.models import UserProfile


class EmailTemplateMasterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        admin = Group.objects.create(name="admin")
        cls.user = User.objects.create_user("template-admin", password="test")
        cls.user.groups.add(admin)
        UserProfile.objects.create(user=cls.user, department="Vận hành")
        cls.campaign_type = CampaignType.objects.create(
            code="EMAIL-TEMPLATE-TEST", code_prefix="ETT", name="Email template test",
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_admin_creates_named_template_and_sends_parameterized_test(self):
        page = self.client.get(reverse("master_data_email_templates"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Template email")
        self.assertEqual(self.client.get(reverse("master_data_response_guidance")).status_code, 200)
        response = self.client.post(reverse("master_data_email_templates"), {
            "name": "PGD tùy chỉnh",
            "email_type": EmailTemplateMaster.EmailType.PGD_RESPONSE,
            "subject_template": "{{report_month}} · {{shop_name}}",
            "body_template": "Kính gửi {{shop_name}}\n{{document_error_count}} dòng lỗi\n{{response_url}}",
            "cc_template": "{{shop_manager_email}}, audit@example.com",
            "bcc_template": "risk@example.com",
            "is_active": "on",
        })
        self.assertEqual(response.status_code, 302)
        template = EmailTemplateMaster.objects.get(name="PGD tùy chỉnh")
        editor = self.client.get(f"{reverse('master_data_email_templates')}?edit={template.pk}")
        self.assertEqual(editor.status_code, 200)
        self.assertContains(editor, "data-rich-email-editor")
        self.assertContains(editor, "Gửi thử bằng dữ liệu mẫu")
        self.assertContains(editor, 'data-met-variable="document_error_count"')
        self.assertContains(editor, 'data-met-variable="shop_manager_email"')
        self.assertEqual(template.cc_template, "{{shop_manager_email}}, audit@example.com")
        self.assertNotContains(editor, "Tham số test (JSON)")
        parameters = {"report_month": "10/2026", "shop_name": "PGD Test", "document_error_count": 3, "response_url": "https://example.invalid/respond/", "shop_manager_email": "manager@example.com"}
        with patch("app_document_campaigns.services.microsoft_graph_email.send_rendered_email") as sender:
            sent = self.client.post(
                reverse("master_data_email_template_test", args=[template.pk]),
                {"tester_email": "tester@example.com", "parameters": json.dumps(parameters)},
            )
        self.assertEqual(sent.status_code, 302)
        rendered = sender.call_args.args[0]
        self.assertEqual(rendered.to, ["tester@example.com"])
        self.assertEqual(rendered.cc, [])
        self.assertIn("10/2026 · PGD Test", rendered.subject)
        self.assertIn("https://example.invalid/respond/", rendered.body)
        self.assertIn("3 dòng lỗi", rendered.body)
        with patch("app_document_campaigns.services.microsoft_graph_email.send_rendered_email") as sender:
            sent = self.client.post(
                reverse("master_data_email_template_test", args=[template.pk]),
                {"tester_email": "default-tester@example.com"},
            )
        self.assertEqual(sent.status_code, 302)
        self.assertEqual(sender.call_args.args[0].to, ["default-tester@example.com"])
        self.assertIn("PGD mẫu", sender.call_args.args[0].body)
        self.assertIn("12 dòng lỗi", sender.call_args.args[0].body)

    def test_campaign_settings_maps_each_step_and_snapshots_template_content(self):
        pgd = EmailTemplateMaster.objects.create(
            name="PGD mapping", email_type=EmailTemplateMaster.EmailType.PGD_RESPONSE,
            subject_template="PGD {{shop_name}}", body_template="{{response_url}}", cc_template="{{shop_manager_email}}", bcc_template="audit@example.com", created_by=self.user,
        )
        monitoring = EmailTemplateMaster.objects.create(
            name="Monitor mapping", email_type=EmailTemplateMaster.EmailType.AREA_MONITORING,
            subject_template="Monitor {{area_manager_name}}", body_template="{{manager_url}}", cc_template="audit@example.com", created_by=self.user,
        )
        confirmation = EmailTemplateMaster.objects.create(
            name="Confirm mapping", email_type=EmailTemplateMaster.EmailType.AREA_CONFIRMATION,
            subject_template="Confirm {{area_manager_name}}", body_template="{{manager_url}}", bcc_template="risk@example.com", created_by=self.user,
        )
        now = timezone.now()
        campaign = Campaign.objects.create(
            code="ETT-202610", name="Kỳ mapping", campaign_type=self.campaign_type,
            report_month=date(2026, 10, 1), response_deadline=now + timedelta(days=5),
            area_response_deadline=now + timedelta(days=8), link_expires_at=now + timedelta(days=36),
            created_by=self.user,
        )
        payload = {
                "name": campaign.name,
                "response_deadline": (now + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M"),
                "area_response_deadline": (now + timedelta(days=8)).strftime("%Y-%m-%dT%H:%M"),
                "pgd_email_template": pgd.pk,
                "area_monitoring_email_template": monitoring.pk,
                "area_confirmation_email_template": confirmation.pk,
                "shop_instructions": "",
                "area_manager_instructions": "",
                "response_options": list(
                    ShopResponseOption.objects.filter(is_active=True).values_list("pk", flat=True)
                ),
            }
        from app_document_campaigns.forms import CampaignSettingsForm
        validation_form = CampaignSettingsForm(payload, instance=campaign)
        self.assertTrue(validation_form.is_valid(), validation_form.errors.as_json())
        response = self.client.post(
            reverse("document_campaigns:update_campaign_settings", args=[campaign.pk]), payload,
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("settings=1", response.url)
        campaign.refresh_from_db()
        self.assertEqual(campaign.pgd_email_template, pgd)
        self.assertEqual(campaign.area_monitoring_email_template, monitoring)
        self.assertEqual(campaign.area_confirmation_email_template, confirmation)
        pgd_config = CampaignEmailConfig.objects.get(campaign=campaign)
        area_config = CampaignAreaEmailConfig.objects.get(campaign=campaign)
        self.assertEqual(pgd_config.subject_template, pgd.subject_template)
        self.assertEqual(pgd_config.cc_template, pgd.cc_template)
        self.assertEqual(pgd_config.bcc_template, pgd.bcc_template)
        self.assertEqual(area_config.monitoring_body_template, monitoring.body_template)
        self.assertEqual(area_config.monitoring_cc_template, monitoring.cc_template)
        self.assertEqual(area_config.confirmation_body_template, confirmation.body_template)
        self.assertEqual(area_config.confirmation_bcc_template, confirmation.bcc_template)

        # Later edits to a master template do not rewrite a campaign snapshot
        # unless that campaign explicitly changes its selected template.
        original_subject = pgd_config.subject_template
        pgd.subject_template = "Nội dung master đã đổi {{shop_name}}"
        pgd.save(update_fields=["subject_template", "updated_at"])
        payload["name"] = "Kỳ mapping đã đổi tên"
        response = self.client.post(
            reverse("document_campaigns:update_campaign_settings", args=[campaign.pk]), payload,
        )
        self.assertEqual(response.status_code, 302)
        pgd_config.refresh_from_db()
        self.assertEqual(pgd_config.subject_template, original_subject)
        detail = self.client.get(reverse("document_campaigns:campaign_detail", args=[campaign.pk]))
        self.assertContains(detail, "Nội dung kỳ đang khác template Master Data: PGD")

        payload["reapply_email_templates"] = "on"
        response = self.client.post(
            reverse("document_campaigns:update_campaign_settings", args=[campaign.pk]), payload,
        )
        self.assertEqual(response.status_code, 302)
        pgd_config.refresh_from_db()
        self.assertEqual(pgd_config.subject_template, pgd.subject_template)
