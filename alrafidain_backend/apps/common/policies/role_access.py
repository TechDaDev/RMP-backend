from apps.common.choices import UserType, VerificationStatus


class RoleAccessPolicy:
    @staticmethod
    def is_patient(user) -> bool:
        return bool(user and user.is_authenticated and user.user_type == UserType.PATIENT)

    @staticmethod
    def is_doctor(user) -> bool:
        return bool(user and user.is_authenticated and user.user_type == UserType.DOCTOR)

    @staticmethod
    def is_pharmacist(user) -> bool:
        return bool(user and user.is_authenticated and user.user_type == UserType.PHARMACIST)

    @staticmethod
    def is_laboratorian(user) -> bool:
        return bool(user and user.is_authenticated and user.user_type == UserType.LABORATORIAN)

    @staticmethod
    def is_admin_or_staff(user) -> bool:
        return bool(
            user
            and user.is_authenticated
            and (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))
        )

    @classmethod
    def is_verified_doctor(cls, user) -> bool:
        if not cls.is_doctor(user):
            return False
        try:
            return user.doctor_profile.verification_status == VerificationStatus.APPROVED
        except Exception:
            return False

    @classmethod
    def is_verified_pharmacist(cls, user) -> bool:
        if not cls.is_pharmacist(user):
            return False
        try:
            return user.pharmacist_profile.verification_status == VerificationStatus.APPROVED
        except Exception:
            return False

    @classmethod
    def is_verified_laboratorian(cls, user) -> bool:
        if not cls.is_laboratorian(user):
            return False
        try:
            return user.laboratorian_profile.verification_status == VerificationStatus.APPROVED
        except Exception:
            return False
