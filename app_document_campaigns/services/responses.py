import logging
from dataclasses import dataclass
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from app_document_campaigns.models import (
    Campaign,
    CampaignError,
    CampaignStatusHistory,
    ShopAccessLink,
    ShopResponse,
    ShopSubmission,
)


MAX_AUTOSAVE_BATCH_SIZE = 50
logger = logging.getLogger(__name__)


class ResponseError(Exception):
    pass


class ResponseValidationError(ResponseError):
    def __init__(self, message, *, missing_uids=None):
        self.missing_uids = missing_uids or []
        super().__init__(message)


class ResponseConflictError(ResponseError):
    def __init__(self, conflicts):
        self.conflicts = conflicts
        super().__init__("Dữ liệu đã thay đổi ở phiên khác.")


class ResponseReadOnlyError(ResponseError):
    pass


@dataclass(frozen=True)
class NormalizedChange:
    error_uid: UUID
    answer_code: str
    note: str
    answer_payload: dict
    expected_version: int


def _normalize_changes(changes):
    if not isinstance(changes, list) or not changes:
        raise ResponseValidationError("Danh sách thay đổi không hợp lệ.")
    if len(changes) > MAX_AUTOSAVE_BATCH_SIZE:
        raise ResponseValidationError(f"Mỗi lần chỉ được lưu tối đa {MAX_AUTOSAVE_BATCH_SIZE} dòng.")

    normalized = []
    seen = set()
    for item in changes:
        if not isinstance(item, dict):
            raise ResponseValidationError("Mỗi thay đổi phải là một object.")
        try:
            error_uid = UUID(str(item.get("error_uid", "")))
        except (TypeError, ValueError) as exc:
            raise ResponseValidationError("error_uid không hợp lệ.") from exc
        if error_uid in seen:
            raise ResponseValidationError("Một lỗi không được xuất hiện hai lần trong cùng batch.")
        seen.add(error_uid)

        answer_code = str(item.get("answer_code", "")).strip()
        note = str(item.get("note", "")).strip()
        answer_payload = item.get("answer_payload") or {}
        expected_version = item.get("version_no", 0)
        if not isinstance(answer_payload, dict):
            raise ResponseValidationError("answer_payload phải là object.")
        if not isinstance(expected_version, int) or expected_version < 0:
            raise ResponseValidationError("version_no không hợp lệ.")
        if len(answer_code) > 100:
            raise ResponseValidationError("Mã phản hồi quá dài.")

        normalized.append(
            NormalizedChange(
                error_uid=error_uid,
                answer_code=answer_code,
                note=note,
                answer_payload=answer_payload,
                expected_version=expected_version,
            )
        )
    return normalized


def _assert_link_editable(link):
    if link.campaign.status != Campaign.Status.ACTIVE:
        raise ResponseReadOnlyError("Chiến dịch hiện không nhận phản hồi.")
    if not link.is_editable:
        raise ResponseReadOnlyError("Đã hết thời gian cập nhật phản hồi.")
    if ShopSubmission.objects.filter(campaign=link.campaign, shop=link.shop).exists():
        raise ResponseReadOnlyError("PGD đã gửi phản hồi chính thức.")


@transaction.atomic
def save_response_batch(*, link, changes):
    link = ShopAccessLink.objects.select_for_update().select_related("campaign", "shop").get(pk=link.pk)
    _assert_link_editable(link)
    normalized = _normalize_changes(changes)
    allowed = set(link.campaign.response_options.values_list("value", flat=True))
    if allowed and any(item.answer_code and item.answer_code not in allowed for item in normalized):
        raise ResponseValidationError("Phản hồi không nằm trong danh sách áp dụng cho chiến dịch.")
    uids = [item.error_uid for item in normalized]
    errors = {
        item.error_uid: item
        for item in CampaignError.objects.filter(
            campaign=link.campaign,
            shop=link.shop,
            error_uid__in=uids,
        ).exclude(status__in=[CampaignError.Status.EXCLUDED, CampaignError.Status.CANCELLED])
    }
    if len(errors) != len(uids):
        raise ResponseValidationError("Có lỗi không thuộc phạm vi của PGD hoặc đã bị loại.")

    existing = {
        response.error.error_uid: response
        for response in ShopResponse.objects.select_for_update()
        .select_related("error")
        .filter(error__error_uid__in=uids, shop=link.shop)
    }

    conflicts = []
    for item in normalized:
        response = existing.get(item.error_uid)
        current_version = response.version_no if response else 0
        if current_version != item.expected_version:
            conflicts.append(
                {
                    "error_uid": str(item.error_uid),
                    "expected_version": item.expected_version,
                    "current_version": current_version,
                }
            )
    if conflicts:
        raise ResponseConflictError(conflicts)

    saved = []
    touched_error_ids = []
    for item in normalized:
        error = errors[item.error_uid]
        response = existing.get(item.error_uid)
        if response is None:
            response = ShopResponse.objects.create(
                error=error,
                shop=link.shop,
                answer_code=item.answer_code,
                answer_payload=item.answer_payload,
                note=item.note,
                version_no=1,
            )
        else:
            response.answer_code = item.answer_code
            response.answer_payload = item.answer_payload
            response.note = item.note
            response.version_no += 1
            response.save(
                update_fields=["answer_code", "answer_payload", "note", "version_no", "updated_at"]
            )
        saved.append(
            {
                "error_uid": str(item.error_uid),
                "version_no": response.version_no,
                "saved_at": response.updated_at.isoformat(),
            }
        )
        if error.status in [CampaignError.Status.READY, CampaignError.Status.WAITING_SHOP]:
            touched_error_ids.append(error.pk)

    if touched_error_ids:
        CampaignError.objects.filter(pk__in=touched_error_ids).update(
            status=CampaignError.Status.SHOP_DRAFT,
            updated_at=timezone.now(),
        )
    return saved


@transaction.atomic
def submit_shop_responses(*, link, idempotency_key):
    if not idempotency_key or len(idempotency_key) > 100:
        raise ResponseValidationError("Idempotency key không hợp lệ.")

    link = ShopAccessLink.objects.select_for_update().select_related("campaign", "shop").get(pk=link.pk)
    existing_submission = ShopSubmission.objects.filter(
        campaign=link.campaign,
        shop=link.shop,
    ).first()
    if existing_submission:
        return existing_submission, True
    _assert_link_editable(link)

    errors = list(
        CampaignError.objects.select_for_update()
        .filter(campaign=link.campaign, shop=link.shop)
        .exclude(status__in=[CampaignError.Status.EXCLUDED, CampaignError.Status.CANCELLED])
    )
    responses = {
        response.error_id: response
        for response in ShopResponse.objects.select_for_update().filter(
            error_id__in=[error.pk for error in errors],
            shop=link.shop,
        )
    }
    missing = [str(error.error_uid) for error in errors if not responses.get(error.pk) or not responses[error.pk].answer_code]
    if missing:
        raise ResponseValidationError(
            f"Còn {len(missing)} dòng chưa chọn phản hồi.",
            missing_uids=missing,
        )

    now = timezone.now()
    ShopResponse.objects.filter(pk__in=[response.pk for response in responses.values()]).update(
        status=ShopResponse.Status.SUBMITTED,
        submitted_at=now,
        updated_at=now,
    )
    histories = []
    for error in errors:
        histories.append(
            CampaignStatusHistory(
                campaign=link.campaign,
                error=error,
                from_status=error.status,
                to_status=CampaignError.Status.SHOP_SUBMITTED,
                reason="PGD gửi phản hồi chính thức",
            )
        )
    CampaignStatusHistory.objects.bulk_create(histories)
    CampaignError.objects.filter(pk__in=[error.pk for error in errors]).update(
        status=CampaignError.Status.SHOP_SUBMITTED,
        updated_at=now,
    )
    submission = ShopSubmission.objects.create(
        campaign=link.campaign,
        shop=link.shop,
        idempotency_key=idempotency_key,
        response_count=len(responses),
        submitted_at=now,
    )
    submission_id = submission.pk

    def enqueue_post_submit():
        # Import lazily so the response service does not depend on Celery while
        # Django is loading models. The task only receives an internal ID; the
        # public access token must never be written to the broker.
        from app_document_campaigns.tasks import process_shop_submission

        try:
            process_shop_submission.delay(submission_id)
        except Exception:
            # The PGD submission is the primary business transaction. A broker
            # outage must not turn a committed submission into an HTTP 500.
            logger.exception(
                "Could not enqueue post-submit notification for submission_id=%s",
                submission_id,
            )

    transaction.on_commit(enqueue_post_submit)
    return submission, False
