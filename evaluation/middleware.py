from django.shortcuts import redirect
from django.urls import reverse
from django.apps import apps

class EvaluationRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Проверяем, нужно ли студенту пройти оценку
        if (request.user.is_authenticated and 
            hasattr(request.user, 'role') and
            request.user.role == 'student' and 
            not request.path.startswith('/evaluation/') and
            not request.path.startswith('/admin/') and
            request.path not in ['/logout/']):
            
            try:
                # Получаем модели через apps для избежания циклических зависимостей
                StudentProfile = apps.get_model('school', 'StudentProfile')
                Semester = apps.get_model('school', 'Semester')
                TeacherAssignment = apps.get_model('school', 'TeacherAssignment')
                Evaluation = apps.get_model('evaluation', 'Evaluation')
                EvaluationSettings = apps.get_model('evaluation', 'EvaluationSettings')
                
                student_profile = StudentProfile.objects.get(user=request.user)
                current_semester = Semester.objects.last()  # Последний семестр
                
                if current_semester:
                    # Получаем все назначения преподавателей для студента в текущем семестре
                    assignments = TeacherAssignment.objects.filter(
                        group__students=student_profile,
                        semester=current_semester
                    )
                    
                    # Проверяем, есть ли незаполненные оценки
                    completed_evaluations = Evaluation.objects.filter(
                        student=student_profile,
                        teacher_assignment__in=assignments
                    ).values_list('teacher_assignment_id', flat=True)
                    
                    pending_assignments = assignments.exclude(id__in=completed_evaluations)
                    
                    # Если есть незаполненные оценки и система оценок активна
                    eval_settings = EvaluationSettings.load()
                    if pending_assignments.exists() and eval_settings.is_active:
                        # Исключаем уже находящиеся на странице оценки
                        if request.path != reverse('evaluation:evaluation_form'):
                            return redirect('evaluation:evaluation_form')
            except Exception:
                # В случае любой ошибки просто продолжаем выполнение
                pass
        
        response = self.get_response(request)
        return response