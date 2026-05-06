import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.db.models import Avg, Count
from django.http import HttpResponse
import csv

from school.models import StudentProfile, TeacherAssignment, Semester, CustomUser
from .models import Evaluation, EvaluationSettings

logger = logging.getLogger(__name__)


@login_required
def evaluation_form(request):
    if request.user.role != 'student':
        messages.error(request, 'Доступ запрещен.')
        return redirect('dashboard')

    try:
        student_profile = StudentProfile.objects.get(user=request.user)
    except StudentProfile.DoesNotExist:
        messages.error(request, 'Профиль студента не найден.')
        return redirect('dashboard')

    current_semester = student_profile.get_current_semester()

    if not current_semester:
        messages.error(request, 'Текущий семестр не найден.')
        return redirect('student_dashboard')

    assignments = TeacherAssignment.objects.filter(
        group__students=student_profile,
        semester=current_semester
    ).select_related('teacher', 'subject')

    if not assignments.exists():
        messages.info(request, 'У вас нет предметов для оценки в текущем семестре.')
        return redirect('student_dashboard')

    completed_evaluations = Evaluation.objects.filter(
        student=student_profile,
        teacher_assignment__in=assignments
    ).select_related('teacher_assignment__teacher', 'teacher_assignment__subject')

    completed_assignment_ids = list(completed_evaluations.values_list('teacher_assignment_id', flat=True))

    pending_assignments = assignments.exclude(id__in=completed_assignment_ids)

    if not pending_assignments.exists():
        return redirect('student_dashboard')

    eval_settings = EvaluationSettings.load()
    if not eval_settings.is_active:
        messages.info(request, 'Система оценки преподавателей временно недоступна.')
        return redirect('student_dashboard')

    if request.method == 'POST':
        created_assignments = []
        errors = []

        with transaction.atomic():
            for assignment in pending_assignments:
                rating_key = f'rating_{assignment.id}'
                comment_key = f'comment_{assignment.id}'

                rating = request.POST.get(rating_key)
                comment = request.POST.get(comment_key, '').strip()

                if rating:
                    try:
                        rating = int(rating)
                        if 1 <= rating <= 10:
                            try:
                                evaluation = Evaluation.objects.create(
                                    student=student_profile,
                                    teacher_assignment=assignment,
                                    rating=rating,
                                    comment=comment or None
                                )
                                created_assignments.append(assignment)
                                request.session['eval_check_ts'] = 0
                            except Exception as e:
                                errors.append(f'Ошибка при сохранении оценки для {assignment.teacher.get_full_name()}: {str(e)}')
                        else:
                            errors.append(f'Оценка для {assignment.teacher.get_full_name()} должна быть от 1 до 10.')
                    except ValueError:
                        errors.append(f'Некорректная оценка для {assignment.teacher.get_full_name()}.')

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'evaluation/form.html', {
                'assignments': pending_assignments,
                'completed_evaluations': completed_evaluations
            })

        if created_assignments:
            try:
                send_evaluation_emails(created_assignments)
            except Exception as e:
                logger.error(f"Error sending evaluation emails: {e}")

        messages.success(request, 'Спасибо за заполнение формы оценки преподавателей!')
        return redirect('student_dashboard')

    return render(request, 'evaluation/form.html', {
        'assignments': pending_assignments,
        'completed_evaluations': completed_evaluations
    })


def send_evaluation_emails(assignments):
    """Send evaluation results to teachers"""
    try:
        teacher_assignments_dict = {}
        for assignment in assignments:
            teacher = assignment.teacher
            if teacher not in teacher_assignments_dict:
                teacher_assignments_dict[teacher] = []
            teacher_assignments_dict[teacher].append(assignment)

        for teacher, teacher_assignments in teacher_assignments_dict.items():
            try:
                evaluations = Evaluation.objects.filter(
                    teacher_assignment__in=teacher_assignments
                ).select_related('student__user', 'teacher_assignment__subject')

                avg_rating = evaluations.aggregate(avg=Avg('rating'))['avg']
                comments = evaluations.exclude(comment__isnull=True).exclude(comment='')

                if avg_rating or comments.exists():
                    subject = 'Новые результаты оценки студентов'
                    message = render_to_string('evaluation/teacher_email.html', {
                        'teacher': teacher,
                        'avg_rating': avg_rating,
                        'comments': comments,
                        'assignments': teacher_assignments
                    })

                    try:
                        send_mail(
                            subject,
                            message,
                            settings.DEFAULT_FROM_EMAIL,
                            [teacher.email],
                            fail_silently=False,
                            html_message=message
                        )
                    except Exception as e:
                        logger.error(f"Failed to send email to {teacher.email}: {e}")
            except Exception as e:
                logger.error(f"Failed to process email for teacher {teacher}: {e}")
    except Exception as e:
        logger.error(f"Failed to send evaluation emails: {e}")


@login_required
def analytics_dashboard(request):
    if not request.user.is_superuser:
        messages.error(request, 'Доступ запрещен.')
        return redirect('dashboard')

    total_evaluations = Evaluation.objects.count()
    avg_rating = Evaluation.objects.aggregate(avg=Avg('rating'))['avg']

    teacher_stats = Evaluation.objects.values(
        'teacher_assignment__teacher__id',
        'teacher_assignment__teacher__first_name',
        'teacher_assignment__teacher__last_name'
    ).annotate(
        avg_rating=Avg('rating'),
        total_evaluations=Count('id')
    ).order_by('-avg_rating')

    semester_stats = Evaluation.objects.values(
        'teacher_assignment__semester__name'
    ).annotate(
        avg_rating=Avg('rating'),
        total_evaluations=Count('id')
    ).order_by('-teacher_assignment__semester__end_date')

    top_comments = Evaluation.objects.exclude(
        comment__isnull=True
    ).exclude(
        comment=''
    ).select_related(
        'student__user',
        'teacher_assignment__teacher',
        'teacher_assignment__subject'
    ).order_by('-created_at')[:10]

    context = {
        'total_evaluations': total_evaluations,
        'avg_rating': avg_rating,
        'teacher_stats': teacher_stats,
        'semester_stats': semester_stats,
        'top_comments': top_comments,
    }

    return render(request, 'evaluation/analytics_dashboard.html', context)


@login_required
def teacher_detail(request, teacher_id):
    if not request.user.is_superuser:
        messages.error(request, 'Доступ запрещен.')
        return redirect('dashboard')

    teacher = get_object_or_404(CustomUser, id=teacher_id, role='teacher')

    evaluations = Evaluation.objects.filter(
        teacher_assignment__teacher=teacher
    ).select_related(
        'student__user',
        'teacher_assignment__subject',
        'teacher_assignment__semester'
    ).order_by('-created_at')

    avg_rating = evaluations.aggregate(avg=Avg('rating'))['avg']
    comments = evaluations.exclude(comment__isnull=True).exclude(comment='')

    subject_stats = evaluations.values(
        'teacher_assignment__subject__name'
    ).annotate(
        avg_rating=Avg('rating'),
        count=Count('id')
    )

    semester_stats = evaluations.values(
        'teacher_assignment__semester__name'
    ).annotate(
        avg_rating=Avg('rating'),
        count=Count('id')
    ).order_by('-teacher_assignment__semester__end_date')

    context = {
        'teacher': teacher,
        'evaluations': evaluations,
        'avg_rating': avg_rating,
        'comments': comments,
        'total_evaluations': evaluations.count(),
        'subject_stats': subject_stats,
        'semester_stats': semester_stats,
    }

    return render(request, 'evaluation/teacher_detail.html', context)


@login_required
def export_evaluations(request):
    if not request.user.is_superuser:
        messages.error(request, 'Доступ запрещен.')
        return redirect('dashboard')

    format = request.GET.get('format', 'csv')

    evaluations = Evaluation.objects.select_related(
        'student__user',
        'teacher_assignment__teacher',
        'teacher_assignment__subject',
        'teacher_assignment__semester'
    ).order_by('teacher_assignment__teacher__last_name', 'created_at')

    if format == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="evaluations.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Преподаватель', 'Предмет', 'Семестр', 'Студент', 'Оценка', 'Комментарий', 'Дата'
        ])

        for eval in evaluations:
            writer.writerow([
                eval.teacher_assignment.teacher.get_full_name(),
                eval.teacher_assignment.subject.name,
                eval.teacher_assignment.semester.name if eval.teacher_assignment.semester else '',
                eval.student.user.get_full_name(),
                eval.rating,
                eval.comment or '',
                eval.created_at.strftime('%Y-%m-%d %H:%M')
            ])

        return response

    messages.error(request, 'Неподдерживаемый формат.')
    return redirect('analytics_dashboard')
