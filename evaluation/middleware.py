from django.shortcuts import redirect
from django.urls import reverse
from django.apps import apps

_EVALUATION_FORM_URL = None


class EvaluationRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (request.user.is_authenticated and
                hasattr(request.user, 'role') and
                request.user.role == 'student' and
                not request.path.startswith('/evaluation/') and
                not request.path.startswith('/admin/') and
                request.path not in ['/logout/']):

            try:
                from school.services.semester import get_current_semester
                StudentProfile = apps.get_model('school', 'StudentProfile')
                TeacherAssignment = apps.get_model('school', 'TeacherAssignment')
                Evaluation = apps.get_model('evaluation', 'Evaluation')
                EvaluationSettings = apps.get_model('evaluation', 'EvaluationSettings')

                student_profile = StudentProfile.objects.get(user=request.user)
                current_semester = get_current_semester()

                if current_semester:
                    assignments = TeacherAssignment.objects.filter(
                        group__students=student_profile,
                        semester=current_semester
                    )

                    completed_evaluations = Evaluation.objects.filter(
                        student=student_profile,
                        teacher_assignment__in=assignments
                    ).values_list('teacher_assignment_id', flat=True)

                    pending_assignments = assignments.exclude(id__in=completed_evaluations)

                    eval_settings = EvaluationSettings.load()
                    if pending_assignments.exists() and eval_settings.is_active:
                        global _EVALUATION_FORM_URL
                        if _EVALUATION_FORM_URL is None:
                            _EVALUATION_FORM_URL = reverse('evaluation:evaluation_form')
                        if request.path != _EVALUATION_FORM_URL:
                            return redirect('evaluation:evaluation_form')
            except Exception:
                pass

        response = self.get_response(request)
        return response
