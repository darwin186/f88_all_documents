from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('app_documents', '0014_borrow_request_reference_contact_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserPresenceDaily',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('work_date', models.DateField()),
                ('last_seen_at', models.DateTimeField(blank=True, null=True)),
                ('total_active_seconds', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(db_column='user_id', on_delete=django.db.models.deletion.CASCADE, related_name='presence_daily', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'f_UserPresenceDaily',
                'ordering': ['-work_date', '-last_seen_at'],
                'unique_together': {('user', 'work_date')},
            },
        ),
    ]
