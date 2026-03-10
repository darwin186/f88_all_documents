from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app_documents", "0017_userprofile_personal_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="UiScreen",
            fields=[
                ("screen_id", models.AutoField(primary_key=True, serialize=False)),
                ("screen_key", models.CharField(max_length=100, unique=True)),
                ("screen_name", models.CharField(max_length=255)),
                ("screen_path", models.CharField(blank=True, max_length=255, null=True)),
                ("screen_group", models.CharField(blank=True, max_length=100, null=True)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "db_table": "d_UiScreen",
                "ordering": ["screen_group", "screen_name"],
            },
        ),
        migrations.CreateModel(
            name="UiPermission",
            fields=[
                ("permission_id", models.AutoField(primary_key=True, serialize=False)),
                ("role_code", models.CharField(max_length=50)),
                ("can_view", models.BooleanField(default=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("screen", models.ForeignKey(db_column="screen_id", on_delete=django.db.models.deletion.CASCADE, to="app_documents.uiscreen")),
                ("updated_by", models.ForeignKey(blank=True, db_column="updated_by", null=True, on_delete=django.db.models.deletion.SET_NULL, to="auth.user")),
            ],
            options={
                "db_table": "f_UiPermission",
                "unique_together": {("screen", "role_code")},
            },
        ),
    ]
