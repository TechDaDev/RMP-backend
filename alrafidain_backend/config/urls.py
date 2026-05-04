from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(_request):
    return Response({"status": "ok", "service": "alrafidain-backend"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/health/", health_check, name="health"),
    path("api/accounts/", include("apps.accounts.urls")),
    path("api/profiles/", include("apps.profiles.urls")),
    path("api/consultations/", include("apps.consultations.urls")),
    path("api/prescriptions/", include("apps.prescriptions.urls")),
    path("api/lab-orders/", include("apps.lab_orders.urls")),
    path("api/lab-results/", include("apps.lab_orders.result_urls")),
    path("api/notifications/", include("apps.notifications.urls")),
    path("api/patient-records/", include("apps.patient_records.urls")),
    path("api/knowledge-base/", include("apps.knowledge_base.urls")),
    path("api/rag/", include("apps.rag.urls")),
]
