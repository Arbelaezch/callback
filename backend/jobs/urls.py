from django.urls import path

from .views import ChoicesView

urlpatterns = [
    path('choices/', ChoicesView.as_view(), name='job_choices'),
]