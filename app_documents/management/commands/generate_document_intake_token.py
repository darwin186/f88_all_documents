import hashlib
import secrets

from django.core.management.base import BaseCommand, CommandError

from app_documents.models import ExternalDocumentIntakeToken


class Command(BaseCommand):
    help = "Tạo token một lần cho API nhận batch chứng từ từ Prefect."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True, help="Tên nhận diện, ví dụ prefect-production")
        parser.add_argument("--scope", action="append", choices=["documents:write", "master_data:write"], required=True)

    def handle(self, *args, **options):
        name = options["name"].strip()
        if ExternalDocumentIntakeToken.objects.filter(name=name).exists():
            raise CommandError(f"Token name '{name}' đã tồn tại; không in lại token cũ.")
        raw = "doc_" + secrets.token_urlsafe(40)
        ExternalDocumentIntakeToken.objects.create(
            name=name, token_prefix=raw[:12], token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            scopes=sorted(set(options["scope"])),
        )
        self.stdout.write(self.style.SUCCESS("Token chỉ hiển thị đúng lần này. Lưu vào Prefect Secret:"))
        self.stdout.write(raw)
