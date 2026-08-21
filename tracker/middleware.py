from datetime import timedelta

from django.shortcuts import redirect
from django.utils import timezone

from .models import Manager

IDLE_LIMIT_MINUTES = 60

# paths that don't require a manager to be logged in
EXEMPT_PATHS = [
    "/login/",
    "/admin-reset/",
    "/admin-reset/logout/",
]
EXEMPT_PREFIXES = [
    "/static/",
    "/admin/",  # Django's own built-in admin site, separate auth system
]


class ManagerSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        is_exempt = path in EXEMPT_PATHS or any(path.startswith(p) for p in EXEMPT_PREFIXES)

        if not is_exempt:
            manager_id = request.session.get("manager_id")
            manager = Manager.objects.filter(id=manager_id).first() if manager_id else None

            if not manager:
                return redirect("login")

            now = timezone.now()
            if manager.last_activity_at and now - manager.last_activity_at > timedelta(minutes=IDLE_LIMIT_MINUTES):
                manager.is_active_session = False
                manager.save()
                request.session.flush()
                return redirect("login")

            manager.last_activity_at = now
            manager.save()
            request.current_manager = manager  # available to every view from here on

        return self.get_response(request)