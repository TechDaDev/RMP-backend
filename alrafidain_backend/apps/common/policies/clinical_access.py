from apps.common.choices import ConsultationStatus, LabResultStatus

from .role_access import RoleAccessPolicy


class ClinicalAccessPolicy:
    ALLOWED_DOCTOR_RECORD_STATUSES = (
        ConsultationStatus.ACCEPTED,
        ConsultationStatus.DOCTOR_RESPONDED,
        ConsultationStatus.CLOSED,
    )

    @classmethod
    def can_doctor_access_patient(cls, user, patient) -> bool:
        if not RoleAccessPolicy.is_verified_doctor(user):
            return False
        if not RoleAccessPolicy.is_patient(patient):
            return False

        from apps.consultations.models import Consultation

        return Consultation.objects.filter(
            patient=patient,
            assigned_doctor=user,
            status__in=cls.ALLOWED_DOCTOR_RECORD_STATUSES,
        ).exists()

    @staticmethod
    def can_user_access_consultation(user, consultation) -> bool:
        if not user or not user.is_authenticated:
            return False
        return user.id in [consultation.patient_id, consultation.assigned_doctor_id]

    @classmethod
    def can_user_access_prescription(cls, user, prescription) -> bool:
        if not user or not user.is_authenticated:
            return False
        if RoleAccessPolicy.is_admin_or_staff(user):
            return True
        if RoleAccessPolicy.is_patient(user):
            return prescription.patient_id == user.id
        if RoleAccessPolicy.is_doctor(user):
            return prescription.doctor_id == user.id
        return RoleAccessPolicy.is_verified_pharmacist(user)

    @classmethod
    def can_user_access_lab_order(cls, user, lab_order) -> bool:
        if not user or not user.is_authenticated:
            return False
        if RoleAccessPolicy.is_admin_or_staff(user):
            return True
        if RoleAccessPolicy.is_patient(user):
            return lab_order.patient_id == user.id
        if RoleAccessPolicy.is_doctor(user):
            return lab_order.doctor_id == user.id
        return RoleAccessPolicy.is_verified_laboratorian(user)

    @classmethod
    def can_user_access_lab_result(cls, user, lab_result) -> bool:
        if not user or not user.is_authenticated:
            return False
        if RoleAccessPolicy.is_admin_or_staff(user):
            return True
        if RoleAccessPolicy.is_patient(user):
            return (
                lab_result.patient_id == user.id and lab_result.status == LabResultStatus.RELEASED
            )
        if RoleAccessPolicy.is_doctor(user):
            return lab_result.doctor_id == user.id
        if RoleAccessPolicy.is_laboratorian(user):
            return lab_result.laboratorian_id == user.id
        return False

    @classmethod
    def can_user_access_patient_record(cls, user, record) -> bool:
        if not user or not user.is_authenticated:
            return False
        if RoleAccessPolicy.is_admin_or_staff(user):
            return True

        patient = getattr(record, "patient", None)
        if patient is None and hasattr(record, "medical_record"):
            patient = record.medical_record.patient

        if patient is None:
            return False

        if RoleAccessPolicy.is_patient(user):
            return patient.id == user.id
        if RoleAccessPolicy.is_doctor(user):
            return cls.can_doctor_access_patient(user, patient)
        return False
