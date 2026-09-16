import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from app_document_campaigns.models import CampaignVersion
from app_document_campaigns.services.imports import CampaignImportError
from app_document_campaigns.services.sql_sources import stage_monthly_sql_sources


class Command(BaseCommand):
    help = "Chạy hai nguồn SQL lỗi chứng từ vào staging của một campaign version nháp."

    def add_arguments(self, parser):
        parser.add_argument("version_id", type=int)
        parser.add_argument("--user-id", type=int, required=True)
        parser.add_argument("--database", default="default")

    def handle(self, *args, **options):
        try:
            version = CampaignVersion.objects.get(pk=options["version_id"])
            created_by = get_user_model().objects.get(pk=options["user_id"])
            result = stage_monthly_sql_sources(
                version=version,
                created_by=created_by,
                using=options["database"],
            )
        except CampaignVersion.DoesNotExist as exc:
            raise CommandError("Không tìm thấy campaign version.") from exc
        except get_user_model().DoesNotExist as exc:
            raise CommandError("Không tìm thấy user thực hiện import.") from exc
        except CampaignImportError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(json.dumps(result, ensure_ascii=False)))
