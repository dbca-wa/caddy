"""
WSGI config for caddy project.
It exposes the WSGI callable as a module-level variable named ``application``.
"""
import confy
import os
from django.core.wsgi import get_wsgi_application

confy.read_environment_file('.env')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'caddy.settings')
application = get_wsgi_application()
