from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.audit.services import create_audit_log
from apps.common.choices import UserType
from apps.common.responses import success_response

from .models import (
    DoctorProfile,
    LaboratorianProfile,
    PatientProfile,
    PharmacistProfile,
    UserProfile,
)
from .serializers import (
    DoctorProfileSerializer,
    FullProfileSerializer,
    LaboratorianProfileSerializer,
    PatientProfileSerializer,
    PharmacistProfileSerializer,
    UserProfileSerializer,
)


@extend_schema(tags=["Profiles"])
class MyProfileView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = []

    @extend_schema(
        summary="Get full profile",
        description="Returns the full profile with completion and verification info.",
    )
    def get(self, request):
        return success_response(data=FullProfileSerializer(request.user).data)


@extend_schema(tags=["Profiles"])
class UpdateUserProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserProfileSerializer
    http_method_names = ["get", "patch"]

    def get_object(self):
        return get_object_or_404(UserProfile, user=self.request.user)

    def perform_update(self, serializer):
        instance = serializer.save()
        create_audit_log(
            actor=self.request.user,
            action="user_profile_updated",
            target=instance,
            request=self.request,
        )


@extend_schema(tags=["Profiles"])
class UpdatePatientProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PatientProfileSerializer
    http_method_names = ["get", "patch"]

    def get_object(self):
        user = self.request.user
        if user.user_type != UserType.PATIENT:
            raise PermissionDenied("Only patients can access this profile.")
        return get_object_or_404(PatientProfile, user=user)

    def perform_update(self, serializer):
        instance = serializer.save()
        create_audit_log(
            actor=self.request.user,
            action="patient_profile_updated",
            target=instance,
            request=self.request,
        )


@extend_schema(tags=["Profiles"])
class UpdateDoctorProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = DoctorProfileSerializer
    http_method_names = ["get", "patch"]

    def get_object(self):
        user = self.request.user
        if user.user_type != UserType.DOCTOR:
            raise PermissionDenied("Only doctors can access this profile.")
        return get_object_or_404(DoctorProfile, user=user)

    def perform_update(self, serializer):
        instance = serializer.save()
        create_audit_log(
            actor=self.request.user,
            action="doctor_profile_updated",
            target=instance,
            request=self.request,
        )


@extend_schema(tags=["Profiles"])
class UpdatePharmacistProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PharmacistProfileSerializer
    http_method_names = ["get", "patch"]

    def get_object(self):
        user = self.request.user
        if user.user_type != UserType.PHARMACIST:
            raise PermissionDenied("Only pharmacists can access this profile.")
        return get_object_or_404(PharmacistProfile, user=user)

    def perform_update(self, serializer):
        instance = serializer.save()
        create_audit_log(
            actor=self.request.user,
            action="pharmacist_profile_updated",
            target=instance,
            request=self.request,
        )


@extend_schema(tags=["Profiles"])
class UpdateLaboratorianProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LaboratorianProfileSerializer
    http_method_names = ["get", "patch"]

    def get_object(self):
        user = self.request.user
        if user.user_type != UserType.LABORATORIAN:
            raise PermissionDenied("Only laboratorians can access this profile.")
        return get_object_or_404(LaboratorianProfile, user=user)

    def perform_update(self, serializer):
        instance = serializer.save()
        create_audit_log(
            actor=self.request.user,
            action="laboratorian_profile_updated",
            target=instance,
            request=self.request,
        )
