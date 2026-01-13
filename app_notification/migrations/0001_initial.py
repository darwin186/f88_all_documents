from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='NotificationReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=100, unique=True)),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
                ('default_channel', models.CharField(choices=[('gapo', 'Gapo Chat'), ('email', 'Email'), ('teams', 'Microsoft Teams')], default='gapo', max_length=20)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='notification_reports', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'f_notification_report',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='NotificationSubscription',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('channel', models.CharField(choices=[('gapo', 'Gapo Chat'), ('email', 'Email'), ('teams', 'Microsoft Teams')], default='gapo', max_length=20)),
                ('target', models.CharField(help_text='Địa chỉ nhận: Gapo user id, email hoặc webhook', max_length=255)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('report', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='subscriptions', to='app_notification.notificationreport')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notification_subscriptions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'f_notification_subscription',
                'ordering': ['-created_at'],
                'unique_together': {('user', 'report', 'channel', 'target')},
            },
        ),
        migrations.CreateModel(
            name='NotificationSchedule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('channel', models.CharField(choices=[('gapo', 'Gapo Chat'), ('email', 'Email'), ('teams', 'Microsoft Teams')], max_length=20)),
                ('target', models.CharField(max_length=255)),
                ('message', models.TextField()),
                ('schedule_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('sent', 'Sent'), ('failed', 'Failed'), ('cancelled', 'Cancelled')], default='pending', max_length=20)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('last_error', models.TextField(blank=True, null=True)),
                ('metadata', models.JSONField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_notifications', to=settings.AUTH_USER_MODEL)),
                ('report', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='schedules', to='app_notification.notificationreport')),
                ('subscription', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='schedules', to='app_notification.notificationsubscription')),
            ],
            options={
                'db_table': 'f_notification_schedule',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='notificationschedule',
            index=models.Index(fields=['status', 'schedule_at'], name='app_notific_status_23d6dd_idx'),
        ),
    ]
