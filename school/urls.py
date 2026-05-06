from django.urls import path,include
from . import views
from .views import export_student_form, export_teacher_form ,export_schedule_teacher,export_schedule_student,ImportExcelView,faq_view
from . import views 

admin_patterns = [
    path('send-credentials/<int:user_id>/', views.send_credentials_to_user, name='send_credentials'),
    path('reset-password/<int:user_id>/', views.reset_user_password, name='reset_password'),
]

from django.http import HttpResponse

# Простая тестовая view
def home_view(request):
    return HttpResponse("<h1>Django на Railway работает!</h1><p>Сайт успешно запущен</p>")


urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),




    path('faq/', views.faq_view, name='faq'),
    # Student URLs
    path('student/', views.student_dashboard, name='student_dashboard'),
    path('student/subject/<int:tsg_id>/', views.student_subject_detail, name='student_subject_detail'),
    path('student/<int:student_id>/', views.student_detail, name='student_detail'),
    
    # Teacher URLs
    path('teacher/', views.teacher_dashboard, name='teacher_dashboard'),
    path('teacher/<int:teacher_id>/', views.teacher_detail, name='teacher_detail'),
    path('grade/<int:tsg_id>/', views.grade_students, name='grade_students'),
    
    # Admin URLs
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    
    # Group URLs
    path('group/<int:group_id>/', views.group_detail, name='group_detail'),
    
    # Excel Import URLs
    path('import_excel/', views.ImportExcelView.as_view(), name='import_excel'),

    # path('import-student-grades/', ImportStudentGradesView.as_view(), name='import_student_grades'),

   path('tutor/', views.tutor_dashboard, name='tutor_dashboard'),
    path('tutor/group/<int:group_id>/', views.tutor_group_detail, name='tutor_group_detail'),
    path('tutor/student/<int:student_id>/grades/', views.tutor_student_grades, name='tutor_student_grades'),
   



    path('tutor/create-student/', views.tutor_create_student, name='tutor_create_student'),
    path('tutor/create-group/', views.tutor_create_group, name='tutor_create_group'),
    path('tutor/group/<int:group_id>/manage-students/', views.tutor_manage_group_students, name='tutor_manage_group_students'),


    path('schedule/edit/', views.schedule_edit, name='schedule_edit'),

    path('admin-actions/', include(admin_patterns)),





    path('scheduler/', views.scheduler_dashboard, name='scheduler_dashboard'),
    path('scheduler/schedule/', views.schedule_list, name='schedule_list'),
    path('scheduler/schedule/create/', views.schedule_create, name='schedule_create'),
    path('scheduler/schedule/<int:entry_id>/update/', views.schedule_update, name='schedule_update'),
    path('scheduler/schedule/<int:entry_id>/delete/', views.schedule_delete, name='schedule_delete'),
    path('scheduler/export/student/', views.export_schedule_student, name='scheduler_export_student'),
    path('scheduler/export/teacher/', views.export_schedule_teacher, name='scheduler_export_teacher'),
    path('scheduler/schedule/group/<int:group_id>/', views.schedule_group, name='schedule_group'),
    path('export/student/', export_student_form, name='export_student_form'),
    path('export/teacher/', export_teacher_form, name='export_teacher_form'),
    path('export/student/download/', export_schedule_student, name='export_schedule_student'),
    path('export/teacher/download/', export_schedule_teacher, name='export_schedule_teacher'),



path('registration/password_reset/', views.password_reset_request, name='password_reset'),
path('registration/password_reset/done/', views.password_reset_done, name='password_reset_done'),
path('registration/reset/<uidb64>/<token>/', views.password_reset_confirm, name='password_reset_confirm'),
path('registration/reset/done/', views.password_reset_complete, name='password_reset_complete'),

]