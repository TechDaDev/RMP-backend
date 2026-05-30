from contextlib import suppress

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.audit.services import create_audit_log
from apps.common.choices import NotificationType, VerificationStatus
from apps.common.permissions import CanApproveProfessionals
from apps.common.responses import error_response, success_response
from apps.notifications.services import create_notification

from .admin_serializers import (
    ROLE_PROFILE_MODEL_MAP,
    AdminVerificationDecisionSerializer,
    AdminVerificationDetailSerializer,
    AdminVerificationListSerializer,
)


class AdminVerificationListPagination(LimitOffsetPagination):
    default_limit = 20


@extend_schema(tags=["Admin Verifications"])
class AdminVerificationListView(APIView):
    permission_classes = [IsAuthenticated, CanApproveProfessionals]

    def _build_queryset(self, role, status_filter, search):
        model = ROLE_PROFILE_MODEL_MAP[role]
        queryset = model.objects.select_related("user", "user__user_profile", "verified_by")

        if status_filter:
            queryset = queryset.filter(verification_status=status_filter)

        if search:
            base_q = (
                Q(user__email__icontains=search)
                | Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
            )
            if role == "doctor":
                base_q = (
                    base_q
                    | Q(medical_license_number__icontains=search)
                    | Q(work_address__icontains=search)
                )
            elif role == "pharmacist":
                base_q = (
                    base_q
                    | Q(pharmacist_license_number__icontains=search)
                    | Q(pharmacy_name__icontains=search)
                    | Q(pharmacy_address__icontains=search)
                )
            elif role == "laboratorian":
                base_q = (
                    base_q
                    | Q(laboratorian_license_number__icontains=search)
                    | Q(laboratory_name__icontains=search)
                    | Q(laboratory_address__icontains=search)
                    | Q(laboratory_governorate__icontains=search)
                    | Q(laboratory_phone_number__icontains=search)
                )
            queryset = queryset.filter(base_q)

        return queryset

    @extend_schema(
        parameters=[
            OpenApiParameter("role", OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter("status", OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter("search", OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter("limit", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("offset", OpenApiTypes.INT, OpenApiParameter.QUERY),
        ],
        responses={200: AdminVerificationListSerializer(many=True)},
    )
    def get(self, request):
        role = request.query_params.get("role")
        status_filter = request.query_params.get("status", VerificationStatus.PENDING)
        search = request.query_params.get("search", "").strip()

        if role and role not in ROLE_PROFILE_MODEL_MAP:
            return error_response("Invalid role filter.", status_code=400)
        if status_filter and status_filter not in VerificationStatus.values:
            return error_response("Invalid status filter.", status_code=400)

        roles = [role] if role else list(ROLE_PROFILE_MODEL_MAP.keys())

        records = []
        for role_name in roles:
            queryset = self._build_queryset(role_name, status_filter, search)
            for profile in queryset:
                records.append({"role": role_name, "profile": profile})

        records.sort(key=lambda item: item["profile"].created_at, reverse=True)

        paginator = AdminVerificationListPagination()
        paginated = paginator.paginate_queryset(records, request, view=self)
        serialized = AdminVerificationListSerializer(paginated, many=True).data

        return success_response(
            "Verification requests retrieved.",
            data={
                "count": paginator.count,
                "next": paginator.get_next_link(),
                "previous": paginator.get_previous_link(),
                "results": serialized,
            },
        )


@extend_schema(tags=["Admin Verifications"])
class AdminVerificationDetailView(APIView):
    permission_classes = [IsAuthenticated, CanApproveProfessionals]

    @extend_schema(responses={200: AdminVerificationDetailSerializer})
    def get(self, request, role, pk):
        model = ROLE_PROFILE_MODEL_MAP.get(role)
        if model is None:
            return error_response("Invalid role.", status_code=400)

        profile = get_object_or_404(
            model.objects.select_related("user", "user__user_profile", "verified_by"),
            pk=pk,
        )
        payload = AdminVerificationDetailSerializer({"role": role, "profile": profile}).data
        return success_response("Verification request retrieved.", data=payload)


class _BaseAdminVerificationDecisionView(APIView):
    permission_classes = [IsAuthenticated, CanApproveProfessionals]
    next_status = None
    action_name = None

    def _get_profile(self, role, pk):
        model = ROLE_PROFILE_MODEL_MAP.get(role)
        if model is None:
            return None
        return (
            model.objects.select_related("user", "user__user_profile", "verified_by")
            .filter(pk=pk)
            .first()
        )

    @extend_schema(
        request=AdminVerificationDecisionSerializer,
        responses={200: AdminVerificationDetailSerializer},
    )
    def post(self, request, role, pk):
        profile = self._get_profile(role, pk)
        if profile is None:
            return error_response("Not found.", status_code=404)

        if profile.user_id == request.user.id:
            return error_response(
                "You cannot review your own profile.",
                status_code=403,
            )

        serializer = AdminVerificationDecisionSerializer(
            data=request.data,
            context={"action": self.action_name},
        )
        if not serializer.is_valid():
            return error_response("Invalid input.", errors=serializer.errors, status_code=400)

        validated = serializer.validated_data
        old_status = profile.verification_status

        profile.verification_status = self.next_status
        profile.verified_at = timezone.now()
        profile.verified_by = request.user
        if self.action_name == "approve":
            profile.verification_notes = validated.get("note", "").strip()
            message_text = "Your verification profile has been approved."
            notification_action = "verification_approved"
        elif self.action_name == "reject":
            profile.verification_notes = validated.get("reason", "").strip()
            message_text = "Your verification profile has been rejected."
            notification_action = "verification_rejected"
        else:
            profile.verification_notes = validated.get("reason", "").strip()
            message_text = "Your verification profile has been suspended."
            notification_action = "verification_suspended"

        profile.save(
            update_fields=[
                "verification_status",
                "verified_at",
                "verified_by",
                "verification_notes",
                "updated_at",
            ]
        )

        create_audit_log(
            actor=request.user,
            action=notification_action,
            target=profile,
            metadata={
                "role": role,
                "profile_id": str(profile.id),
                "target_user_id": str(profile.user_id),
                "old_status": old_status,
                "new_status": profile.verification_status,
                "note": profile.verification_notes,
            },
            request=request,
        )

        with suppress(Exception):
            create_notification(
                recipient=profile.user,
                notification_type=NotificationType.PROFILE,
                title="Verification status updated",
                message=message_text,
                data={
                    "role": role,
                    "profile_id": str(profile.id),
                    "verification_status": profile.verification_status,
                },
            )

        payload = AdminVerificationDetailSerializer({"role": role, "profile": profile}).data
        return success_response("Verification status updated.", data=payload)


@extend_schema(tags=["Admin Verifications"])
class AdminVerificationApproveView(_BaseAdminVerificationDecisionView):
    next_status = VerificationStatus.APPROVED
    action_name = "approve"


@extend_schema(tags=["Admin Verifications"])
class AdminVerificationRejectView(_BaseAdminVerificationDecisionView):
    next_status = VerificationStatus.REJECTED
    action_name = "reject"


@extend_schema(tags=["Admin Verifications"])
class AdminVerificationSuspendView(_BaseAdminVerificationDecisionView):
    next_status = VerificationStatus.SUSPENDED
    action_name = "suspend"
