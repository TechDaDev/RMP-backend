from rest_framework.routers import DefaultRouter

from .views import PharmacyPrescriptionRequestViewSet

router = DefaultRouter()
router.register(r"requests", PharmacyPrescriptionRequestViewSet, basename="pharmacy-requests")

urlpatterns = router.urls
