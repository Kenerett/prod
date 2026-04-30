from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.db.models import Avg, Count
from school.models import CustomUser, TeacherAssignment
from evaluation.models import Evaluation

class Command(BaseCommand):
    help = 'Отправляет сводные результаты оценок всем преподавателям'

    def add_arguments(self, parser):
        parser.add_argument(
            '--semester-id',
            type=int,
            help='ID семестра для отправки результатов (по умолчанию все)',
        )

    def handle(self, *args, **options):
        # Получаем всех преподавателей
        teachers = CustomUser.objects.filter(role='teacher')
        
        sent_count = 0
        error_count = 0
        
        for teacher in teachers:
            try:
                # Получаем все оценки для этого преподавателя
                evaluations_query = Evaluation.objects.filter(
                    teacher_assignment__teacher=teacher
                )
                
                # Фильтруем по семестру если указан
                if options['semester_id']:
                    evaluations_query = evaluations_query.filter(
                        teacher_assignment__semester_id=options['semester_id']
                    )
                
                evaluations = evaluations_query.select_related(
                    'student__user',
                    'teacher_assignment__subject',
                    'teacher_assignment__semester'
                )
                
                # Если есть оценки, отправляем email
                if evaluations.exists():
                    # Вычисляем средний балл
                    avg_rating = evaluations.aggregate(avg=Avg('rating'))['avg']
                    
                    # Получаем комментарии
                    comments = evaluations.exclude(comment__isnull=True).exclude(comment='')
                    
                    # Получаем уникальные предметы
                    subjects = evaluations.values_list(
                        'teacher_assignment__subject__name', flat=True
                    ).distinct()
                    
                    # Получаем количество оценок по каждому предмету
                    subject_stats = evaluations.values(
                        'teacher_assignment__subject__name'
                    ).annotate(
                        count=Count('id'),
                        avg_rating=Avg('rating')
                    )
                    
                    # Формируем сообщение
                    subject = 'Сводные результаты оценки студентов'
                    message = render_to_string('evaluation/teacher_summary_email.html', {
                        'teacher': teacher,
                        'avg_rating': avg_rating,
                        'total_evaluations': evaluations.count(),
                        'comments': comments,
                        'subjects': subjects,
                        'subject_stats': subject_stats,
                    })
                    
                    # Отправляем email
                    send_mail(
                        subject,
                        message,
                        settings.DEFAULT_FROM_EMAIL,
                        [teacher.email],
                        fail_silently=False,
                        html_message=message
                    )
                    
                    sent_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'Отправлено {teacher.get_full_name()}')
                    )
                    
            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(f'Ошибка отправки {teacher.get_full_name()}: {e}')
                )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Успешно отправлено: {sent_count}, Ошибок: {error_count}'
            )
        )