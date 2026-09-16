from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("app_documents", "0040_shopcatalogjob")]
    operations = [migrations.AddConstraint(model_name="shopcatalogjob", constraint=models.UniqueConstraint(fields=("kind",), condition=models.Q(status__in=["queued", "running"]), name="one_active_shop_catalog_job_per_kind"))]
