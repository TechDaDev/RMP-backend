import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.utils import timezone

from .models import EmailOTP, OTPPurpose

User = get_user_model()


def generate_otp_code() -> str:
    return f"{random.SystemRandom().randint(0, 999999):06d}"


def generate_email_otp(user, purpose: str) -> EmailOTP:
    """Invalidate existing unused OTPs for same user+purpose and create a fresh one."""
    EmailOTP.objects.filter(user=user, purpose=purpose, is_used=False).update(is_used=True)
    return EmailOTP.objects.create(
        user=user,
        purpose=purpose,
        code=generate_otp_code(),
        expires_at=timezone.now() + timedelta(minutes=10),
    )


def send_activation_email(user, otp: EmailOTP) -> None:
    send_mail(
        subject="Activate your Al-Rafidain account",
        message=(
            f"Hi {user.first_name},\n\n"
            f"Your activation code is: {otp.code}\n\n"
            "It expires in 10 minutes."
        ),
        from_email=None,
        recipient_list=[user.email],
        fail_silently=False,
    )


def send_password_reset_email(user, otp: EmailOTP) -> None:
    send_mail(
        subject="Reset your Al-Rafidain password",
        message=(
            f"Hi {user.first_name},\n\n"
            f"Your password reset code is: {otp.code}\n\n"
            "It expires in 10 minutes."
        ),
        from_email=None,
        recipient_list=[user.email],
        fail_silently=False,
    )


def verify_email_otp(user, purpose: str, code: str) -> EmailOTP:
    """
    Validate an OTP for the given user and purpose.
    Raises ValidationError with a descriptive message on failure.
    Returns the validated EmailOTP instance on success.
    """
    try:
        otp = (
            EmailOTP.objects.filter(user=user, purpose=purpose, is_used=False)
            .latest("created_at")
        )
    except EmailOTP.DoesNotExist:
        raise ValidationError("No active OTP found. Please request a new one.")

    if otp.code != code:
        raise ValidationError("Invalid OTP code.")

    if otp.is_expired():
        raise ValidationError("This OTP has expired. Please request a new one.")

    return otp
