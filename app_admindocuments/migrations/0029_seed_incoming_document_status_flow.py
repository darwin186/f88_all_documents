from django.db import migrations


def seed_document_status_flow(apps, schema_editor):
    Status = apps.get_model('app_admindocuments', 'AdmIncomingDispatchStatus')
    Dispatch = apps.get_model('app_admindocuments', 'AdmIncomingDispatch')

    statuses = [
        ('doc_received', 'Đã tiếp nhận', 6),
        ('doc_at_clerical', 'Đang ở Văn thư', 7),
        ('doc_at_assistant', 'Đang ở Ban trợ lý', 8),
        ('doc_archived', 'Lưu trữ', 9),
    ]
    for code, name, sort_order in statuses:
        Status.objects.update_or_create(
            code=code,
            defaults={
                'name': name,
                'sort_order': sort_order,
                'is_active': True,
            },
        )

    legacy_mapping = {
        'in_progress': 'doc_at_clerical',
        'to_btl': 'doc_at_assistant',
        'done': 'doc_archived',
        'archived': 'doc_archived',
    }
    for old_code, new_code in legacy_mapping.items():
        Dispatch.objects.filter(
            incoming_item_type_id='cong_van',
            status_id=old_code,
        ).update(status_id=new_code)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('app_admindocuments', '0028_remove_incoming_doc_pending_signer'),
    ]

    operations = [
        migrations.RunPython(seed_document_status_flow, noop),
    ]
