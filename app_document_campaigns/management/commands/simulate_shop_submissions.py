"""Explicit, audited simulation; never sends post-submit emails/tasks."""
from collections import Counter
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from app_document_campaigns.models import Campaign, CampaignError, CampaignStatusHistory, ChecklistQuestion, ShopAccessLink, ShopResponse, ShopSubmission


class Command(BaseCommand):
    help = "Generate marked test responses and submit every PGD in one named campaign."

    def add_arguments(self, parser):
        parser.add_argument("campaign_code")
        parser.add_argument("--confirm-simulation", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        if not options["confirm_simulation"]:
            raise CommandError("Requires --confirm-simulation. This creates synthetic business data.")
        campaign = Campaign.objects.select_for_update().get(code=options["campaign_code"])
        if campaign.status != Campaign.Status.ACTIVE:
            raise CommandError("Campaign must be active; finalized campaigns cannot be simulated.")
        errors = list(campaign.errors.select_for_update().exclude(status__in=["excluded", "cancelled"]).only("id", "shop_id", "status", "checklist_template_id"))
        allowed = {"ready", "waiting_shop", "shop_draft", "shop_submitted", "shop_supplement"}
        if any(error.status not in allowed for error in errors):
            raise CommandError("Campaign has progressed beyond shop/team review; simulation refused.")
        templates = {}
        for question in ChecklistQuestion.objects.filter(template_id__in={e.checklist_template_id for e in errors}, is_active=True, code="SHOP_RESPONSE"):
            values = []
            for option in question.options:
                value = option.get("value") or option.get("label") if isinstance(option, dict) else option
                if value:
                    values.append(str(value))
            templates[question.template_id] = values
        campaign_choices = list(campaign.response_options.values_list("value", flat=True))
        if campaign_choices:
            templates = {e.checklist_template_id: campaign_choices for e in errors}
        if any(not templates.get(e.checklist_template_id) for e in errors):
            raise CommandError("Some errors have no configured SHOP_RESPONSE options; refusing invented choices.")
        now = timezone.now()
        existing = {r.error_id: r for r in ShopResponse.objects.select_for_update().filter(error__in=errors)}
        new, filled, histories = [], [], []
        counts = Counter()
        for error in errors:
            counts[error.shop_id] += 1
            response = existing.get(error.pk)
            if not response or not response.answer_code:
                choices = templates[error.checklist_template_id]
                answer = choices[1] if len(choices) > 1 and error.pk % 5 == 0 else choices[0]
                marker = "[GIA LAP] Phan hoi tao de kiem thu team review; khong phai phan hoi thuc te cua PGD."
                if response:
                    response.answer_code = answer
                    response.note = (response.note + "\n" + marker).strip()
                    response.answer_payload = {**response.answer_payload, "simulation": True}
                    filled.append(response)
                else:
                    new.append(ShopResponse(error=error, shop_id=error.shop_id, answer_code=answer, note=marker, answer_payload={"simulation": True}, status="submitted", submitted_at=now))
            if error.status != "shop_submitted":
                histories.append(CampaignStatusHistory(campaign=campaign, error=error, from_status=error.status, to_status="shop_submitted", reason="[GIA LAP] Admin requested simulated official PGD submission; original answers preserved; no email sent."))
        ShopResponse.objects.bulk_create(new, batch_size=1000)
        ShopResponse.objects.bulk_update(filled, ["answer_code", "note", "answer_payload"], batch_size=1000)
        ShopResponse.objects.filter(error__in=errors).exclude(status="submitted").update(status="submitted", submitted_at=now, updated_at=now, version_no=F("version_no") + 1)
        CampaignStatusHistory.objects.bulk_create(histories, batch_size=1000)
        CampaignError.objects.filter(pk__in=[e.pk for e in errors]).exclude(status="shop_submitted").update(status="shop_submitted", updated_at=now)
        submitted = set(ShopSubmission.objects.filter(campaign=campaign).values_list("shop_id", flat=True))
        ShopSubmission.objects.bulk_create([ShopSubmission(campaign=campaign, shop_id=shop_id, idempotency_key=f"simulation:{campaign.pk}:shop:{shop_id}", response_count=count, submitted_at=now) for shop_id, count in counts.items() if shop_id not in submitted], batch_size=1000)
        cutoff = now - timedelta(minutes=1)
        if not campaign.response_deadline or campaign.response_deadline > cutoff:
            campaign.response_deadline = cutoff
            campaign.save(update_fields=["response_deadline", "updated_at"])
        ShopAccessLink.objects.filter(campaign=campaign, revoked_at__isnull=True, response_deadline__gt=cutoff).update(response_deadline=cutoff)
        CampaignStatusHistory.objects.create(campaign=campaign, from_status=campaign.status, to_status=campaign.status, reason=f"[GIA LAP] Synthetic answers: {len(new) + len(filled)}; shops submitted: {len(counts)}; original answers preserved. Deadline closed; ready for team review. No email sent.")
        self.stdout.write(f"campaign_id={campaign.pk}; rows={len(errors)}; synthetic={len(new)+len(filled)}; preserved={len(errors)-len(new)-len(filled)}; shops={len(counts)}; submitted_all=True; links_locked=True")
