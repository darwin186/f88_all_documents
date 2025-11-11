from django.apps import AppConfig


class AppDocumentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_documents'
    
    def ready(self):
        import app_documents.signals  # Replace with the actual path to your signals