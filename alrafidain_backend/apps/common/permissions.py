from rest_framework.permissions import BasePermission

from apps.audit.services import record_security_event
from apps.common.policies import ClinicalAccessPolicy, RoleAccessPolicy
from apps.common.staff_access import has_staff_capability


class IsVerifiedDoctor(BasePermission):
    def has_permission(self, request, view):
        return RoleAccessPolicy.is_verified_doctor(request.user)


class IsVerifiedPharmacist(BasePermission):
    def has_permission(self, request, view):
        return RoleAccessPolicy.is_verified_pharmacist(request.user)


class IsVerifiedLaboratorian(BasePermission):
    def has_permission(self, request, view):
        return RoleAccessPolicy.is_verified_laboratorian(request.user)


class IsPatientOwner(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        patient_id = getattr(obj, "patient_id", None)
        if patient_id is None and hasattr(obj, "medical_record"):
            patient_id = obj.medical_record.patient_id
        return patient_id == request.user.id


class CanAccessConsultation(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        return ClinicalAccessPolicy.can_user_access_consultation(request.user, obj)


class CanAccessPrescription(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        return ClinicalAccessPolicy.can_user_access_prescription(request.user, obj)


class CanAccessLabOrder(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        return ClinicalAccessPolicy.can_user_access_lab_order(request.user, obj)


class CanAccessLabResult(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        return ClinicalAccessPolicy.can_user_access_lab_result(request.user, obj)


class CanAccessPatientRecord(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        return ClinicalAccessPolicy.can_user_access_patient_record(request.user, obj)


class CanAccessKnowledgeBase(BasePermission):
    def has_permission(self, request, view):
        return has_staff_capability(request.user, "manage_knowledge_base")


class CanExportRagDataset(BasePermission):
    def has_permission(self, request, view):
        allowed = has_staff_capability(request.user, "export_datasets")
        if not allowed and getattr(request, "user", None) and request.user.is_authenticated:
            record_security_event(
                actor=request.user,
                action="rag_dataset_export_access_denied",
                request=request,
                metadata={"reason_code": "policy_denied"},
            )
        return allowed


class CanApproveProfessionals(BasePermission):
    def has_permission(self, request, view):
        return has_staff_capability(request.user, "approve_professionals")
