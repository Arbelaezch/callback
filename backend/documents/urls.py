from django.urls import path

from .views import (
    ContextSourceDetailView,
    ContextSourceListView,
    GeneratedDocumentView,
    GenerateView,
    JobPostingDetailView,
    JobPostingListView,
    ResumeParseView,
)

urlpatterns = [
    path('resumes/<int:resume_id>/parse/', ResumeParseView.as_view(), name='resume-parse'),
    path('sources/', ContextSourceListView.as_view(), name='source-list'),
    path('sources/<int:source_id>/', ContextSourceDetailView.as_view(), name='source-detail'),
    path('jobs/', JobPostingListView.as_view(), name='job-list'),
    path('jobs/<int:job_id>/', JobPostingDetailView.as_view(), name='job-detail'),
    path('jobs/<int:job_id>/generate/', GenerateView.as_view(), name='job-generate'),
    path('documents/<int:document_id>/', GeneratedDocumentView.as_view(), name='document-detail'),
]
