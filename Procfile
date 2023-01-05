release: python manage.py makemigrations && python manage.py migrate
web: gunicorn sms.wsgi --log-file -
worker: cd tg_bot && python core.py