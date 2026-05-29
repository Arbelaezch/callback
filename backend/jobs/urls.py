from django.urls import path

from .views import (
    AgentView,
    ChoicesView,
    ApplicationListView,
    SearchListView,
    SearchToggleView,
    SearchTriggerView,
    SearchRunLogView,
    SearchScheduleView,
)

urlpatterns = [
    path('choices/', ChoicesView.as_view(), name='job_choices'),
    path('agent/', AgentView.as_view(), name='agent'),
    path('applications/', ApplicationListView.as_view(), name='application_list'),
    path('searches/', SearchListView.as_view(), name='search_list'),
    path('searches/<int:pk>/toggle/', SearchToggleView.as_view(), name='search_toggle'),
    path('searches/<int:pk>/trigger/', SearchTriggerView.as_view(), name='search_trigger'),
    path('searches/<int:pk>/runs/', SearchRunLogView.as_view(), name='search_runs'),
    path('searches/<int:pk>/schedule/', SearchScheduleView.as_view(), name='search_schedule'),
]