from django.urls import re_path

from sextant import views

urlpatterns = [
    re_path(r"^$", views.IndexView.as_view(), name="index"),
    re_path(r"^stream/$", views.stream, name="stream"),
]
