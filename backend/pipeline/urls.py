from django.urls import path

from .views import ApplicationCallbackView

urlpatterns = [
    path(
        'applications/<int:application_id>/callback/',
        ApplicationCallbackView.as_view(),
        name='application-callback',
    ),
]