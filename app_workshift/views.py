from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.db import models
from django.utils import timezone
from django.core.serializers.json import DjangoJSONEncoder
import json

from app_documents.utils import get_user_context, require_ui_permission

from .models import (
    WorkPolicy,
    WorkWeek,
    WorkShift,
    TaskCatalog,
    TaskAssignment,
    WorkAuditLog,
)


DEFAULT_POLICY = {
    'working_days': [0, 1, 2, 3, 4],
    'open_time': '08:00',
    'close_time': '17:30',
    'lunch_start': '12:00',
    'lunch_end': '13:30',
    'max_shifts_per_day': 2,
    'max_hours_per_day': Decimal('8'),
    'max_hours_per_week': Decimal('40'),
    'max_hours_per_month': Decimal('160'),
    'min_hours_per_shift': Decimal('4'),
}


def _parse_time(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, '%H:%M').time()
    except ValueError:
        return None


def _get_active_policy():
    return WorkPolicy.objects.filter(is_active=True).order_by('-effective_from', '-policy_id').first()


def _get_policy_values(policy):
    if not policy:
        return {
            'working_days': DEFAULT_POLICY['working_days'],
            'open_time': _parse_time(DEFAULT_POLICY['open_time']),
            'close_time': _parse_time(DEFAULT_POLICY['close_time']),
            'lunch_start': _parse_time(DEFAULT_POLICY['lunch_start']),
            'lunch_end': _parse_time(DEFAULT_POLICY['lunch_end']),
            'max_shifts_per_day': DEFAULT_POLICY['max_shifts_per_day'],
            'max_hours_per_day': DEFAULT_POLICY['max_hours_per_day'],
            'max_hours_per_week': DEFAULT_POLICY['max_hours_per_week'],
            'max_hours_per_month': DEFAULT_POLICY['max_hours_per_month'],
            'min_hours_per_shift': DEFAULT_POLICY['min_hours_per_shift'],
        }
    working_days = []
    if policy.working_days:
        for part in policy.working_days.split(','):
            try:
                working_days.append(int(part.strip()))
            except ValueError:
                continue
    if not working_days:
        working_days = DEFAULT_POLICY['working_days']
    return {
        'working_days': working_days,
        'open_time': policy.open_time,
        'close_time': policy.close_time,
        'lunch_start': policy.lunch_start,
        'lunch_end': policy.lunch_end,
        'max_shifts_per_day': policy.max_shifts_per_day,
        'max_hours_per_day': policy.max_hours_per_day,
        'max_hours_per_week': policy.max_hours_per_week,
        'max_hours_per_month': policy.max_hours_per_month,
        'min_hours_per_shift': policy.min_hours_per_shift,
    }


def _get_week_start(date_val):
    return date_val - timedelta(days=date_val.weekday())


def _get_week_days(week_start):
    return [week_start + timedelta(days=idx) for idx in range(5)]


def _get_month_range(date_val):
    if date_val.day >= 25:
        start = date_val.replace(day=25)
        if date_val.month == 12:
            end = date_val.replace(year=date_val.year + 1, month=1, day=24)
        else:
            end = date_val.replace(month=date_val.month + 1, day=24)
    else:
        if date_val.month == 1:
            start = date_val.replace(year=date_val.year - 1, month=12, day=25)
        else:
            start = date_val.replace(month=date_val.month - 1, day=25)
        end = date_val.replace(day=24)
    return start, end


def _calc_hours(day, start_time, end_time, lunch_start, lunch_end):
    if not start_time or not end_time:
        return None
    start_dt = datetime.combine(day, start_time)
    end_dt = datetime.combine(day, end_time)
    if end_dt <= start_dt:
        return None
    total = Decimal((end_dt - start_dt).total_seconds()) / Decimal(3600)
    if lunch_start and lunch_end:
        lunch_start_dt = datetime.combine(day, lunch_start)
        lunch_end_dt = datetime.combine(day, lunch_end)
        overlap = max(
            Decimal('0'),
            Decimal((min(end_dt, lunch_end_dt) - max(start_dt, lunch_start_dt)).total_seconds()) / Decimal(3600),
        )
        total = total - overlap
    if total <= 0:
        return None
    return total.quantize(Decimal('0.01'))


def _build_week_context(user, week_start, policy_values, selected_user=None):
    month_start, month_end = _get_month_range(week_start)
    month_start, month_end = _get_month_range(week_start)
    month_start, month_end = _get_month_range(week_start)
    week_days = _get_week_days(week_start)
    week_end = week_days[-1]
    month_start, month_end = _get_month_range(week_start)
    prev_week = week_start - timedelta(days=7)
    next_week = week_start + timedelta(days=7)
    work_week = WorkWeek.objects.filter(user=user, week_start_date=week_start).first()
    shifts = []
    if work_week:
        shifts = list(WorkShift.objects.filter(work_week=work_week))
    shift_map = {}
    for shift in shifts:
        day_key = shift.shift_date.isoformat()
        shift_map.setdefault(day_key, {})[shift.shift_index] = shift
    daily_totals = {}
    for day in week_days:
        daily_total = Decimal('0')
        for idx in range(1, policy_values['max_shifts_per_day'] + 1):
            shift = shift_map.get(day.isoformat(), {}).get(idx)
            if shift:
                daily_total += shift.total_hours
        daily_totals[day.isoformat()] = daily_total
    total_hours = work_week.total_hours if work_week else Decimal('0')
    shift_rows = []
    for day in week_days:
        day_key = day.isoformat()
        shifts = {}
        for idx in range(1, policy_values['max_shifts_per_day'] + 1):
            shift = shift_map.get(day_key, {}).get(idx)
            shifts[str(idx)] = {
                'start_time': shift.start_time.strftime('%H:%M') if shift else '',
                'end_time': shift.end_time.strftime('%H:%M') if shift else '',
            }
        shift_rows.append({
            'day': day,
            'day_key': day_key,
            'shifts': shifts,
            'total_hours': daily_totals.get(day_key, Decimal('0')),
        })
    return {
        'week_days': week_days,
        'week_end': week_end,
        'work_week': work_week,
        'shift_rows': shift_rows,
        'total_hours': total_hours,
    }


@login_required
@require_ui_permission('workshift_register')
def workshift_register_view(request):
    user_context = get_user_context(request.user)
    is_admin = user_context.get('is_admin') or user_context.get('is_super_admin')

    policy = _get_active_policy()
    policy_values = _get_policy_values(policy)
    max_shift_hours = Decimal('0')
    if policy_values.get('max_shifts_per_day'):
        try:
            max_shift_hours = (policy_values['max_hours_per_day'] / Decimal(policy_values['max_shifts_per_day'])).quantize(Decimal('0.01'))
        except Exception:
            max_shift_hours = Decimal('0')
    min_shift_hours = policy_values.get('min_hours_per_shift') or Decimal('4')

    selected_user = request.user
    user_id = request.GET.get('user_id')
    if is_admin and user_id:
        selected_user = get_object_or_404(User, pk=user_id)

    week_param = request.GET.get('week_start')
    if week_param:
        try:
            week_start = datetime.strptime(week_param, '%Y-%m-%d').date()
        except ValueError:
            week_start = _get_week_start(datetime.today().date())
    else:
        week_start = _get_week_start(datetime.today().date())
    prev_week = week_start - timedelta(days=7)
    next_week = week_start + timedelta(days=7)
    prev_week = week_start - timedelta(days=7)
    next_week = week_start + timedelta(days=7)
    prev_week = week_start - timedelta(days=7)
    next_week = week_start + timedelta(days=7)
    prev_week = week_start - timedelta(days=7)
    next_week = week_start + timedelta(days=7)
    prev_week = week_start - timedelta(days=7)
    next_week = week_start + timedelta(days=7)

    prev_week = week_start - timedelta(days=7)
    next_week = week_start + timedelta(days=7)

    month_start, month_end = _get_month_range(week_start)
    week_days = _get_week_days(week_start)
    week_end = week_days[-1]
    work_week = WorkWeek.objects.filter(user=selected_user, week_start_date=week_start).first()
    month_hours = WorkShift.objects.filter(
        work_week__user=selected_user,
        shift_date__range=(month_start, month_end),
    ).aggregate(total=models.Sum('total_hours')).get('total') or Decimal('0')
    is_locked = work_week and work_week.status in [WorkWeek.Status.SUBMITTED, WorkWeek.Status.LOCKED]
    slot_times = []
    if policy_values.get('open_time') and policy_values.get('close_time'):
        slot_dt = datetime.combine(datetime.today().date(), policy_values['open_time'])
        end_dt = datetime.combine(datetime.today().date(), policy_values['close_time'])
        step = timedelta(minutes=30)
        while slot_dt < end_dt:
            slot_times.append(slot_dt.strftime('%H:%M'))
            slot_dt += step

    assignment_map = {}
    if work_week:
        assignments = TaskAssignment.objects.filter(work_shift__work_week=work_week).select_related('task', 'work_shift')
        for assignment in assignments:
            day_key = assignment.work_shift.shift_date.isoformat()
            shift_key = str(assignment.work_shift.shift_index)
            assignment_map.setdefault(day_key, {}).setdefault(shift_key, []).append({
                'task': assignment.task.task_name,
                'hours': float(assignment.planned_hours),
            })

    errors = []
    if request.method == 'POST':
        action = request.POST.get('action', 'draft')
        if is_locked and not is_admin:
            messages.error(request, 'Tuần làm việc đã submit. Vui lòng liên hệ admin để chỉnh sửa.')
            return redirect(request.path + f'?week_start={week_start}')

        shifts_payload = []
        daily_totals = {day: Decimal('0') for day in week_days}
        form_values = {}
        weekly_total = Decimal('0')

        for day in week_days:
            day_allowed = day.weekday() in policy_values['working_days']
            daily_shifts = []
            for idx in range(1, policy_values['max_shifts_per_day'] + 1):
                start_key = f'shift_{day.isoformat()}_{idx}_start'
                end_key = f'shift_{day.isoformat()}_{idx}_end'
                start_val = request.POST.get(start_key, '').strip()
                end_val = request.POST.get(end_key, '').strip()
                form_values[f'{day.isoformat()}_{idx}_start'] = start_val
                form_values[f'{day.isoformat()}_{idx}_end'] = end_val
                if not start_val and not end_val:
                    continue
                if not day_allowed:
                    errors.append(f'{day.strftime("%d/%m")} không thuộc ngày làm việc.')
                    continue
                start_time = _parse_time(start_val)
                end_time = _parse_time(end_val)
                if not start_time or not end_time:
                    errors.append(f'{day.strftime("%d/%m")} ca {idx}: giờ không hợp lệ.')
                    continue
                if start_time < policy_values['open_time'] or end_time > policy_values['close_time']:
                    errors.append(f'{day.strftime("%d/%m")} ca {idx}: ngoài giờ mở/kết kho.')
                    continue
                hours = _calc_hours(day, start_time, end_time, policy_values['lunch_start'], policy_values['lunch_end'])
                if hours is None:
                    errors.append(f'{day.strftime("%d/%m")} ca {idx}: ca làm việc không hợp lệ.')
                    continue
                if min_shift_hours and hours < min_shift_hours:
                    errors.append(f'{day.strftime("%d/%m")} ca {idx} tối thiểu {min_shift_hours} giờ.')
                    continue
                if max_shift_hours and hours > max_shift_hours:
                    errors.append(f'{day.strftime("%d/%m")} ca {idx} vượt quá {max_shift_hours} giờ/ca.')
                    continue
                daily_shifts.append((start_time, end_time))
                daily_totals[day] += hours
                weekly_total += hours
                shifts_payload.append({
                    'shift_date': day,
                    'shift_index': idx,
                    'start_time': start_time,
                    'end_time': end_time,
                    'total_hours': hours,
                })
            if len(daily_shifts) > policy_values['max_shifts_per_day']:
                errors.append(f'{day.strftime("%d/%m")} vượt quá số ca tối đa.')
            if len(daily_shifts) == 2:
                first = daily_shifts[0]
                second = daily_shifts[1]
                if first[1] > second[0]:
                    errors.append(f'{day.strftime("%d/%m")} ca làm việc bị chồng giờ.')
            if daily_totals[day] > policy_values['max_hours_per_day']:
                errors.append(f'{day.strftime("%d/%m")} vượt quá {policy_values["max_hours_per_day"]} giờ/ngày.')

        if weekly_total > policy_values['max_hours_per_week']:
            errors.append(f'Vượt quá {policy_values["max_hours_per_week"]} giờ/tuần.')

        if errors:
            shift_rows = []
            for day in week_days:
                day_key = day.isoformat()
                shifts = {}
                for idx in range(1, policy_values['max_shifts_per_day'] + 1):
                    shifts[str(idx)] = {
                        'start_time': form_values.get(f'{day_key}_{idx}_start', ''),
                        'end_time': form_values.get(f'{day_key}_{idx}_end', ''),
                    }
                shift_rows.append({
                    'day': day,
                    'day_key': day_key,
                    'shifts': shifts,
                    'total_hours': daily_totals.get(day, Decimal('0')),
                })
            context = {
                **user_context,
                'policy': policy,
                'policy_values': policy_values,
                'week_start': week_start,
                'week_end': week_end,
                'week_days': week_days,
                'prev_week': prev_week,
                'next_week': next_week,
                'shift_rows': shift_rows,
                'total_hours': weekly_total,
                'month_hours': month_hours,
                'month_start': month_start,
                'month_end': month_end,
                'slot_times': slot_times,
                'assignment_map_json': json.dumps(assignment_map, cls=DjangoJSONEncoder),
                'errors': errors,
                'selected_user': selected_user,
                'is_admin': is_admin,
                'is_locked': is_locked,
            }
            return render(request, 'app_workshift/workshift_register.html', context)

        if not work_week:
            work_week = WorkWeek.objects.create(
                user=selected_user,
                week_start_date=week_start,
                week_end_date=week_end,
                status=WorkWeek.Status.DRAFT,
                total_hours=weekly_total,
                created_by=request.user,
                updated_by=request.user,
            )
        else:
            work_week.total_hours = weekly_total
            work_week.updated_by = request.user
            work_week.updated_at = timezone.now()
            work_week.save(update_fields=['total_hours', 'updated_by', 'updated_at'])

        existing_shifts = WorkShift.objects.filter(work_week=work_week)
        before_data = list(existing_shifts.values('shift_date', 'shift_index', 'start_time', 'end_time', 'total_hours'))
        existing_map = {(s.shift_date, s.shift_index): s for s in existing_shifts}
        payload_keys = set()
        new_shifts = []
        for item in shifts_payload:
            key = (item['shift_date'], item['shift_index'])
            payload_keys.add(key)
            if key in existing_map:
                shift = existing_map[key]
                shift.start_time = item['start_time']
                shift.end_time = item['end_time']
                shift.total_hours = item['total_hours']
                shift.updated_by = request.user
                shift.save(update_fields=['start_time', 'end_time', 'total_hours', 'updated_by'])
            else:
                new_shifts.append(WorkShift(
                    work_week=work_week,
                    shift_date=item['shift_date'],
                    shift_index=item['shift_index'],
                    start_time=item['start_time'],
                    end_time=item['end_time'],
                    total_hours=item['total_hours'],
                    created_by=request.user,
                    updated_by=request.user,
                ))
        if new_shifts:
            WorkShift.objects.bulk_create(new_shifts)
        for key, shift in existing_map.items():
            if key not in payload_keys:
                shift.delete()

        if action == 'submit':
            work_week.status = WorkWeek.Status.SUBMITTED
            work_week.save(update_fields=['status'])
            messages.success(request, 'Đăng ký lịch làm việc thành công.')
        else:
            messages.success(request, 'Đã lưu bản nháp.')

        WorkAuditLog.objects.create(
            entity_type='WorkWeek',
            entity_id=work_week.week_id,
            action='submit' if action == 'submit' else 'save',
            before_data=json.loads(json.dumps({'shifts': before_data}, cls=DjangoJSONEncoder)),
            after_data=json.loads(json.dumps({'shifts': shifts_payload}, cls=DjangoJSONEncoder)),
            actor=request.user,
        )

        return redirect(f"{reverse('workshift_register')}?week_start={week_start}&user_id={selected_user.id}")

    week_context = _build_week_context(selected_user, week_start, policy_values, selected_user=selected_user)

    ctv_users = []
    if is_admin:
        ctv_users = User.objects.filter(groups__name='checker', is_active=True).order_by('username')

    context = {
        **user_context,
        'policy': policy,
        'policy_values': policy_values,
        'week_start': week_start,
        'week_end': week_context['week_end'],
        'week_days': week_context['week_days'],
        'shift_rows': week_context['shift_rows'],
        'total_hours': week_context['total_hours'],
        'month_hours': month_hours,
        'month_start': month_start,
        'month_end': month_end,
        'slot_times': slot_times,
        'assignment_map_json': json.dumps(assignment_map, cls=DjangoJSONEncoder),
        'work_week': week_context['work_week'],
        'selected_user': selected_user,
        'ctv_users': ctv_users,
        'is_admin': is_admin,
        'is_locked': is_locked,
        'prev_week': prev_week,
        'next_week': next_week,
    }
    return render(request, 'app_workshift/workshift_register.html', context)


@login_required
@require_ui_permission('workshift_tasks')
def workshift_tasks_view(request):
    user_context = get_user_context(request.user)
    is_admin = user_context.get('is_admin') or user_context.get('is_super_admin')
    task_tab = request.GET.get('tab', 'assign') if is_admin else 'assign'

    week_param = request.GET.get('week_start')
    if week_param:
        try:
            week_start = datetime.strptime(week_param, '%Y-%m-%d').date()
        except ValueError:
            week_start = _get_week_start(datetime.today().date())
    else:
        week_start = _get_week_start(datetime.today().date())
    prev_week = week_start - timedelta(days=7)
    next_week = week_start + timedelta(days=7)

    ctv_users = []
    if is_admin:
        ctv_users = User.objects.filter(groups__name='checker', is_active=True).order_by('username')
    users_to_show = ctv_users if is_admin else [request.user]

    work_weeks = WorkWeek.objects.filter(user__in=users_to_show, week_start_date=week_start).select_related('user')
    shifts = WorkShift.objects.filter(work_week__in=work_weeks).select_related('work_week', 'work_week__user') if work_weeks else []
    policy = _get_active_policy()
    policy_values = _get_policy_values(policy)
    week_days = _get_week_days(week_start)
    shift_indices = list(range(1, policy_values['max_shifts_per_day'] + 1))
    shift_grid = {
        user.id: {day.isoformat(): {idx: None for idx in shift_indices} for day in week_days}
        for user in users_to_show
    }
    for shift in shifts:
        day_key = shift.shift_date.isoformat()
        user_id = shift.work_week.user_id
        if user_id in shift_grid and day_key in shift_grid[user_id]:
            shift_grid[user_id][day_key][shift.shift_index] = shift
    tasks = TaskCatalog.objects.filter(is_active=True).order_by('task_name')
    tasks_catalog = TaskCatalog.objects.all().order_by('task_name') if is_admin else []

    if request.method == 'POST' and is_admin:
        action = request.POST.get('action', 'assign')
        if action == 'create_task':
            task_code = request.POST.get('task_code', '').strip()
            task_name = request.POST.get('task_name', '').strip()
            is_active = request.POST.get('is_active') == '1'
            if not task_code or not task_name:
                messages.error(request, 'Vui lòng nhập mã task và tên task.')
            elif TaskCatalog.objects.filter(task_code=task_code).exists():
                messages.error(request, 'Mã task đã tồn tại.')
            else:
                TaskCatalog.objects.create(
                    task_code=task_code,
                    task_name=task_name,
                    is_active=is_active,
                    created_by=request.user,
                    updated_by=request.user,
                )
                messages.success(request, 'Đã tạo task mới.')
            return redirect(f"{reverse('workshift_tasks')}?tab=catalog&week_start={week_start}")

        shift_id = request.POST.get('shift_id')
        task_id = request.POST.get('task_id')
        planned_hours = request.POST.get('planned_hours')
        note = request.POST.get('note', '').strip()
        try:
            planned_hours_val = Decimal(planned_hours)
        except (TypeError, ValueError, ArithmeticError):
            planned_hours_val = Decimal('0')
        if not shift_id or not task_id:
            messages.error(request, 'Vui lòng chọn ca và task.')
        else:
            shift = get_object_or_404(WorkShift, pk=shift_id)
            task = get_object_or_404(TaskCatalog, pk=task_id)
            current_total = shift.task_assignments.aggregate(total=models.Sum('planned_hours')).get('total') or Decimal('0')
            if planned_hours_val <= 0:
                messages.error(request, 'Giờ task không hợp lệ.')
            elif current_total + planned_hours_val > shift.total_hours:
                messages.error(request, 'Tổng giờ task vượt quá giờ ca.')
            else:
                TaskAssignment.objects.create(
                    work_shift=shift,
                    task=task,
                    planned_hours=planned_hours_val,
                    note=note or None,
                    assigned_by=request.user,
                )
                messages.success(request, 'Đã phân công task.')
        return redirect(f"{reverse('workshift_tasks')}?tab=assign&week_start={week_start}")

    assignments = TaskAssignment.objects.filter(work_shift__in=shifts).select_related('task', 'work_shift')
    assignments_by_shift = {}
    for assignment in assignments:
        assignments_by_shift.setdefault(assignment.work_shift_id, []).append(assignment)

    context = {
        **user_context,
        'week_start': week_start,
        'week_end': week_start + timedelta(days=4),
        'prev_week': prev_week,
        'next_week': next_week,
        'week_days': week_days,
        'shift_indices': shift_indices,
        'shift_grid': shift_grid,
        'users_to_show': users_to_show,
        'shifts': shifts,
        'assignments_by_shift': assignments_by_shift,
        'tasks': tasks,
        'tasks_catalog': tasks_catalog,
        'ctv_users': ctv_users,
        'is_admin': is_admin,
        'task_tab': task_tab,
    }
    return render(request, 'app_workshift/workshift_tasks.html', context)


@login_required
@require_ui_permission('workshift_policy')
def workshift_policy_view(request):
    user_context = get_user_context(request.user)
    is_admin = user_context.get('is_admin') or user_context.get('is_super_admin')
    if not is_admin:
        messages.error(request, 'Bạn không có quyền truy cập cấu hình.')
        return redirect('workshift_register')

    policies = WorkPolicy.objects.all().order_by('-effective_from', '-policy_id')
    selected_policy = None
    policy_id = request.GET.get('policy_id')
    is_new = request.GET.get('new') == '1'
    if is_new:
        selected_policy = None
    elif policy_id:
        selected_policy = get_object_or_404(WorkPolicy, pk=policy_id)
    else:
        selected_policy = policies.filter(is_active=True).first() or policies.first()

    errors = []
    form_data = {}
    selected_days = []
    if request.method == 'POST':
        policy_id = request.POST.get('policy_id') or ''
        policy_name = request.POST.get('policy_name', '').strip() or 'Default'
        working_days = request.POST.getlist('working_days')
        open_time = _parse_time(request.POST.get('open_time'))
        close_time = _parse_time(request.POST.get('close_time'))
        lunch_start = _parse_time(request.POST.get('lunch_start'))
        lunch_end = _parse_time(request.POST.get('lunch_end'))
        effective_from_raw = request.POST.get('effective_from')
        is_active = request.POST.get('is_active') == '1'
        try:
            max_shifts_per_day = int(request.POST.get('max_shifts_per_day') or 0)
        except ValueError:
            max_shifts_per_day = 0
        try:
            max_hours_per_day = Decimal(request.POST.get('max_hours_per_day') or '0')
        except (ValueError, ArithmeticError):
            max_hours_per_day = Decimal('0')
        try:
            max_hours_per_week = Decimal(request.POST.get('max_hours_per_week') or '0')
        except (ValueError, ArithmeticError):
            max_hours_per_week = Decimal('0')
        try:
            max_hours_per_month = Decimal(request.POST.get('max_hours_per_month') or '0')
        except (ValueError, ArithmeticError):
            max_hours_per_month = Decimal('0')
        try:
            min_hours_per_shift = Decimal(request.POST.get('min_hours_per_shift') or '0')
        except (ValueError, ArithmeticError):
            min_hours_per_shift = Decimal('0')

        effective_from = None
        if effective_from_raw:
            try:
                effective_from = datetime.strptime(effective_from_raw, '%Y-%m-%d').date()
            except ValueError:
                errors.append('Ngày hiệu lực không hợp lệ.')

        if not working_days:
            errors.append('Vui lòng chọn ngày làm việc.')
        if not open_time or not close_time:
            errors.append('Vui lòng nhập giờ mở/kết kho.')
        if open_time and close_time and open_time >= close_time:
            errors.append('Giờ mở kho phải trước giờ kết kho.')
        if lunch_start and lunch_end and lunch_start >= lunch_end:
            errors.append('Giờ nghỉ trưa không hợp lệ.')
        if max_shifts_per_day <= 0:
            errors.append('Số ca/ngày không hợp lệ.')
        if max_hours_per_day <= 0 or max_hours_per_week <= 0 or max_hours_per_month <= 0:
            errors.append('Hạn mức giờ không hợp lệ.')
        if min_hours_per_shift <= 0:
            errors.append('Giờ tối thiểu/ca không hợp lệ.')

        form_data = {
            'policy_id': policy_id,
            'policy_name': policy_name,
            'working_days': [int(day) for day in working_days if day.isdigit()],
            'open_time': request.POST.get('open_time') or '',
            'close_time': request.POST.get('close_time') or '',
            'lunch_start': request.POST.get('lunch_start') or '',
            'lunch_end': request.POST.get('lunch_end') or '',
            'max_shifts_per_day': max_shifts_per_day,
            'max_hours_per_day': max_hours_per_day,
            'max_hours_per_week': max_hours_per_week,
            'max_hours_per_month': request.POST.get('max_hours_per_month') or '',
            'min_hours_per_shift': request.POST.get('min_hours_per_shift') or '',
            'effective_from': effective_from_raw or '',
            'is_active': is_active,
        }
        selected_days = form_data['working_days']

        if not errors:
            if policy_id:
                selected_policy = get_object_or_404(WorkPolicy, pk=policy_id)
                selected_policy.policy_name = policy_name
                selected_policy.working_days = ','.join(sorted(working_days))
                selected_policy.open_time = open_time
                selected_policy.close_time = close_time
                selected_policy.lunch_start = lunch_start
                selected_policy.lunch_end = lunch_end
                selected_policy.max_shifts_per_day = max_shifts_per_day
                selected_policy.max_hours_per_day = max_hours_per_day
                selected_policy.max_hours_per_week = max_hours_per_week
                selected_policy.max_hours_per_month = max_hours_per_month
                selected_policy.min_hours_per_shift = min_hours_per_shift
                selected_policy.effective_from = effective_from
                selected_policy.updated_by = request.user
                selected_policy.is_active = is_active
                selected_policy.save()
            else:
                selected_policy = WorkPolicy.objects.create(
                    policy_name=policy_name,
                    working_days=','.join(sorted(working_days)),
                    open_time=open_time,
                    close_time=close_time,
                    lunch_start=lunch_start,
                    lunch_end=lunch_end,
                    max_shifts_per_day=max_shifts_per_day,
                    max_hours_per_day=max_hours_per_day,
                    max_hours_per_week=max_hours_per_week,
                    max_hours_per_month=max_hours_per_month,
                    min_hours_per_shift=min_hours_per_shift,
                    effective_from=effective_from,
                    is_active=is_active,
                    created_by=request.user,
                    updated_by=request.user,
                )
            if is_active:
                WorkPolicy.objects.exclude(pk=selected_policy.pk).update(is_active=False)
            messages.success(request, 'Đã lưu cấu hình work policy.')
            return redirect(f"{reverse('workshift_policy')}?policy_id={selected_policy.policy_id}")

    if not form_data and selected_policy:
        selected_days = [int(x) for x in (selected_policy.working_days or '').split(',') if x.strip().isdigit()]
        form_data = {
            'policy_id': selected_policy.policy_id,
            'policy_name': selected_policy.policy_name,
            'working_days': selected_days,
            'open_time': selected_policy.open_time.strftime('%H:%M') if selected_policy.open_time else '',
            'close_time': selected_policy.close_time.strftime('%H:%M') if selected_policy.close_time else '',
            'lunch_start': selected_policy.lunch_start.strftime('%H:%M') if selected_policy.lunch_start else '',
            'lunch_end': selected_policy.lunch_end.strftime('%H:%M') if selected_policy.lunch_end else '',
            'max_shifts_per_day': selected_policy.max_shifts_per_day,
            'max_hours_per_day': selected_policy.max_hours_per_day,
            'max_hours_per_week': selected_policy.max_hours_per_week,
            'max_hours_per_month': selected_policy.max_hours_per_month,
            'min_hours_per_shift': selected_policy.min_hours_per_shift,
            'effective_from': selected_policy.effective_from.strftime('%Y-%m-%d') if selected_policy.effective_from else '',
            'is_active': selected_policy.is_active,
        }

    day_labels = [
        (0, 'Thứ 2'),
        (1, 'Thứ 3'),
        (2, 'Thứ 4'),
        (3, 'Thứ 5'),
        (4, 'Thứ 6'),
    ]

    context = {
        **user_context,
        'policies': policies,
        'selected_policy': selected_policy,
        'form_data': form_data,
        'selected_days': selected_days,
        'errors': errors,
        'day_labels': day_labels,
        'is_admin': is_admin,
    }
    return render(request, 'app_workshift/workshift_policy.html', context)
