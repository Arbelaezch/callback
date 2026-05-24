from django.urls import path

from .views import (
    ChoicesView,
    ApplicationListView,
    JobSearchListView,
    JobSearchToggleView,
)

urlpatterns = [
    path('choices/', ChoicesView.as_view(), name='job_choices'),
    path('applications/', ApplicationListView.as_view(), name='application_list'),
    path('searches/', JobSearchListView.as_view(), name='job_search_list'),
    path('searches/<int:pk>/toggle/', JobSearchToggleView.as_view(), name='job_search_toggle'),
]