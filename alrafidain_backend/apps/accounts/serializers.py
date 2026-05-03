import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.utils import timezone
from rest_framework import serializers

from apps.common.choices import UserType

from .models import EmailOTP, OTPPurpose

User = get_user_model()


def _generate_otp() -> str:
    return f"{random.SystemRandom().randint(0, 999999):06d}"


def _create_otp(user, purpose: str) -> EmailOTP:
    EmailOTP.objects.filter(user=user, purpose=purpose, is_used=False).update(is_used=True)
    return EmailOTP.objects.create(
        user=user,
        purpose=purpose,
        code=_generate_otp(),
        expires_at=timezone.now() + timedelta(minutes=10),
    )


def _send_activation_email(user, otp: EmailOTP) -> None:
    send_mail(
        subject="Activate your Al-Rafidain account",
        message=f"Hi {user.first_name},\n\nYour activation code is: {otp.code}\n\nIt expires in 10 minutes.",
        from_email=None,
        recipient_list=[user.email],
        fail_silently=False,
    )


def _send_password_reset_email(user, otp: EmailOTP) -> None:
    send_mail(
        subject="Reset your Al-Rafidain password",
        message=f"Hi {user.first_name},\n\nYour password reset code is: {otp.code}\n\nIt expires in 10 minutes.",
        from_email=None,
        recipient_list=[user.email],
        fail_silently=False,
    )


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "full_name", "user_type", "is_active", "date_joined"]
        read_only_fields = fields


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    user_type = serializers.ChoiceField(choices=UserType.choices)

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value.lower()

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        from apps.profiles.models import (
            DoctorProfile,
            LaboratorianProfile,
            PatientProfile,
            PharmacistProfile,
            UserProfile,
        )

        validated_data.pop("password_confirm")
        password = validated_data.pop("password")
        user = User.objects.create_user(password=password, **validated_data)

        UserProfile.objects.create(user=user)

        user_type = user.user_type
        if user_type == UserType.PATIENT:
            PatientProfile.objects.create(user=user)
            from apps.patient_records.services import get_or_create_patient_medical_record

            get_or_create_patient_medical_record(user)
        elif user_type == UserType.DOCTOR:
            DoctorProfile.objects.create(user=user)
        elif user_type == UserType.PHARMACIST:
            PharmacistProfile.objects.create(user=user)
        elif user_type == UserType.LABORATORIAN:
            LaboratorianProfile.objects.create(user=user)

        otp = _create_otp(user, OTPPurpose.ACCOUNT_ACTIVATION)
        _send_activation_email(user, otp)

        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs["email"].lower()
        password = attrs["password"]

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid credentials.")

        if not user.check_password(password):
            raise serializers.ValidationError("Invalid credentials.")

        if not user.is_active:
            raise serializers.ValidationError(
                "Account is not activated. Please check your email for the OTP."
            )

        attrs["user"] = user
        return attrs


class ActivateAccountSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=6, min_length=6)

    def validate(self, attrs):
        email = attrs["email"].lower()
        code = attrs["code"]

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError("User not found.")

        otp = (
            EmailOTP.objects.filter(
                user=user,
                purpose=OTPPurpose.ACCOUNT_ACTIVATION,
                code=code,
                is_used=False,
            )
            .order_by("-created_at")
            .first()
        )

        if not otp:
            raise serializers.ValidationError("Invalid or already used OTP.")
        if otp.is_expired():
            raise serializers.ValidationError("OTP has expired. Request a new one.")

        attrs["user"] = user
        attrs["otp"] = otp
        return attrs


class ResendActivationOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        value = value.lower()
        user = User.objects.filter(email=value, is_active=False).first()
        self.context["user"] = user
        return value


class RequestPasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        value = value.lower()
        try:
            user = User.objects.get(email=value)
            if user.is_active:
                self.context["user"] = user
        except User.DoesNotExist:
            pass  # Do not reveal whether user exists
        return value


class ConfirmPasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=6, min_length=6)
    new_password = serializers.CharField(write_only=True, min_length=8)
    new_password_confirm = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs["email"].lower()
        code = attrs["code"]

        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError({"new_password_confirm": "Passwords do not match."})

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError("User not found.")

        otp = (
            EmailOTP.objects.filter(
                user=user,
                purpose=OTPPurpose.PASSWORD_RESET,
                code=code,
                is_used=False,
            )
            .order_by("-created_at")
            .first()
        )

        if not otp:
            raise serializers.ValidationError("Invalid or already used OTP.")
        if otp.is_expired():
            raise serializers.ValidationError("OTP has expired. Request a new one.")

        attrs["user"] = user
        attrs["otp"] = otp
        return attrs
