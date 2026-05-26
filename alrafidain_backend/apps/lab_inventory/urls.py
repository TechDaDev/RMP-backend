from rest_framework.routers import DefaultRouter

from .views import LabTestOfferingViewSet

router = DefaultRouter()
router.register(r"inventory", LabTestOfferingViewSet, basename="lab-inventory")

urlpatterns = router.urls
