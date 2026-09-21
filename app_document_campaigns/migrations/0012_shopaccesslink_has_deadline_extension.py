from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("app_document_campaigns", "0011_teamreviewexceljob_and_more")]
    operations = [migrations.AddField(model_name="shopaccesslink", name="has_deadline_extension", field=models.BooleanField(default=False))]
