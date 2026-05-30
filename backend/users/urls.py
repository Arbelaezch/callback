from django.urls import path
from .views import ResumeUploadView

urlpatterns = [
    path('resumes/', ResumeUploadView.as_view(), name='resume_upload'),
]