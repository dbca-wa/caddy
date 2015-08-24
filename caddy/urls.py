from __future__ import absolute_import
from django.conf.urls import include, url
from .api import v1_api

urlpatterns = [
    url(r'^api/', include(v1_api.urls)),  # All API views are defined in api.py
]
