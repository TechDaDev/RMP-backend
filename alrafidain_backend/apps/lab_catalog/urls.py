from rest_framework.routers import DefaultRouter

from .views import LabTestViewSet

router = DefaultRouter()
router.register(r"lab-tests", LabTestViewSet, basename="catalog-lab-tests")

urlpatterns = router.urls
