from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='WorkPolicy',
            fields=[
                ('policy_id', models.AutoField(primary_key=True, serialize=False)),
                ('policy_name', models.CharField(default='Default', max_length=100)),
                ('working_days', models.CharField(default='0,1,2,3,4', max_length=20)),
                ('open_time', models.TimeField()),
                ('close_time', models.TimeField()),
                ('lunch_start', models.TimeField()),
                ('lunch_end', models.TimeField()),
                ('max_shifts_per_day', models.PositiveSmallIntegerField(default=2)),
                ('max_hours_per_day', models.DecimalField(decimal_places=2, default=8, max_digits=5)),
                ('max_hours_per_week', models.DecimalField(decimal_places=2, default=40, max_digits=5)),
                ('effective_from', models.DateField(blank=True, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, db_column='created_by', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='work_policies_created', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, db_column='updated_by', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='work_policies_updated', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'd_WorkPolicy',
                'ordering': ['-effective_from', '-policy_id'],
            },
        ),
        migrations.CreateModel(
            name='WorkWeek',
            fields=[
                ('week_id', models.AutoField(primary_key=True, serialize=False)),
                ('week_start_date', models.DateField()),
                ('week_end_date', models.DateField()),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('submitted', 'Submitted'), ('locked', 'Locked')], default='draft', max_length=20)),
                ('total_hours', models.DecimalField(decimal_places=2, default=0, max_digits=6)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, db_column='created_by', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='work_weeks_created', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, db_column='updated_by', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='work_weeks_updated', to=settings.AUTH_USER_MODEL)),
                ('user', models.ForeignKey(db_column='user_id', on_delete=django.db.models.deletion.CASCADE, related_name='work_weeks', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'f_WorkWeek',
                'ordering': ['-week_start_date'],
                'unique_together': {('user', 'week_start_date')},
            },
        ),
        migrations.CreateModel(
            name='WorkShift',
            fields=[
                ('shift_id', models.AutoField(primary_key=True, serialize=False)),
                ('shift_date', models.DateField()),
                ('shift_index', models.PositiveSmallIntegerField(default=1)),
                ('start_time', models.TimeField()),
                ('end_time', models.TimeField()),
                ('total_hours', models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, db_column='created_by', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='work_shifts_created', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, db_column='updated_by', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='work_shifts_updated', to=settings.AUTH_USER_MODEL)),
                ('work_week', models.ForeignKey(db_column='week_id', on_delete=django.db.models.deletion.CASCADE, related_name='shifts', to='app_workshift.workweek')),
            ],
            options={
                'db_table': 'f_WorkShift',
                'ordering': ['shift_date', 'shift_index'],
                'unique_together': {('work_week', 'shift_date', 'shift_index')},
            },
        ),
        migrations.CreateModel(
            name='TaskCatalog',
            fields=[
                ('task_id', models.AutoField(primary_key=True, serialize=False)),
                ('task_code', models.CharField(max_length=50, unique=True)),
                ('task_name', models.CharField(max_length=255)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, db_column='created_by', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='task_catalog_created', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, db_column='updated_by', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='task_catalog_updated', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'd_TaskCatalog',
                'ordering': ['task_name'],
            },
        ),
        migrations.CreateModel(
            name='TaskAssignment',
            fields=[
                ('assignment_id', models.AutoField(primary_key=True, serialize=False)),
                ('planned_hours', models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ('note', models.TextField(blank=True, null=True)),
                ('assigned_at', models.DateTimeField(auto_now_add=True)),
                ('assigned_by', models.ForeignKey(blank=True, db_column='assigned_by', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='task_assignments_created', to=settings.AUTH_USER_MODEL)),
                ('task', models.ForeignKey(db_column='task_id', on_delete=django.db.models.deletion.CASCADE, to='app_workshift.taskcatalog')),
                ('work_shift', models.ForeignKey(db_column='shift_id', on_delete=django.db.models.deletion.CASCADE, related_name='task_assignments', to='app_workshift.workshift')),
            ],
            options={
                'db_table': 'f_TaskAssignment',
                'ordering': ['-assigned_at'],
            },
        ),
        migrations.CreateModel(
            name='TaskWorklog',
            fields=[
                ('worklog_id', models.AutoField(primary_key=True, serialize=False)),
                ('actual_hours', models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ('note', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, db_column='created_by', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='task_worklogs_created', to=settings.AUTH_USER_MODEL)),
                ('task', models.ForeignKey(db_column='task_id', on_delete=django.db.models.deletion.CASCADE, to='app_workshift.taskcatalog')),
                ('work_shift', models.ForeignKey(db_column='shift_id', on_delete=django.db.models.deletion.CASCADE, related_name='task_worklogs', to='app_workshift.workshift')),
            ],
            options={
                'db_table': 'f_TaskWorklog',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='WorkAuditLog',
            fields=[
                ('log_id', models.AutoField(primary_key=True, serialize=False)),
                ('entity_type', models.CharField(max_length=50)),
                ('entity_id', models.IntegerField()),
                ('action', models.CharField(max_length=50)),
                ('before_data', models.JSONField(blank=True, null=True)),
                ('after_data', models.JSONField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(blank=True, db_column='actor', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='work_audit_logs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'f_WorkAuditLog',
                'ordering': ['-created_at'],
            },
        ),
    ]
