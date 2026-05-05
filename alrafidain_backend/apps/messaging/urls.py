from django.urls import path

from .views import (
    ConsultationMarkMessagesReadView,
    ConsultationMessageListView,
)

urlpatterns = [
    path(
        "<uuid:consultation_id>/messages/",
        ConsultationMessageListView.as_view(),
        name="consultation-messages-list-create",
    ),
    path(
        "<uuid:consultation_id>/messages/mark-read/",
        ConsultationMarkMessagesReadView.as_view(),
        name="consultation-messages-mark-read",
    ),
]
