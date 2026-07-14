import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def seed_external_identities(apps, schema_editor):
    identity_model = apps.get_model("app_documents", "CollateralRegistrationExternalIdentity")
    registration_model = apps.get_model("app_documents", "CollateralRegistration")
    user_model = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    creator = user_model.objects.filter(is_superuser=True).order_by("id").first()
    if creator is None:
        creator = user_model.objects.order_by("id").first()
    codes = {"ketoan", "ketoan1"}
    codes.update(
        value.strip()
        for value in registration_model.objects.exclude(registered_by_name__isnull=True)
        .exclude(registered_by_name="")
        .values_list("registered_by_name", flat=True)
        if value and value.strip()
    )
    identities = {}
    for code in sorted(codes):
        identity, _ = identity_model.objects.get_or_create(
            external_code=code,
            defaults={
                "display_name": code,
                "created_by_id": creator.pk if creator else None,
                "updated_by_id": creator.pk if creator else None,
            },
        )
        identities[code] = identity

    for registration in registration_model.objects.exclude(registered_by_name__isnull=True).exclude(registered_by_name=""):
        code = registration.registered_by_name.strip()
        identity = identities.get(code)
        if identity:
            registration.registered_identity_id = identity.pk
            registration.save(update_fields=["registered_identity"])


class Migration(migrations.Migration):

    dependencies = [
        ("app_documents", "0026_collateralregistrationapitoken_and_postmini_default"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CollateralRegistrationExternalIdentity",
            fields=[
                ("identity_id", models.AutoField(primary_key=True, serialize=False)),
                ("external_code", models.CharField(max_length=100, unique=True)),
                ("display_name", models.CharField(blank=True, max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        db_column="created_by",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gddb_external_identities_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        db_column="updated_by",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gddb_external_identities_updated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "d_CollateralRegistrationExternalIdentity",
                "ordering": ["external_code"],
            },
        ),
        migrations.AddField(
            model_name="shop",
            name="default_gddb_identity",
            field=models.ForeignKey(
                blank=True,
                db_column="default_gddb_identity_id",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="default_shops",
                to="app_documents.collateralregistrationexternalidentity",
            ),
        ),
        migrations.AddField(
            model_name="collateralregistration",
            name="registered_identity",
            field=models.ForeignKey(
                blank=True,
                db_column="registered_identity_id",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="registrations",
                to="app_documents.collateralregistrationexternalidentity",
            ),
        ),
        migrations.RunPython(seed_external_identities, migrations.RunPython.noop),
    ]
