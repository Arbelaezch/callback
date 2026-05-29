from django.urls import path

from .views import (
    ChoicesView,
    ApplicationListView,
    JobSearchListView,
    JobSearchToggleView,
    JobSearchTriggerView,
    JobSearchRunLogView,
    JobSearchScheduleView,
)

urlpatterns = [
    path('choices/', ChoicesView.as_view(), name='job_choices'),
    path('applications/', ApplicationListView.as_view(), name='application_list'),
    path('searches/', JobSearchListView.as_view(), name='job_search_list'),
    path('searches/<int:pk>/toggle/', JobSearchToggleView.as_view(), name='job_search_toggle'),
    path('searches/<int:pk>/trigger/', JobSearchTriggerView.as_view(), name='job_search_trigger'),
    path('searches/<int:pk>/runs/', JobSearchRunLogView.as_view(), name='job_search_runs'),
    path('searches/<int:pk>/schedule/', JobSearchScheduleView.as_view(), name='job_search_schedule'),
]