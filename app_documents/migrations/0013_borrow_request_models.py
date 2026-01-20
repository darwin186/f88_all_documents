from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app_documents", "0012_checkingtransactionstatus_is_request_additional"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BorrowRequest",
            fields=[
                ("request_id", models.AutoField(primary_key=True, serialize=False)),
                ("needed_date", models.DateField()),
                ("appointment_date", models.DateField(blank=True, null=True)),
                ("ticket_code", models.CharField(blank=True, max_length=100, null=True)),
                ("contact_email", models.EmailField(blank=True, max_length=254, null=True)),
                ("note", models.TextField(blank=True, null=True)),
                ("status", models.CharField(choices=[("draft", "Nháp"), ("pending", "Chờ xử lý"), ("assigned", "Đã gán chứng từ"), ("handed_over", "Đã bàn giao"), ("partially_returned", "Trả một phần"), ("returned", "Đã trả"), ("cancelled", "Hủy"), ("rejected", "Từ chối")], default="pending", max_length=30)),
                ("source_system", models.CharField(blank=True, max_length=50, null=True)),
                ("external_ref", models.CharField(blank=True, max_length=100, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("borrower", models.ForeignKey(db_column="borrower", on_delete=django.db.models.deletion.CASCADE, related_name="borrow_requests", to="app_documents.shop")),
                ("created_by", models.ForeignKey(blank=True, db_column="created_by", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="borrow_request_created", to=settings.AUTH_USER_MODEL)),
                ("requester", models.ForeignKey(blank=True, db_column="requester", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="borrow_requesters", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, db_column="updated_by", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="borrow_request_updated", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "f_BorrowRequest",
            },
        ),
        migrations.CreateModel(
            name="BorrowRequestItem",
            fields=[
                ("item_id", models.AutoField(primary_key=True, serialize=False)),
                ("appointment_date", models.DateField(blank=True, null=True)),
                ("status", models.CharField(choices=[("pending", "Chờ gán"), ("assigned", "Đã gán"), ("handed_over", "Đã bàn giao"), ("returned", "Đã trả"), ("lost", "Báo mất"), ("cancelled", "Hủy")], default="pending", max_length=30)),
                ("note", models.TextField(blank=True, null=True)),
                ("handed_over_date", models.DateTimeField(blank=True, null=True)),
                ("return_date", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("borrow_request", models.ForeignKey(db_column="request_id", on_delete=django.db.models.deletion.CASCADE, related_name="items", to="app_documents.borrowrequest")),
                ("created_by", models.ForeignKey(blank=True, db_column="created_by", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="borrow_request_item_created", to=settings.AUTH_USER_MODEL)),
                ("documents_id", models.ForeignKey(blank=True, db_column="documents_id", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="borrow_request_items", to="app_documents.documentsdetail")),
                ("legacy_borrowing", models.ForeignKey(blank=True, db_column="borrow_id", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="request_items", to="app_documents.borrowingdocument")),
                ("updated_by", models.ForeignKey(blank=True, db_column="updated_by", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="borrow_request_item_updated", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "f_BorrowRequestItem",
            },
        ),
        migrations.CreateModel(
            name="BorrowRequestLog",
            fields=[
                ("log_id", models.AutoField(primary_key=True, serialize=False)),
                ("action", models.CharField(max_length=50)),
                ("from_status", models.CharField(blank=True, max_length=30, null=True)),
                ("to_status", models.CharField(blank=True, max_length=30, null=True)),
                ("note", models.TextField(blank=True, null=True)),
                ("meta", models.JSONField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("borrow_request", models.ForeignKey(db_column="request_id", on_delete=django.db.models.deletion.CASCADE, related_name="logs", to="app_documents.borrowrequest")),
                ("created_by", models.ForeignKey(blank=True, db_column="created_by", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="borrow_request_logs", to=settings.AUTH_USER_MODEL)),
                ("item", models.ForeignKey(blank=True, db_column="item_id", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="logs", to="app_documents.borrowrequestitem")),
            ],
            options={
                "db_table": "f_BorrowRequestLog",
            },
        ),
    ]
