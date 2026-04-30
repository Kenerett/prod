from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import render
from school.models import RequestLog

def analytics_view(request):
    if not request.user.is_staff:
        return admin.site.login(request)
        
    # Получаем статистику по ролям
    role_stats_today = RequestLog.get_detailed_role_stats('today')
    role_stats_week = RequestLog.get_detailed_role_stats('week')
    role_stats_month = RequestLog.get_detailed_role_stats('month')
        
    context = {
        'visits_today': RequestLog.get_visits_today(),
        'visits_week': RequestLog.get_visits_this_week(),
        'visits_month': RequestLog.get_visits_this_month(),
        'current_users': RequestLog.get_current_users(),
        'current_guests': RequestLog.get_current_guests(),
        'total_visits': RequestLog.objects.count(),
        'role_stats_today': role_stats_today,
        'role_stats_week': role_stats_week,
        'role_stats_month': role_stats_month,
    }
    return render(request, 'admin/analytics.html', context)

urlpatterns = [
    # URL для приложения evaluation - должно быть выше admin
    path('evaluation/', include('evaluation.urls')),
    
    # Аналитика админки
    path('suasdper-secrasdet-ad12min-pasdnel-7x9q2/analytics/', analytics_view, name='admin_analytics'),
    
    # Админка Django
    path('suasdper-secrasdet-ad12min-pasdnel-7x9q2/', admin.site.urls),
    
    # Основные URL приложения school
    path('', include('school.urls')),
    
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)