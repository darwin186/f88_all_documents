from django.utils import timezone

def current_time(request):
    return {'now': timezone.now()}
