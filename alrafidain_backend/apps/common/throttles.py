from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    scope = "login"


class OTPRateThrottle(AnonRateThrottle):
    scope = "otp"


class PasswordResetRateThrottle(AnonRateThrottle):
    scope = "password_reset"


class QRScanRateThrottle(UserRateThrottle):
    scope = "qr_scan"
