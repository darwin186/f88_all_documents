from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('app_documents', '0008_add_badge_colors'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PartnerPackageHistory',
            fields=[
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('action', models.CharField(max_length=50)),
                ('old_value', models.CharField(blank=True, max_length=255, null=True)),
                ('new_value', models.CharField(blank=True, max_length=255, null=True)),
                ('note', models.CharField(blank=True, max_length=255, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, db_column='created_by', null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('package', models.ForeignKey(db_column='package_id', on_delete=django.db.models.deletion.CASCADE, related_name='partnerpackage_history', to='app_documents.package')),
            ],
            options={
                'db_table': 'd_PartnerPackageHistory',
                'ordering': ['-created_at'],
            },
        ),
    ]
