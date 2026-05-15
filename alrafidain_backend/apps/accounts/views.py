from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.services import create_audit_log, record_security_event
from apps.common.responses import error_response, success_response
from apps.common.throttles import LoginRateThrottle, OTPRateThrottle, PasswordResetRateThrottle

from .models import OTPPurpose
from .serializers import (
    ActivateAccountSerializer,
    ConfirmPasswordResetSerializer,
    LoginSerializer,
    RegisterSerializer,
    RequestPasswordResetSerializer,
    ResendActivationOTPSerializer,
    UserSerializer,
)
from .services import (
    generate_email_otp,
    send_activation_email,
    send_password_reset_email,
)

User = get_user_model()


@extend_schema(tags=["Accounts"])
class RegisterView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=RegisterSerializer,
        summary="Register a new user",
        description=(
            "Creates an inactive user account and sends an activation OTP to the provided email."
        ),
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        create_audit_log(
            actor=user,
            action="user_registered",
            target=user,
            request=request,
        )
        return success_response(
            message="Registration successful. Check your email for the activation OTP.",
            status_code=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["Accounts"])
class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    @extend_schema(
        request=LoginSerializer,
        summary="Login",
        description="Authenticate with email and password. Returns JWT access and refresh tokens.",
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            record_security_event(
                action="login_failed",
                metadata={
                    "reason_code": "invalid_credentials",
                    "email": request.data.get("email", ""),
                },
                request=request,
            )
            return error_response(
                message="Login failed.",
                errors=serializer.errors,
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        user = serializer.validated_data["user"]
        refresh = RefreshToken.for_user(user)
        create_audit_log(
            actor=user,
            action="login_success",
            target=user,
            request=request,
        )
        return success_response(
            data={
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(user, context={"request": request}).data,
            }
        )


@extend_schema(tags=["Accounts"])
class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get current user",
        description="Returns the authenticated user's basic information.",
    )
    def get(self, request):
        serialized_user = UserSerializer(request.user, context={"request": request}).data
        return success_response(data=serialized_user)


@extend_schema(tags=["Accounts"])
class ActivateAccountView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [OTPRateThrottle]

    @extend_schema(
        request=ActivateAccountSerializer,
        summary="Activate account",
        description="Activates a user account using the OTP sent to their email.",
    )
    def post(self, request):
        serializer = ActivateAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        otp = serializer.validated_data["otp"]
        otp.mark_used()
        user.is_active = True
        user.save(update_fields=["is_active"])
        create_audit_log(
            actor=user,
            action="account_activated",
            target=user,
            request=request,
        )
        return success_response(message="Account activated successfully.")


@extend_schema(tags=["Accounts"])
class ResendActivationOTPView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [OTPRateThrottle]

    @extend_schema(
        request=ResendActivationOTPSerializer,
        summary="Resend activation OTP",
        description=(
            "Resends the activation OTP. Returns a generic response to avoid user enumeration."
        ),
    )
    def post(self, request):
        serializer = ResendActivationOTPSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.context.get("user")
        if user:
            otp = generate_email_otp(user, OTPPurpose.ACCOUNT_ACTIVATION)
            send_activation_email(user, otp)
            create_audit_log(
                actor=user,
                action="activation_otp_resent",
                target=user,
                request=request,
            )
        return success_response(
            message="If the email exists and is inactive, an OTP has been sent."
        )


@extend_schema(tags=["Accounts"])
class RequestPasswordResetView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    @extend_schema(
        request=RequestPasswordResetSerializer,
        summary="Request password reset",
        description=(
            "Sends a password reset OTP. Returns a generic response to avoid user enumeration."
        ),
    )
    def post(self, request):
        serializer = RequestPasswordResetSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.context.get("user")
        if user:
            otp = generate_email_otp(user, OTPPurpose.PASSWORD_RESET)
            send_password_reset_email(user, otp)
            create_audit_log(
                actor=user,
                action="password_reset_requested",
                target=user,
                request=request,
            )
        return success_response(message="If the email exists, a password reset OTP has been sent.")


@extend_schema(tags=["Accounts"])
class ConfirmPasswordResetView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    @extend_schema(
        request=ConfirmPasswordResetSerializer,
        summary="Confirm password reset",
        description="Resets the user's password using the OTP code.",
    )
    def post(self, request):
        serializer = ConfirmPasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        otp = serializer.validated_data["otp"]
        otp.mark_used()
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        create_audit_log(
            actor=user,
            action="password_reset_confirmed",
            target=user,
            request=request,
        )
        return success_response(message="Password reset successful.")
