import os
from celery import Celery

# Установка переменной окружения для настроек Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school_project.settings')

app = Celery('school_project')

# Использование строки здесь означает, что воркер не должен сериализовать
# объект конфигурации для дочерних процессов.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Загрузка модулей задач из всех зарегистрированных приложений Django.
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')