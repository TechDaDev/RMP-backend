from django.urls import path

from .admin_views import (
    AdminVerificationApproveView,
    AdminVerificationDetailView,
    AdminVerificationListView,
    AdminVerificationRejectView,
    AdminVerificationSuspendView,
)

urlpatterns = [
    path("verifications/", AdminVerificationListView.as_view(), name="admin-verifications-list"),
    path(
        "verifications/<str:role>/<uuid:pk>/",
        AdminVerificationDetailView.as_view(),
        name="admin-verifications-detail",
    ),
    path(
        "verifications/<str:role>/<uuid:pk>/approve/",
        AdminVerificationApproveView.as_view(),
        name="admin-verifications-approve",
    ),
    path(
        "verifications/<str:role>/<uuid:pk>/reject/",
        AdminVerificationRejectView.as_view(),
        name="admin-verifications-reject",
    ),
    path(
        "verifications/<str:role>/<uuid:pk>/suspend/",
        AdminVerificationSuspendView.as_view(),
        name="admin-verifications-suspend",
    ),
]
