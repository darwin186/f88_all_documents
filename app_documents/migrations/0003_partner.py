from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('app_documents', '0002_areamanager_contractdetail_employee_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Partner',
            fields=[
                ('partner_id', models.AutoField(primary_key=True, serialize=False)),
                ('partner_code', models.CharField(max_length=10, unique=True)),
                ('partner_name', models.CharField(max_length=255, unique=True)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'db_table': 'd_Partner',
                'verbose_name': 'Partner Vendor',
                'verbose_name_plural': 'Partners',
            },
        ),
        migrations.AddField(
            model_name='partnerpackage',
            name='partner',
            field=models.ForeignKey(blank=True, db_column='partner_id', null=True, on_delete=django.db.models.deletion.SET_NULL, to='app_documents.partner'),
        ),
    ]
