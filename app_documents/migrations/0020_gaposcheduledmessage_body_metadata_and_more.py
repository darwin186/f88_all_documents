from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app_documents", "0019_user_presence_hourly_and_daily_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="gaposcheduledmessage",
            name="body_metadata",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="gaposcheduledmessage",
            name="body_type",
            field=models.CharField(
                choices=[
                    ("text", "Text"),
                    ("quick_replies", "Quick replies"),
                    ("carousel", "Carousel"),
                    ("dynamic", "Dynamic"),
                ],
                default="text",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="gaposcheduledmessage",
            name="collab_id",
            field=models.CharField(blank=True, default="", max_length=50),
        ),
        migrations.AddField(
            model_name="gaposcheduledmessage",
            name="thread_id",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="gaposcheduledmessage",
            name="receiver_id",
            field=models.CharField(blank=True, default="", max_length=50),
        ),
    ]
