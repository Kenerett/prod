import logging
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import redirect, render
from school.models import RequestLog

logger = logging.getLogger(__name__)


@login_required
def analytics_dashboard(request):
    if not request.user.is_superuser:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')

    today_stats = RequestLog.get_analytics_summary('today')
    week_stats = RequestLog.get_analytics_summary('week')
    month_stats = RequestLog.get_analytics_summary('month')

    return render(request, 'analytics/dashboard.html', {
        'today': today_stats,
        'week': week_stats,
        'month': month_stats,
    })
