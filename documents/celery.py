import os
from celery import Celery
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "documents.settings")

app = Celery("documents")
app.config_from_object("django.conf:settings", namespace="CELERY")
# Explicitly include task modules to avoid discovery issues in some environments
app.autodiscover_tasks()
app.conf.imports = app.conf.imports or []
if "app_documents.tasks" not in app.conf.imports:
    app.conf.imports.append("app_documents.tasks")


@app.task(bind=True)
def debug_task(self):
    return f"Debug task executed: {self.request!r}"
