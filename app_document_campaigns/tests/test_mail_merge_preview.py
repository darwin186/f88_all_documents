from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from app_document_campaigns.models import Campaign


class MailMergePreviewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user('mail-merge-designer', password='test')
        cls.admin.groups.add(Group.objects.create(name='admin'))
        cls.checker = User.objects.create_user('mail-merge-checker', password='test')
        cls.checker.groups.add(Group.objects.create(name='checker'))

    def test_preview_has_its_own_workflow_and_does_not_create_campaigns(self):
        self.client.force_login(self.admin)
        before = Campaign.objects.count()
        response = self.client.get(reverse('document_campaigns:mail_merge_preview'))
        self.assertEqual(response.status_code, 200)
        for label in ['Cấu hình', 'Tải dữ liệu', 'Thiết kế bảng', 'Mapping PGD / email',
                      'Phát hành &amp; theo dõi', 'Chốt &amp; báo cáo']:
            self.assertContains(response, label)
        self.assertContains(response, 'data-mail-merge-preview')
        self.assertContains(response, 'Bản xem thử · Dữ liệu mẫu')
        self.assertNotContains(response, 'data-workflow-step=')
        self.assertEqual(Campaign.objects.count(), before)
        self.assertEqual(self.client.post(reverse('document_campaigns:mail_merge_preview'), {'name': 'test'}).status_code, 405)
        self.assertEqual(Campaign.objects.count(), before)

    def test_campaign_list_temporarily_hides_mail_merge_and_keeps_one_create_link(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('document_campaigns:campaign_list'))
        self.assertNotContains(response, reverse('document_campaigns:mail_merge_preview'))
        self.assertNotContains(response, 'Mail Merge')
        self.assertContains(response, f'href="{reverse("document_campaigns:campaign_create")}"', count=1)
        self.assertContains(response, 'Quản lý chiến dịch')
        self.assertNotContains(response, 'Danh sách kỳ')
        self.assertNotContains(response, '<h1')
        self.assertNotContains(response, 'Quản lý các kỳ Book lỗi và chiến dịch thu thập phản hồi từ PGD.')
        self.assertNotContains(response, 'Tạo chiến dịch mới')
        self.assertNotContains(response, 'data-workflow-step=')

    def test_prototype_requires_admin(self):
        url = reverse('document_campaigns:mail_merge_preview')
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.checker)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_create_asks_for_workflow_type_before_book_form(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('document_campaigns:campaign_create'))
        self.assertTemplateUsed(response, 'app_document_campaigns/campaign_kind.html')
        self.assertContains(response, 'name="workflow_type"', count=2)
        self.assertContains(response, 'value="hard_copy"')
        self.assertContains(response, 'value="mail_merge"')
        self.assertNotContains(response, 'data-workflow-step=')
        self.assertNotRegex(response.content.decode(), r'<input[^>]*\bchecked\b')

    def test_hard_copy_selection_opens_existing_book_form(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('document_campaigns:campaign_create'), {'workflow_type': 'hard_copy'})
        self.assertTemplateUsed(response, 'app_document_campaigns/campaign_form.html')
        self.assertContains(response, 'name="workflow_type" value="hard_copy"')
        self.assertContains(response, 'data-workflow-step=')
        self.assertContains(response, 'Chứng từ bản cứng')

    def test_mail_merge_selection_starts_its_own_configuration(self):
        self.client.force_login(self.admin)
        before = Campaign.objects.count()
        response = self.client.get(reverse('document_campaigns:campaign_create'), {'workflow_type': 'mail_merge'})
        self.assertRedirects(response, reverse('document_campaigns:mail_merge_preview') + '?step=1&mode=create')
        response = self.client.get(response.url)
        self.assertTrue(response.context['creating'])
        self.assertContains(response, 'Chiến dịch Mail Merge mới')
        self.assertNotContains(response, 'data-workflow-step=')
        self.assertEqual(Campaign.objects.count(), before)
        response = self.client.post(reverse('document_campaigns:campaign_create'), {'workflow_type': 'mail_merge', 'name': 'test'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Campaign.objects.count(), before)

    def test_unknown_workflow_type_is_rejected(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('document_campaigns:campaign_create'), {'workflow_type': 'other'}).status_code, 400)

    def test_post_requires_explicit_workflow_choice(self):
        self.client.force_login(self.admin)
        before = Campaign.objects.count()
        response = self.client.post(reverse('document_campaigns:campaign_create'), {'name': 'Untyped'})
        self.assertContains(response, 'Vui lòng chọn loại chiến dịch', status_code=400)
        self.assertEqual(Campaign.objects.count(), before)
