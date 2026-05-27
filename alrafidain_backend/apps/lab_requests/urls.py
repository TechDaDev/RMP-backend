from rest_framework.routers import DefaultRouter

from .views import LabOrderRequestViewSet

router = DefaultRouter()
router.register(r"requests", LabOrderRequestViewSet, basename="lab-requests")

urlpatterns = router.urls
