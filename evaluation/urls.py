# evaluation/urls.py
from django.urls import path
from . import views

app_name = 'evaluation' # Убедитесь, что это есть

urlpatterns = [
    path('form/', views.evaluation_form, name='evaluation_form'),
    path('analytics/', views.analytics_dashboard, name='analytics_dashboard'),
    path('analytics/teacher/<int:teacher_id>/', views.teacher_detail, name='teacher_detail'),
    path('export/', views.export_evaluations, name='export_evaluations'),
    # path('', views.analytics_dashboard, name='index'), # Эта строка не обязательна, если у вас нет корневого пути для evaluation
]