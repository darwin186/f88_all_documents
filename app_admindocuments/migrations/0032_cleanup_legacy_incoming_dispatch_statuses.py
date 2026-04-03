from django.db import migrations


DOC_STATUS_MAP = {
    'received': 'doc_received',
    'to_btl': 'doc_at_assistant',
    'to_pc': 'doc_at_assistant',
    'at_clerical': 'doc_at_clerical',
    'at_assistant': 'doc_at_assistant',
    'in_progress': 'doc_at_clerical',
    'pending_signer': 'doc_at_assistant',
    'doc_pending_signer': 'doc_at_assistant',
    'done': 'doc_archived',
    'archived': 'doc_archived',
}

PARCEL_STATUS_MAP = {
    'pkg_processing': 'pkg_done',
    'pkg_archived': 'pkg_done',
}

ACTIVE_STATUS_DEFAULTS = {
    'doc_received': {'name': 'Đã tiếp nhận', 'sort_order': 6},
    'doc_at_clerical': {'name': 'Đang ở Văn thư', 'sort_order': 7},
    'doc_at_assistant': {'name': 'Đang ở Ban trợ lý', 'sort_order': 8},
    'doc_archived': {'name': 'Lưu trữ', 'sort_order': 9},
    'pkg_received': {'name': 'Lễ tân tiếp nhận', 'sort_order': 1},
    'pkg_at_clerical': {'name': 'Đã thông báo', 'sort_order': 2},
    'pkg_done': {'name': 'Hoàn tất', 'sort_order': 3},
}

LEGACY_CODES_TO_DEACTIVATE = [
    'received',
    'to_btl',
    'to_pc',
    'at_clerical',
    'at_assistant',
    'in_progress',
    'pending_signer',
    'doc_pending_signer',
    'done',
    'archived',
    'pkg_processing',
    'pkg_archived',
]


def forwards(apps, schema_editor):
    Status = apps.get_model('app_admindocuments', 'AdmIncomingDispatchStatus')
    Dispatch = apps.get_model('app_admindocuments', 'AdmIncomingDispatch')
    DispatchStatusLog = apps.get_model('app_admindocuments', 'AdmIncomingDispatchStatusLog')
    ParcelReceipt = apps.get_model('app_admindocuments', 'AdmParcelReceipt')
    ParcelReceiptLog = apps.get_model('app_admindocuments', 'AdmParcelReceiptLog')

    for code, defaults in ACTIVE_STATUS_DEFAULTS.items():
        Status.objects.update_or_create(
            code=code,
            defaults={
                'name': defaults['name'],
                'sort_order': defaults['sort_order'],
                'is_active': True,
            },
        )

    for old_code, new_code in DOC_STATUS_MAP.items():
        Dispatch.objects.filter(status_id=old_code).update(status_id=new_code)
        DispatchStatusLog.objects.filter(from_status_id=old_code).update(from_status_id=new_code)
        DispatchStatusLog.objects.filter(to_status_id=old_code).update(to_status_id=new_code)

    for old_code, new_code in PARCEL_STATUS_MAP.items():
        ParcelReceipt.objects.filter(status_id=old_code).update(status_id=new_code)
        ParcelReceiptLog.objects.filter(from_status=old_code).update(from_status=new_code)
        ParcelReceiptLog.objects.filter(to_status=old_code).update(to_status=new_code)

    Status.objects.filter(code__in=LEGACY_CODES_TO_DEACTIVATE).update(is_active=False)


def backwards(apps, schema_editor):
    Status = apps.get_model('app_admindocuments', 'AdmIncomingDispatchStatus')
    Status.objects.filter(code__in=LEGACY_CODES_TO_DEACTIVATE).update(is_active=True)


class Migration(migrations.Migration):

    dependencies = [
        ('app_admindocuments', '0031_admincomingdispatchstatus_badge_colors'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
