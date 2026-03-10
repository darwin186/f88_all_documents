from django.db import models
from django.contrib.auth.models import User


class WorkPolicy(models.Model):
    policy_id = models.AutoField(primary_key=True)
    policy_name = models.CharField(max_length=100, default='Default')
    working_days = models.CharField(max_length=20, default='0,1,2,3,4')
    open_time = models.TimeField()
    close_time = models.TimeField()
    lunch_start = models.TimeField()
    lunch_end = models.TimeField()
    max_shifts_per_day = models.PositiveSmallIntegerField(default=2)
    max_hours_per_day = models.DecimalField(max_digits=5, decimal_places=2, default=8)
    max_hours_per_week = models.DecimalField(max_digits=5, decimal_places=2, default=40)
    max_hours_per_month = models.DecimalField(max_digits=6, decimal_places=2, default=160)
    min_hours_per_shift = models.DecimalField(max_digits=4, decimal_places=2, default=4)
    effective_from = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        db_column='created_by',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='work_policies_created',
    )
    updated_by = models.ForeignKey(
        User,
        db_column='updated_by',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='work_policies_updated',
    )

    class Meta:
        db_table = 'd_WorkPolicy'
        ordering = ['-effective_from', '-policy_id']

    def __str__(self):
        return self.policy_name


class WorkWeek(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        SUBMITTED = 'submitted', 'Submitted'
        LOCKED = 'locked', 'Locked'

    week_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, db_column='user_id', on_delete=models.CASCADE, related_name='work_weeks')
    week_start_date = models.DateField()
    week_end_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    total_hours = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        db_column='created_by',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='work_weeks_created',
    )
    updated_by = models.ForeignKey(
        User,
        db_column='updated_by',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='work_weeks_updated',
    )

    class Meta:
        db_table = 'f_WorkWeek'
        unique_together = ('user', 'week_start_date')
        ordering = ['-week_start_date']

    def __str__(self):
        return f"{self.user.username} - {self.week_start_date}"


class WorkShift(models.Model):
    shift_id = models.AutoField(primary_key=True)
    work_week = models.ForeignKey(WorkWeek, db_column='week_id', on_delete=models.CASCADE, related_name='shifts')
    shift_date = models.DateField()
    shift_index = models.PositiveSmallIntegerField(default=1)
    start_time = models.TimeField()
    end_time = models.TimeField()
    total_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        db_column='created_by',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='work_shifts_created',
    )
    updated_by = models.ForeignKey(
        User,
        db_column='updated_by',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='work_shifts_updated',
    )

    class Meta:
        db_table = 'f_WorkShift'
        unique_together = ('work_week', 'shift_date', 'shift_index')
        ordering = ['shift_date', 'shift_index']

    def __str__(self):
        return f"{self.work_week.user.username} - {self.shift_date} ({self.shift_index})"


class TaskCatalog(models.Model):
    task_id = models.AutoField(primary_key=True)
    task_code = models.CharField(max_length=50, unique=True)
    task_name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        db_column='created_by',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='task_catalog_created',
    )
    updated_by = models.ForeignKey(
        User,
        db_column='updated_by',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='task_catalog_updated',
    )

    class Meta:
        db_table = 'd_TaskCatalog'
        ordering = ['task_name']

    def __str__(self):
        return self.task_name


class TaskAssignment(models.Model):
    assignment_id = models.AutoField(primary_key=True)
    work_shift = models.ForeignKey(WorkShift, db_column='shift_id', on_delete=models.CASCADE, related_name='task_assignments')
    task = models.ForeignKey(TaskCatalog, db_column='task_id', on_delete=models.CASCADE)
    planned_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    note = models.TextField(null=True, blank=True)
    assigned_by = models.ForeignKey(
        User,
        db_column='assigned_by',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='task_assignments_created',
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'f_TaskAssignment'
        ordering = ['-assigned_at']

    def __str__(self):
        return f"{self.work_shift} - {self.task.task_name}"


class TaskWorklog(models.Model):
    worklog_id = models.AutoField(primary_key=True)
    work_shift = models.ForeignKey(WorkShift, db_column='shift_id', on_delete=models.CASCADE, related_name='task_worklogs')
    task = models.ForeignKey(TaskCatalog, db_column='task_id', on_delete=models.CASCADE)
    actual_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    note = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        db_column='created_by',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='task_worklogs_created',
    )

    class Meta:
        db_table = 'f_TaskWorklog'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.work_shift} - {self.task.task_name}"


class WorkAuditLog(models.Model):
    log_id = models.AutoField(primary_key=True)
    entity_type = models.CharField(max_length=50)
    entity_id = models.IntegerField()
    action = models.CharField(max_length=50)
    before_data = models.JSONField(null=True, blank=True)
    after_data = models.JSONField(null=True, blank=True)
    actor = models.ForeignKey(
        User,
        db_column='actor',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='work_audit_logs',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'f_WorkAuditLog'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.entity_type} {self.entity_id} - {self.action}"
