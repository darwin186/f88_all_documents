import hashlib
import hmac
import json
from datetime import date

from django.db import IntegrityError, transaction
from django.db.models import F
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import (
    BusinessType, DocumentType, ExternalDocumentIntakeBatch, ExternalDocumentIntakeChunk,
    ExternalDocumentIntakeToken, FolderType, Shop,
)
from .tasks import process_document_intake_batch


MAX_RECORDS_PER_CHUNK = 1000


def _response_error(message, status=400, **extra):
    return JsonResponse({"ok": False, "error": message, **extra}, status=status)


def _payload(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("Body phải là JSON UTF-8 hợp lệ")
    if not isinstance(data, dict):
        raise ValueError("Body JSON phải là object")
    return data


def _token(request, required_scope):
    value = request.headers.get("Authorization", "")
    if value.lower().startswith("bearer "):
        value = value[7:].strip()
    else:
        value = request.headers.get("X-Document-Intake-Token", "").strip()
    if not value:
        return None
    digest = hashlib.sha256(value.encode()).hexdigest()
    token = ExternalDocumentIntakeToken.objects.filter(token_hash=digest, is_active=True).first()
    if not token or not hmac.compare_digest(token.token_hash, digest):
        return None
    if required_scope not in token.scopes:
        return None
    ExternalDocumentIntakeToken.objects.filter(pk=token.pk).update(last_used_at=timezone.now())
    return token


def _serialize(batch):
    return {
        "batch_key": batch.batch_key, "kind": batch.kind, "business_date": batch.business_date.isoformat(),
        "status": batch.status, "received_records": batch.received_records,
        "received_chunks": batch.received_chunks, "expected_records": batch.expected_records,
        "expected_chunks": batch.expected_chunks, "summary": batch.summary,
        "error_message": batch.error_message, "created_at": batch.created_at.isoformat(),
        "finalized_at": batch.finalized_at.isoformat() if batch.finalized_at else None,
        "processed_at": batch.processed_at.isoformat() if batch.processed_at else None,
    }


def _authorised(request, batch):
    scope = "documents:write" if batch.kind == batch.Kind.DOCUMENTS else "master_data:write"
    return _token(request, scope)


def _catalog_token(request):
    # A writer token can read reference data needed to prepare its own payload.
    return _token(request, "documents:write") or _token(request, "master_data:write")


@csrf_exempt
@require_http_methods(["POST"])
def create_batch(request):
    try:
        body = _payload(request)
        kind = body["kind"]
        if kind not in ExternalDocumentIntakeBatch.Kind.values:
            raise ValueError("kind chỉ nhận documents hoặc master_data")
        token = _token(request, "documents:write" if kind == "documents" else "master_data:write")
        if not token:
            return _response_error("Token không hợp lệ hoặc thiếu scope", 401)
        key = str(body["batch_key"]).strip()
        if not key or len(key) > 100:
            raise ValueError("batch_key bắt buộc, tối đa 100 ký tự")
        business_date = date.fromisoformat(str(body["business_date"]))
        defaults = {"kind": kind, "business_date": business_date, "source": str(body.get("source", "prefect"))[:100],
                    "schema_version": str(body.get("schema_version", "v1"))[:20], "expected_records": body.get("expected_records"),
                    "expected_chunks": body.get("expected_chunks"), "token": token}
        with transaction.atomic():
            batch, created = ExternalDocumentIntakeBatch.objects.get_or_create(batch_key=key, defaults=defaults)
            if not created and (batch.kind != kind or batch.business_date != business_date):
                return _response_error("batch_key đã tồn tại với kind hoặc business_date khác", 409)
        return JsonResponse({"ok": True, "created": created, "batch": _serialize(batch)}, status=201 if created else 200)
    except (KeyError, TypeError, ValueError) as exc:
        return _response_error(str(exc))


@csrf_exempt
@require_http_methods(["POST"])
def upload_chunk(request, batch_key):
    try:
        body = _payload(request)
        batch = ExternalDocumentIntakeBatch.objects.get(batch_key=batch_key)
        if not _authorised(request, batch):
            return _response_error("Token không hợp lệ hoặc thiếu scope", 401)
        if batch.status not in {batch.Status.CREATED, batch.Status.UPLOADING}:
            return _response_error("Batch đã finalize hoặc đang xử lý", 409, status_value=batch.status)
        chunk_no = int(body["chunk_no"])
        records = body["records"]
        if chunk_no < 1 or not isinstance(records, list) or not records or len(records) > MAX_RECORDS_PER_CHUNK:
            raise ValueError(f"chunk_no >= 1; records phải có 1..{MAX_RECORDS_PER_CHUNK} phần tử")
        canonical = json.dumps(records, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
        payload_hash = hashlib.sha256(canonical).hexdigest()
        try:
            with transaction.atomic():
                chunk = ExternalDocumentIntakeChunk.objects.create(batch=batch, chunk_no=chunk_no, records=records,
                                                                    record_count=len(records), payload_hash=payload_hash)
                ExternalDocumentIntakeBatch.objects.filter(pk=batch.pk).update(status=batch.Status.UPLOADING,
                    received_records=F("received_records") + len(records), received_chunks=F("received_chunks") + 1)
        except IntegrityError:
            chunk = ExternalDocumentIntakeChunk.objects.get(batch=batch, chunk_no=chunk_no)
            if not hmac.compare_digest(chunk.payload_hash, payload_hash):
                return _response_error("chunk_no đã tồn tại nhưng nội dung khác", 409)
            return JsonResponse({"ok": True, "idempotent": True, "chunk_no": chunk_no})
        return JsonResponse({"ok": True, "idempotent": False, "chunk_no": chunk.chunk_no}, status=201)
    except ExternalDocumentIntakeBatch.DoesNotExist:
        return _response_error("Không tìm thấy batch", 404)
    except (KeyError, TypeError, ValueError) as exc:
        return _response_error(str(exc))


@csrf_exempt
@require_http_methods(["POST"])
def finalize_batch(request, batch_key):
    try:
        batch = ExternalDocumentIntakeBatch.objects.get(batch_key=batch_key)
        if not _authorised(request, batch):
            return _response_error("Token không hợp lệ hoặc thiếu scope", 401)
        if batch.status in {batch.Status.COMPLETED, batch.Status.COMPLETED_WITH_REJECTIONS, batch.Status.PROCESSING}:
            return JsonResponse({"ok": True, "idempotent": True, "batch": _serialize(batch)}, status=202)
        if batch.expected_chunks is not None and batch.received_chunks != batch.expected_chunks:
            return _response_error("Thiếu chunk so với expected_chunks", 409, received_chunks=batch.received_chunks)
        if batch.expected_records is not None and batch.received_records != batch.expected_records:
            return _response_error("Số record không khớp expected_records", 409, received_records=batch.received_records)
        batch.finalized_at = timezone.now()
        batch.status = batch.Status.PROCESSING
        batch.save(update_fields=["finalized_at", "status", "updated_at"])
        result = process_document_intake_batch.delay(batch.batch_key)
        return JsonResponse({"ok": True, "task_id": result.id, "batch": _serialize(batch)}, status=202)
    except ExternalDocumentIntakeBatch.DoesNotExist:
        return _response_error("Không tìm thấy batch", 404)


@require_http_methods(["GET"])
def batch_status(request, batch_key):
    try:
        batch = ExternalDocumentIntakeBatch.objects.get(batch_key=batch_key)
        if not _authorised(request, batch):
            return _response_error("Token không hợp lệ hoặc thiếu scope", 401)
        return JsonResponse({"ok": True, "batch": _serialize(batch)})
    except ExternalDocumentIntakeBatch.DoesNotExist:
        return _response_error("Không tìm thấy batch", 404)


@require_http_methods(["GET"])
def batch_rejections(request, batch_key):
    try:
        batch = ExternalDocumentIntakeBatch.objects.get(batch_key=batch_key)
        if not _authorised(request, batch):
            return _response_error("Token không hợp lệ hoặc thiếu scope", 401)
        try:
            limit = min(max(int(request.GET.get("limit", 200)), 1), 1000)
            offset = max(int(request.GET.get("offset", 0)), 0)
        except ValueError:
            return _response_error("limit và offset phải là số")
        qs = batch.rejections.order_by("row_no", "rejection_id")
        rows = list(qs[offset:offset + limit])
        return JsonResponse({"ok": True, "count": qs.count(), "items": [{
            "row_no": x.row_no, "source_record_id": x.source_record_id, "error_code": x.error_code,
            "message": x.message, "raw_record": x.raw_record,
        } for x in rows]})
    except ExternalDocumentIntakeBatch.DoesNotExist:
        return _response_error("Không tìm thấy batch", 404)


@require_http_methods(["GET"])
def catalog(request):
    """Reference data for the external cleaner; no internal primary keys exposed."""
    if not _catalog_token(request):
        return _response_error("Token không hợp lệ hoặc thiếu scope", 401)
    return JsonResponse({
        "ok": True,
        # Legacy parity: maintain document data 3.py reads every reference row.
        # In particular, CIMB folder type code 2 can be inactive yet must still
        # be accepted for historical/source transactions.
        "folder_types": list(FolderType.objects.all().values("folder_type_id", "folder_type_code", "folder_type_name")),
        "document_types": list(DocumentType.objects.all().values("document_type_id", "document_type_code", "document_type_name")),
        "business_types": list(BusinessType.objects.all().values(
            "business_type_id", "business_type_code", "business_type_name", "action_code", "need_action_code"
        )),
        "shops": list(Shop.objects.filter(for_borrow_only=False).values(
            "shop_code", "shop_name", "shop_closed_date", "manager_id", "region_id"
        )),
    })
