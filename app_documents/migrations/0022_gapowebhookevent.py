from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app_documents", "0021_userprofile_default_receive_location"),
    ]

    operations = [
        migrations.CreateModel(
            name="GapoWebhookEvent",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("event_type", models.CharField(blank=True, default="", max_length=100)),
                ("bot_id", models.CharField(blank=True, default="", max_length=50)),
                ("message_id", models.CharField(blank=True, default="", max_length=100)),
                ("thread_id", models.CharField(blank=True, default="", max_length=50)),
                ("collab_id", models.CharField(blank=True, default="", max_length=50)),
                ("sender_id", models.CharField(blank=True, default="", max_length=50)),
                ("message_text", models.TextField(blank=True, default="")),
                ("http_method", models.CharField(blank=True, default="POST", max_length=10)),
                ("request_path", models.CharField(blank=True, default="", max_length=255)),
                ("remote_addr", models.CharField(blank=True, default="", max_length=64)),
                ("headers", models.JSONField(blank=True, default=dict)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("raw_body", models.TextField(blank=True, default="")),
                ("is_json_valid", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "f_GapoWebhookEvent",
                "ordering": ["-created_at"],
            },
        ),
    ]
