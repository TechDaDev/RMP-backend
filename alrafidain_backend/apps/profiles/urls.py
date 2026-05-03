from django.urls import path

from .views import (
    MyProfileView,
    UpdateDoctorProfileView,
    UpdateLaboratorianProfileView,
    UpdatePatientProfileView,
    UpdatePharmacistProfileView,
    UpdateUserProfileView,
)

urlpatterns = [
    path("me/", MyProfileView.as_view(), name="profiles-me"),
    path("me/user-profile/", UpdateUserProfileView.as_view(), name="profiles-user-profile"),
    path("me/patient/", UpdatePatientProfileView.as_view(), name="profiles-patient"),
    path("me/doctor/", UpdateDoctorProfileView.as_view(), name="profiles-doctor"),
    path("me/pharmacist/", UpdatePharmacistProfileView.as_view(), name="profiles-pharmacist"),
    path("me/laboratorian/", UpdateLaboratorianProfileView.as_view(), name="profiles-laboratorian"),
]
