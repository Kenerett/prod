import time
import json
import logging
from django.utils.deprecation import MiddlewareMixin
from django.shortcuts import redirect
from django.urls import reverse

logger = logging.getLogger(__name__)

SENSITIVE_FIELDS = {'password', 'password1', 'password2', 'csrfmiddlewaretoken', 'token'}
SKIP_PATHS = ('/static/', '/media/', '/favicon.ico')


class RequestLoggerMiddleware(MiddlewareMixin):
    def process_request(self, request):
        for prefix in SKIP_PATHS:
            if request.path.startswith(prefix):
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
            user=request.user if request.user.is_authenticated else None,
            ip_address=ip,
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            referer=request.META.get('HTTP_REFERER', ''),
            url=request.get_full_path(),
            method=request.method,
            is_authenticated=request.user.is_authenticated,
            session_key=request.session.session_key,
            data=data,
        )
        return None

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')


class EvaluationRequiredMiddleware:
    CACHE_TTL = 300  # 5 минут

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._should_check(request):
            if self._get_cached_result(request):
                if request.path != reverse('evaluation:evaluation_form'):
                    return redirect('evaluation:evaluation_form')
        return self.get_response(request)

    def _should_check(self, request):
        if not request.user.is_authenticated:
            return False
        if getattr(request.user, 'role', None) != 'student':
            return False
        if request.path.startswith('/evaluation/'):
            return False
        if request.path in ('/logout/', '/admin/'):
            return False
        for prefix in SKIP_PATHS:
            if request.path.startswith(prefix):
                return False
        return True

    def _get_cached_result(self, request):
        import time
        now = time.time()
        if now - request.session.get('eval_check_ts', 0) > self.CACHE_TTL:
            result = self._check_needs_evaluation(request)
            request.session['eval_check_result'] = result
            request.session['eval_check_ts'] = now
            return result
        return request.session.get('eval_check_result', False)

    def _check_needs_evaluation(self, request):
        from school.models import StudentProfile, TeacherAssignment, Semester
        from evaluation.models import Evaluation, EvaluationSettings
        try:
            eval_settings = EvaluationSettings.load()
            if not eval_settings.is_active:
                return False
            student_profile = StudentProfile.objects.get(user=request.user)
            current_semester = Semester.objects.order_by('-end_date').first()
            if not current_semester:
                return False
            assignments = TeacherAssignment.objects.filter(
                group__students=student_profile,
                semester=current_semester,
            )
            completed_ids = Evaluation.objects.filter(
                student=student_profile,
                teacher_assignment__in=assignments,
            ).values_list('teacher_assignment_id', flat=True)
            return assignments.exclude(id__in=completed_ids).exists()
        except StudentProfile.DoesNotExist:
            return False