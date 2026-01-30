from django.contrib import admin
from .models import (
    WorkPolicy,
    WorkWeek,
    WorkShift,
    TaskCatalog,
    TaskAssignment,
    TaskWorklog,
    WorkAuditLog,
)


@admin.register(WorkPolicy)
class WorkPolicyAdmin(admin.ModelAdmin):
    list_display = (
        'policy_name',
        'is_active',
        'open_time',
        'close_time',
        'lunch_start',
        'lunch_end',
        'max_shifts_per_day',
        'max_hours_per_day',
        'max_hours_per_week',
        'max_hours_per_month',
    )
    list_filter = ('is_active',)
    search_fields = ('policy_name',)


@admin.register(WorkWeek)
class WorkWeekAdmin(admin.ModelAdmin):
    list_display = ('user', 'week_start_date', 'week_end_date', 'status', 'total_hours')
    list_filter = ('status',)
    search_fields = ('user__username',)


@admin.register(WorkShift)
class WorkShiftAdmin(admin.ModelAdmin):
    list_display = ('work_week', 'shift_date', 'shift_index', 'start_time', 'end_time', 'total_hours')
    list_filter = ('shift_date',)
    search_fields = ('work_week__user__username',)


@admin.register(TaskCatalog)
class TaskCatalogAdmin(admin.ModelAdmin):
    list_display = ('task_code', 'task_name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('task_code', 'task_name')


@admin.register(TaskAssignment)
class TaskAssignmentAdmin(admin.ModelAdmin):
    list_display = ('work_shift', 'task', 'planned_hours', 'assigned_by', 'assigned_at')
    search_fields = ('work_shift__work_week__user__username', 'task__task_name')


@admin.register(TaskWorklog)
class TaskWorklogAdmin(admin.ModelAdmin):
    list_display = ('work_shift', 'task', 'actual_hours', 'created_by', 'created_at')
    search_fields = ('work_shift__work_week__user__username', 'task__task_name')


@admin.register(WorkAuditLog)
class WorkAuditLogAdmin(admin.ModelAdmin):
    list_display = ('entity_type', 'entity_id', 'action', 'actor', 'created_at')
    list_filter = ('entity_type', 'action')
    search_fields = ('entity_type', 'entity_id', 'actor__username')
