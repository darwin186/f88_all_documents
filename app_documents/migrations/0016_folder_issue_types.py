from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('app_documents', '0015_user_presence_daily'),
    ]

    operations = [
        migrations.CreateModel(
            name='FolderIssueType',
            fields=[
                ('issue_type_id', models.AutoField(primary_key=True, serialize=False)),
                ('issue_type_name', models.CharField(max_length=255, unique=True)),
                ('is_active', models.BooleanField(default=True)),
                ('is_no_issue', models.BooleanField(default=False)),
                ('badge_color', models.CharField(blank=True, max_length=20, null=True)),
                ('sort_order', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, db_column='created_by', null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, db_column='updated_by', null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'd_FolderIssueType',
                'ordering': ['sort_order', 'issue_type_name'],
            },
        ),
        migrations.CreateModel(
            name='FolderIssue',
            fields=[
                ('issue_id', models.AutoField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, db_column='created_by', null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('folder', models.ForeignKey(db_column='folder_id', on_delete=django.db.models.deletion.CASCADE, to='app_documents.folder')),
                ('issue_type', models.ForeignKey(db_column='issue_type_id', on_delete=django.db.models.deletion.CASCADE, to='app_documents.folderissuetype')),
            ],
            options={
                'db_table': 'f_FolderIssue',
                'unique_together': {('folder', 'issue_type')},
            },
        ),
    ]
