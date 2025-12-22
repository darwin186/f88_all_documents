from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app_admindocuments", "0010_paper_soft_delete"),
    ]

    operations = [
        migrations.CreateModel(
            name="AdmPaperCounter",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("year", models.PositiveIntegerField()),
                ("next_number", models.PositiveIntegerField(default=1)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "paper_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="app_admindocuments.admpapertype",
                    ),
                ),
            ],
            options={
                "verbose_name": "Paper Counter",
                "verbose_name_plural": "Paper Counters",
                "db_table": "adm_paper_counter",
                "ordering": ["-year", "paper_type__name"],
                "unique_together": {("paper_type", "year")},
            },
        ),
    ]
