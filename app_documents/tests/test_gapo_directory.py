from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.template.loader import render_to_string
from django.test import Client, RequestFactory, TestCase
from django.urls import resolve, reverse

from app_admindocuments.models import AdmParcelRecipientImportBatch


class GapoDirectoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superadmin = User.objects.create_superuser('gapo-super', 'gapo@example.com', 'test')
        cls.admin = User.objects.create_user('gapo-admin')
        cls.admin.groups.add(Group.objects.get_or_create(name='admin')[0])
        cls.staff = User.objects.create_user('gapo-staff', is_staff=True)
        cls.staff.groups.add(Group.objects.get_or_create(name='administrative staff')[0])
        cls.employee = User.objects.create_user('gapo-employee')

    def test_requires_login_and_superuser_for_read_and_all_write_actions(self):
        url = reverse('master_data_gapo_directory')
        self.assertEqual(self.client.get(url).status_code, 302)
        self.assertEqual(self.client.post(url, {'action': 'upload'}).status_code, 302)
        for user in [self.admin, self.staff, self.employee]:
            self.client.force_login(user)
            with self.subTest(user=user.username):
                self.assertEqual(self.client.get(url).status_code, 403)
                for action in ['upload', 'activate', 'reimport', 'apply_shop_managers']:
                    self.assertEqual(self.client.post(url, {'action': action, 'batch_id': 1}).status_code, 403)
                self.assertEqual(self.client.get(reverse('admindocuments:parcel_recipient_directory')).status_code, 403)
        self.assertEqual(AdmParcelRecipientImportBatch.objects.count(), 0)

    def test_superuser_opens_directory_with_master_data_navigation(self):
        self.client.force_login(self.superadmin)
        response = self.client.get(reverse('master_data_gapo_directory'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'app_documents/master_data_gapo_directory.html')
        self.assertContains(response, 'aria-current="page">Danh bạ Gapo')
        self.assertContains(response, f'href="{reverse("master_data")}"')
        self.assertContains(response, 'name="action" value="upload"')
        self.assertNotContains(response, 'aria-label="Hành chính"')
        self.assertNotContains(response, '>Tổng quan<')

    def test_navigation_only_exposes_directory_to_superusers(self):
        for user in [self.superadmin, self.admin, self.staff, self.employee]:
            request = RequestFactory().get(reverse('master_data'))
            request.user = user
            request.resolver_match = resolve(request.path)
            html = render_to_string('app_documents/components/top_nav_v2.html', {
                'request': request, 'master_data_nav': True,
                'is_super_admin': user.is_superuser,
                'is_admin': user == self.admin,
            })
            self.assertEqual('Danh bạ Gapo' in html, user.is_superuser)

    def test_legacy_link_preserves_search_and_redirects_to_master_data(self):
        self.client.force_login(self.superadmin)
        response = self.client.get(reverse('admindocuments:parcel_recipient_directory'), {'q': 'A&B + Gapo'})
        self.assertRedirects(response, reverse('master_data_gapo_directory') + '?q=A%26B+%2B+Gapo', fetch_redirect_response=False)

    def test_activate_and_reimport_redirect_to_master_data(self):
        self.client.force_login(self.superadmin)
        batch = AdmParcelRecipientImportBatch.objects.create(original_name='gapo.xlsx', imported_by=self.superadmin)
        response = self.client.post(reverse('master_data_gapo_directory'), {'action': 'activate', 'batch_id': batch.pk})
        self.assertRedirects(response, reverse('master_data_gapo_directory'), fetch_redirect_response=False)
        batch.refresh_from_db()
        self.assertTrue(batch.is_current)
        with patch('app_admindocuments.views._import_parcel_recipient_batch') as importer:
            response = self.client.post(reverse('master_data_gapo_directory'), {'action': 'reimport', 'batch_id': batch.pk})
        self.assertRedirects(response, reverse('master_data_gapo_directory'), fetch_redirect_response=False)
        importer.assert_called_once_with(batch)

    def test_post_still_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.superadmin)
        url = reverse('master_data_gapo_directory')
        self.assertEqual(client.get(url).status_code, 200)
        self.assertEqual(client.post(url, {'action': 'activate', 'batch_id': 1}).status_code, 403)
