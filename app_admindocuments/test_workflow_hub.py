from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from .models import AdmCompany


class WorkflowHubTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('workflow-admin', 'admin@example.com', 'test')
        cls.employee = User.objects.create_user('workflow-employee')
        cls.staff = User.objects.create_user('workflow-staff')
        cls.staff.groups.add(Group.objects.get_or_create(name='administrative staff')[0])

    def test_anonymous_user_must_log_in(self):
        response = self.client.get(reverse('admindocuments:workflow_hub'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('next=', response.url)

    def test_admin_and_administrative_staff_can_open_all_four_flows(self):
        for user in (self.admin, self.staff):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(reverse('admindocuments:workflow_hub'))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(response.context['workflows']), 4)
                for workflow in response.context['workflows']:
                    self.assertTrue(workflow['allowed'])
                    self.assertContains(response, f'href="{workflow["create_url"]}"')
                    self.assertContains(response, f'href="{workflow["list_url"]}"')
                self.assertContains(response, f'href="{reverse("admindocuments:admindocuments_counters")}?tab=admin"')
                self.assertContains(response, 'Số hiệu văn bản hành chính')
                self.assertContains(response, f'href="{reverse("admindocuments:admindocuments_counters")}?tab=paper"')
                self.assertContains(response, 'Số hiệu giấy tờ hành chính')
                for tab in ['admin', 'paper']:
                    counters = self.client.get(reverse('admindocuments:admindocuments_counters'), {'tab': tab})
                    self.assertEqual(counters.status_code, 200)
                    self.assertEqual(counters.context['active_tab'], tab)

    def test_employee_only_has_actions_for_incoming_documents_and_parcels(self):
        self.client.force_login(self.employee)
        response = self.client.get(reverse('admindocuments:workflow_hub'))
        allowed = [workflow['key'] for workflow in response.context['workflows'] if workflow['allowed']]
        self.assertEqual(allowed, ['incoming', 'parcel'])
        self.assertNotContains(response, f'href="{reverse("admindocuments:admindocuments_list")}?create=1"')
        self.assertNotContains(response, f'href="{reverse("admindocuments:paper_document_list")}?create=1"')
        self.assertNotContains(response, 'adm-workflow-counters')
        self.assertEqual(self.client.get(reverse('admindocuments:admindocuments_list')).status_code, 403)
        self.assertEqual(self.client.get(reverse('admindocuments:paper_document_list')).status_code, 403)

    def test_incoming_creation_from_hub_can_select_receiving_company(self):
        company = AdmCompany.objects.create(code='HUB', name='Công ty nhận thử')
        self.client.force_login(self.employee)
        response = self.client.get(reverse('admindocuments:incoming_document_list'), {'create': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<select id="incomingReceivingCompanyCode" name="receiving_company" required')
        self.assertContains(response, f'<option value="{company.code}"')
        self.assertContains(response, 'openIncomingDispatchModal(currentCode, currentLabel)')

    def test_parcel_list_opens_completed_receipts_with_existing_permissions(self):
        completed_url = reverse('admindocuments:parcel_receipt_completed_list')
        for user in [self.admin, self.staff, self.employee]:
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(reverse('admindocuments:workflow_hub'))
                parcel = next(flow for flow in response.context['workflows'] if flow['key'] == 'parcel')
                self.assertEqual(parcel['list_url'], completed_url)
                self.assertEqual(parcel['list_allowed'], user != self.employee)
                self.assertContains(response, f'href="{parcel["create_url"]}"')
                if user == self.employee:
                    self.assertNotContains(response, f'href="{completed_url}"')
                    self.assertEqual(self.client.get(completed_url).status_code, 403)
                else:
                    self.assertContains(response, f'href="{completed_url}"')
                    self.assertEqual(self.client.get(completed_url).status_code, 200)
