from django.urls import path
from .views import ResumeDetailView, ResumePrimaryView, ResumeUploadView, UploadLimitsView

urlpatterns = [
    path('resumes/', ResumeUploadView.as_view(), name='resume_upload'),
    path('resumes/<int:resume_id>/', ResumeDetailView.as_view(), name='resume_detail'),
    path('resumes/<int:resume_id>/primary/', ResumePrimaryView.as_view(), name='resume_primary'),
    path('upload-limits/', UploadLimitsView.as_view(), name='upload_limits'),
]
