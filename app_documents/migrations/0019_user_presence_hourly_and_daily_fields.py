from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('app_documents', '0018_ui_permissions'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='userpresencedaily',
            name='first_seen_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='userpresencedaily',
            name='total_active_minutes',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.CreateModel(
            name='UserPresenceHourly',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('work_date', models.DateField()),
                ('hour', models.PositiveSmallIntegerField()),
                ('active_seconds', models.PositiveIntegerField(default=0)),
                ('first_seen_at', models.DateTimeField(blank=True, null=True)),
                ('last_seen_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(db_column='user_id', on_delete=django.db.models.deletion.CASCADE, related_name='presence_hourly', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'f_UserPresenceHourly',
                'ordering': ['-work_date', '-hour'],
                'unique_together': {('user', 'work_date', 'hour')},
            },
        ),
    ]
