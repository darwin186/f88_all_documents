"""Admin-only shop catalog. Uses the existing shop and manager master tables."""
import json
import hashlib
import secrets
import uuid
from django import forms
from functools import wraps

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.db import transaction, IntegrityError
from django.db.models import Q, Count
from django.http import HttpResponseForbidden, JsonResponse, FileResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.middleware.csrf import CsrfViewMiddleware
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import Manager, Shop, ExternalDocumentIntakeToken, CollateralRegistrationApiToken, ShopCatalogJob
from .utils import get_user_context

SHOP_READ = "master_data:shops:read"
SHOP_WRITE = "master_data:shops:write"


def catalog_auth(view):
    @csrf_exempt
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        authorization = request.headers.get("Authorization", "")
        if authorization:
            if not authorization.lower().startswith("bearer "):
                return JsonResponse({"error": "invalid_token"}, status=401)
            raw = authorization[7:].strip()
            token = ExternalDocumentIntakeToken.objects.select_related("created_by").filter(token_hash=hashlib.sha256(raw.encode()).hexdigest(), is_active=True).first()
            if not token or not token.created_by or not token.created_by.is_active:
                return JsonResponse({"error": "invalid_token"}, status=401)
            required = SHOP_WRITE if request.method == "PATCH" else SHOP_READ
            if required not in token.scopes:
                return JsonResponse({"error": "insufficient_scope", "required_scope": required}, status=403)
            user = token.created_by
            if not (user.is_superuser or user.groups.filter(name="admin").exists()):
                return JsonResponse({"error": "token_owner_not_admin"}, status=403)
            request.user = user
            request.master_data_token = token
            ExternalDocumentIntakeToken.objects.filter(pk=token.pk).update(last_used_at=timezone.now())
        else:
            denied = CsrfViewMiddleware(lambda r: None).process_view(request, lambda r: None, (), {})
            if denied:
                return denied
        return admin_only(view)(request, *args, **kwargs)
    return wrapped


def admin_only(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "authentication_required"}, status=401)
        if not (request.user.is_superuser or request.user.groups.filter(name="admin").exists()):
            if request.path.startswith("/api/"):
                return JsonResponse({"error": "admin_required"}, status=403)
            return HttpResponseForbidden("Chỉ admin được truy cập Master Data.")
        return view(request, *args, **kwargs)
    return wrapped


def local_today():
    now = timezone.now()
    return (timezone.localtime(now) if timezone.is_aware(now) else now).date()


def shop_queryset():
    return Shop.objects.select_related("manager_id__areaManager", "manager_id__regionManager").order_by("shop_code", "shop_id")


def serialize(shop):
    manager = shop.manager_id
    area = manager.areaManager
    region = manager.regionManager
    today = local_today()
    return {
        "shop_id": shop.pk, "shop_code": shop.shop_code, "shop_name": shop.shop_name,
        "shop_email": shop.shop_email or "", "is_shop_active": shop.is_shop_active,
        "shop_closed_date": shop.shop_closed_date.isoformat() if shop.shop_closed_date else None,
        "manager_id": manager.pk,
        "orgchart": {
            "manager_code": manager.manager_code,
            "is_current": manager.is_valid and (not manager.valid_from or manager.valid_from <= today) and (not manager.valid_to or manager.valid_to >= today),
            "area_manager": {"name": area.areaManager_name if area else manager.qlkv_name, "email": (area.areaManager_email if area else manager.qlkv_email) or "", "is_active": area.is_active if area else None},
            "region_manager": {"name": region.regionManager_name if region else manager.qlv_name, "email": (region.regionManager_email if region else manager.qlv_email) or "", "is_active": region.is_active if region else None},
        },
    }


def filtered(request):
    queryset = shop_queryset()
    query = request.GET.get("q", "").strip()
    if query:
        condition = Q(shop_name__icontains=query) | Q(shop_email__icontains=query)
        if query.isdigit():
            condition |= Q(shop_code=int(query))
        queryset = queryset.filter(condition)
    active = request.GET.get("active", "")
    if active in ("true", "false"):
        queryset = queryset.filter(is_shop_active=active == "true")
    return queryset


@admin_only
@require_http_methods(["GET"])
def catalog_page(request):
    page = Paginator(filtered(request), 30).get_page(request.GET.get("page"))
    today = local_today()
    managers = Manager.objects.filter(is_valid=True).filter(Q(valid_from__isnull=True) | Q(valid_from__lte=today)).filter(Q(valid_to__isnull=True) | Q(valid_to__gte=today)).select_related("areaManager", "regionManager").order_by("manager_code")
    return render(request, "app_documents/master_data.html", {
        **get_user_context(request.user),
        "shops": [serialize(shop) for shop in page], "page": page, "managers": managers,
        "q": request.GET.get("q", ""), "active": request.GET.get("active", ""),
        "total": Shop.objects.count(), "active_count": Shop.objects.filter(is_shop_active=True).count(),
        "jobs": [job for kind in ("export", "import") if (job := ShopCatalogJob.objects.filter(kind=kind).order_by("-created_at").values("id", "kind", "status", "progress", "message", "summary").first())],
    })


@catalog_auth
@require_http_methods(["GET"])
def shops_api(request):
    page = Paginator(filtered(request), 100).get_page(request.GET.get("page"))
    return JsonResponse({"count": page.paginator.count, "page": page.number, "pages": page.paginator.num_pages, "results": [serialize(shop) for shop in page]})


@catalog_auth
@require_http_methods(["GET", "PATCH"])
def shop_api(request, shop_id):
    if request.method == "GET":
        return JsonResponse(serialize(get_object_or_404(shop_queryset(), pk=shop_id)))
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict) or not data or set(data) - {"shop_email", "is_shop_active", "manager_id"}:
            raise ValueError("Chỉ cho phép shop_email, is_shop_active, manager_id.")
        if "shop_email" in data:
            if not isinstance(data["shop_email"], str):
                raise ValueError("Email phải là chuỗi; dùng chuỗi trống để xóa email.")
            data["shop_email"] = data["shop_email"].strip()
            if len(data["shop_email"]) > 100:
                raise ValueError("Email tối đa 100 ký tự.")
            if data["shop_email"]:
                validate_email(data["shop_email"])
        if "is_shop_active" in data and type(data["is_shop_active"]) is not bool:
            raise ValueError("is_shop_active phải là true hoặc false.")
        manager = None
        if "manager_id" in data:
            if type(data["manager_id"]) is not int:
                raise ValueError("manager_id phải là số nguyên.")
            manager = Manager.objects.filter(pk=data["manager_id"], is_valid=True).first()
            today = local_today()
            if not manager or (manager.valid_from and manager.valid_from > today) or (manager.valid_to and manager.valid_to < today):
                raise ValueError("Bộ quản lý không tồn tại hoặc đã hết hiệu lực.")
    except (ValueError, ValidationError, UnicodeDecodeError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    with transaction.atomic():
        shop = get_object_or_404(Shop.objects.select_for_update(), pk=shop_id)
        before = {key: getattr(shop, key) if key != "manager_id" else shop.manager_id_id for key in data}
        if "shop_email" in data:
            shop.shop_email = data["shop_email"]
        if "is_shop_active" in data:
            if shop.is_shop_active != data["is_shop_active"]:
                shop.shop_closed_date = None if data["is_shop_active"] else local_today()
            shop.is_shop_active = data["is_shop_active"]
        if manager:
            shop.manager_id = manager
        shop.save(update_fields=[("manager_id" if key == "manager_id" else key) for key in data] + (["shop_closed_date"] if "is_shop_active" in data else []))
        LogEntry.objects.log_action(user_id=request.user.pk, content_type_id=ContentType.objects.get_for_model(Shop).pk, object_id=shop.pk, object_repr=str(shop), action_flag=CHANGE, change_message=json.dumps({"source": "master_data", "token_id": getattr(getattr(request, "master_data_token", None), "pk", None), "before": before, "after": data}, ensure_ascii=False))
    return JsonResponse(serialize(shop_queryset().get(pk=shop_id)))


@admin_only
@require_http_methods(["GET"])
def api_docs(request):
    return render(request, "app_documents/master_data_api.html", get_user_context(request.user))


@admin_only
@require_http_methods(["GET"])
def tokens_page(request):
    response = render(request, "app_documents/master_data_tokens.html", {
        **get_user_context(request.user),
        "integration_tokens": ExternalDocumentIntakeToken.objects.select_related("created_by").order_by("-created_at"),
        "gddb_tokens": CollateralRegistrationApiToken.objects.select_related("owner").order_by("-created_at"),
        "owners": get_user_model().objects.filter(is_active=True).order_by("username") if request.user.is_superuser else [],
        "new_token": request.session.pop("master_data_new_token", None) or request.session.pop("document_intake_new_token", None) or request.session.pop("gddb_new_api_token", None),
    })
    response["Cache-Control"] = "no-store"
    response["Referrer-Policy"] = "no-referrer"
    return response


@admin_only
@require_http_methods(["GET", "POST"])
def response_options_page(request):
    from app_document_campaigns.models import ShopResponseOption
    class OptionForm(forms.ModelForm):
        class Meta:
            model = ShopResponseOption
            fields = ["label", "description", "sort_order", "is_active"]
            labels = {"label": "Tên phản hồi", "description": "Mô tả", "sort_order": "Thứ tự", "is_active": "Đang sử dụng"}
            widgets = {"description": forms.Textarea(attrs={"rows": 3})}
    selected_id = request.POST.get("option_id") if request.method == "POST" else request.GET.get("edit")
    instance = None
    if selected_id:
        if not selected_id.isdigit():
            return HttpResponseForbidden("Mã lựa chọn không hợp lệ.")
        instance = get_object_or_404(ShopResponseOption, pk=int(selected_id))
    form = OptionForm(request.POST if request.method == "POST" else None, instance=instance)
    if request.method == "POST" and form.is_valid():
        option = form.save(commit=False)
        if not option.code:
            option.code = "RESP-" + uuid.uuid4().hex[:12].upper()
        option.save()
        messages.success(request, "Đã lưu danh mục. Các chiến dịch đã có giữ nguyên tên và mã phản hồi đã áp dụng.")
        return redirect("master_data_response_options")
    return render(request, "app_documents/master_data_response_options.html", {**get_user_context(request.user), "form": form, "editing": instance, "options": ShopResponseOption.objects.annotate(uses=Count("campaignresponseoption"))}, status=400 if request.method == "POST" else 200)


@admin_only
@require_http_methods(["POST"])
def create_shop_token(request):
    name = request.POST.get("name", "").strip()
    scopes = set(request.POST.getlist("scopes"))
    if not name or len(name) > 100 or not scopes or scopes - {SHOP_READ, SHOP_WRITE}:
        messages.error(request, "Nhập tên tối đa 100 ký tự và chọn quyền Master Data hợp lệ.")
    elif ExternalDocumentIntakeToken.objects.filter(name=name).exists():
        messages.error(request, "Tên token đã tồn tại.")
    else:
        raw = "md_" + secrets.token_urlsafe(40)
        ExternalDocumentIntakeToken.objects.create(name=name, token_prefix=raw[:12], token_hash=hashlib.sha256(raw.encode()).hexdigest(), scopes=sorted(scopes), created_by=request.user)
        request.session["master_data_new_token"] = raw
        messages.success(request, "Đã tạo token. Sao chép ngay; token chỉ hiển thị một lần.")
    return redirect("master_data_tokens")


@admin_only
@require_http_methods(["POST"])
def queue_catalog_job(request):
    kind = request.POST.get("kind")
    if kind not in {"export", "import"}:
        return JsonResponse({"error": "Loại job không hợp lệ."}, status=400)
    upload = request.FILES.get("file")
    if kind == "import" and (not upload or not upload.name.lower().endswith(".xlsx") or upload.size > 10 * 1024 * 1024):
        return JsonResponse({"error": "Chọn file .xlsx, tối đa 10 MB."}, status=400)
    try:
        with transaction.atomic():
            job = ShopCatalogJob.objects.create(kind=kind, requested_by=request.user, message="Đang chờ worker")
    except IntegrityError:
        existing = ShopCatalogJob.objects.filter(kind=kind, status__in=["queued", "running"]).first()
        if not existing:
            return JsonResponse({"error": "Không thể tạo job. Hãy thử lại."}, status=409)
        return JsonResponse({"error": "Đang có file cùng loại được xử lý. Vui lòng chờ hoàn tất.", "id": existing.pk, "kind": kind, "status": existing.status, "progress": existing.progress, "message": existing.message}, status=409)
    try:
        if kind == "import":
            job.input_file.save(f"pgd-import-{job.pk}.xlsx", upload)
        from .tasks import process_shop_catalog_job
        process_shop_catalog_job.delay(job.pk)
    except Exception:
        job.status = "failed"
        job.message = "Không thể gửi job tới Celery. Kiểm tra Redis/worker và thử lại."
        job.save(update_fields=["status", "message", "updated_at"])
    return JsonResponse({"id": job.pk, "kind": kind, "status": job.status, "progress": job.progress, "message": job.message}, status=202)


@admin_only
@require_http_methods(["GET"])
def catalog_job_status(request, job_id):
    job = get_object_or_404(ShopCatalogJob, pk=job_id)
    now = timezone.now()
    stalled = job.status in {"queued", "running"} and (now - job.updated_at).total_seconds() > 1200
    response = JsonResponse({"id": job.pk, "kind": job.kind, "status": job.status, "progress": job.progress, "message": job.message, "summary": job.summary, "stalled": stalled, "download_url": f"/master-data/jobs/{job.pk}/download/" if job.output_file else None})
    response["Cache-Control"] = "no-store"
    return response


@admin_only
@require_http_methods(["GET"])
def catalog_job_download(request, job_id):
    job = get_object_or_404(ShopCatalogJob, pk=job_id)
    if not job.output_file or job.status not in {"succeeded", "failed"}:
        return JsonResponse({"error": "File chưa sẵn sàng."}, status=409)
    return FileResponse(job.output_file.open("rb"), as_attachment=True, filename=job.output_file.name.rsplit("/", 1)[-1], content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
