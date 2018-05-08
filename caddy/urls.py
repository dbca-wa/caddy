from django.urls import include, path
from .api import v1_api

urlpatterns = [
    path('api/', include(v1_api.urls)),  # All API views are defined in api.py
]
