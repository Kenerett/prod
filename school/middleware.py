import time
import json
import random
import logging
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)

SENSITIVE_FIELDS = {'password', 'password1', 'password2', 'csrfmiddlewaretoken', 'token'}
SKIP_PATHS = ('/static/', '/media/', '/favicon.ico')
ANONYMOUS_SAMPLE_RATE = 0.1  # Log 10% of anonymous requests


class RequestLoggerMiddleware(MiddlewareMixin):
    def process_request(self, request):
        for prefix in SKIP_PATHS:
            if request.path.startswith(prefix):
                return None

        # Sample anonymous traffic to avoid unbounded table growth
        is_auth = request.user.is_authenticated
        if not is_auth and random.random() > ANONYMOUS_SAMPLE_RATE:
            return None

        ip = self._get_client_ip(request)
        data = None

        if request.method in ('POST', 'PUT', 'PATCH'):
            try:
                if request.content_type == 'application/json':
                    raw = json.loads(request.body.decode('utf-8'))
                    data = {k: ('***' if k.lower() in SENSITIVE_FIELDS else v) for k, v in raw.items()}
                else:
                    data = {k: ('***' if k.lower() in SENSITIVE_FIELDS else v) for k, v in request.POST.items()}
            except Exception:
                data = None

        from .models import RequestLog
        RequestLog.objects.create(
            user=request.user if is_auth else None,
            ip_address=ip,
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            referer=request.META.get('HTTP_REFERER', ''),
            url=request.get_full_path(),
            method=request.method,
            is_authenticated=is_auth,
            session_key=request.session.session_key,
            data=data,
        )
        return None

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')
