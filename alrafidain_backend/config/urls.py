from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.common.health import health_deps, health_live, health_ready

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/health/", health_live, name="health"),
    path("api/health/live/", health_live, name="health-live"),
    path("api/health/ready/", health_ready, name="health-ready"),
    path("api/health/deps/", health_deps, name="health-deps"),
    path("api/accounts/", include("apps.accounts.urls")),
    path("api/admin/", include("apps.profiles.admin_urls")),
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
