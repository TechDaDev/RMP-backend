from rest_framework.routers import DefaultRouter

from .views import PharmacyDrugInventoryViewSet

router = DefaultRouter()
router.register(r"inventory", PharmacyDrugInventoryViewSet, basename="pharmacy-inventory")

urlpatterns = router.urls
