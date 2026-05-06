from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import CreateAPIView, ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.common.choices import LabResultStatus, UserType
from apps.common.responses import error_response, success_response
from apps.common.throttles import QRScanRateThrottle
from apps.consultations.models import Consultation
from apps.consultations.permissions import is_assigned_doctor

from .models import LabOrder, LabOrderItem, LabResult, LabTestCatalog
from .permissions import (
    is_approved_doctor,
    is_approved_laboratorian,
    is_lab_order_doctor,
    is_lab_order_patient,
)
from .serializers import (
    CompleteLabOrderItemsSerializer,
    LabOrderCreateSerializer,
    LabOrderDoctorDetailSerializer,
    LabOrderLaboratorianScanSerializer,
    LabOrderPatientDetailSerializer,
    LabOrderPatientListSerializer,
    LabResultCorrectionSerializer,
    LabResultCreateSerializer,
    LabResultLinkToMedicalRecordSerializer,
    LabResultPatientSerializer,
    LabResultReleaseSerializer,
    LabResultReviewSerializer,
    LabResultSerializer,
    LabTestCatalogSerializer,
)
from .services import (
    cancel_lab_order,
    complete_lab_order_items,
    correct_lab_result,
    create_lab_order,
    create_lab_result,
    get_lab_order_by_qr_token,
    get_remaining_tests_for_laboratorian,
    link_lab_result_to_medical_record,
    release_lab_result_to_patient,
    review_lab_result,
)


@extend_schema(tags=["Lab Orders"])
class LabTestCatalogListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LabTestCatalogSerializer

    def get_queryset(self):
        qs = LabTestCatalog.objects.filter(is_active=True)
        category = self.request.query_params.get("category")
        search = self.request.query_params.get("search")
        if category:
            qs = qs.filter(category=category)
        if search:
            qs = qs.filter(name__icontains=search)
        return qs

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return success_response("Lab tests retrieved.", data=serializer.data)


@extend_schema(tags=["Lab Orders"])
class LabOrderCreateView(CreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LabOrderCreateSerializer

    def create(self, request, *args, **kwargs):
        consultation = get_object_or_404(Consultation, id=kwargs["consultation_id"])

        if not is_approved_doctor(request.user):
            return error_response(
                "Only approved doctors can create lab orders.",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        if not is_assigned_doctor(request.user, consultation):
            return error_response(
                "You are not the assigned doctor for this consultation.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                "Invalid input.", errors=serializer.errors, status_code=status.HTTP_400_BAD_REQUEST
            )

        try:
            lab_order = create_lab_order(
                consultation=consultation,
                doctor=request.user,
                items_data=serializer.validated_data["items"],
                request=request,
            )
        except (ValueError, PermissionError) as exc:
            return error_response(str(exc), status_code=status.HTTP_400_BAD_REQUEST)

        return success_response(
            "Lab order created.",
            data=LabOrderDoctorDetailSerializer(lab_order).data,
            status_code=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["Lab Orders"])
class PatientLabOrderListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LabOrderPatientListSerializer

    def get_queryset(self):
        if self.request.user.user_type != UserType.PATIENT:
            return LabOrder.objects.none()
        return LabOrder.objects.filter(patient=self.request.user).select_related(
            "doctor", "consultation"
        )

    def list(self, request, *args, **kwargs):
        if request.user.user_type != UserType.PATIENT:
            return error_response(
                "Only patients can list lab orders.", status_code=status.HTTP_403_FORBIDDEN
            )
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return success_response("Lab orders retrieved.", data=serializer.data)


@extend_schema(tags=["Lab Orders"])
class PatientLabOrderDetailView(RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LabOrderPatientDetailSerializer

    def retrieve(self, request, *args, **kwargs):
        lab_order = get_object_or_404(
            LabOrder.objects.select_related("doctor", "consultation"), id=kwargs["lab_order_id"]
        )
        if not is_lab_order_patient(request.user, lab_order):
            return error_response("Not found.", status_code=status.HTTP_404_NOT_FOUND)
        return success_response("Lab order retrieved.", data=self.get_serializer(lab_order).data)


@extend_schema(tags=["Lab Orders"])
class DoctorLabOrderDetailView(RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LabOrderDoctorDetailSerializer

    def retrieve(self, request, *args, **kwargs):
        lab_order = get_object_or_404(
            LabOrder.objects.select_related("doctor", "patient", "consultation").prefetch_related(
                "items",
                "completion_records__laboratorian",
                "completion_records__lab_order_item",
            ),
            id=kwargs["lab_order_id"],
        )
        if not is_lab_order_doctor(request.user, lab_order):
            return error_response("Not found.", status_code=status.HTTP_404_NOT_FOUND)
        return success_response("Lab order retrieved.", data=self.get_serializer(lab_order).data)


@extend_schema(tags=["Lab Orders"])
class DoctorCancelLabOrderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, lab_order_id):
        lab_order = get_object_or_404(LabOrder, id=lab_order_id)
        if not is_lab_order_doctor(request.user, lab_order):
            return error_response("Not found.", status_code=status.HTTP_404_NOT_FOUND)

        try:
            lab_order = cancel_lab_order(lab_order=lab_order, doctor=request.user, request=request)
        except (ValueError, PermissionError) as exc:
            return error_response(str(exc), status_code=status.HTTP_400_BAD_REQUEST)

        return success_response(
            "Lab order cancelled.", data=LabOrderDoctorDetailSerializer(lab_order).data
        )


@extend_schema(tags=["Lab Orders"])
class LaboratorianLabOrderScanView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [QRScanRateThrottle]

    def post(self, request):
        if not is_approved_laboratorian(request.user):
            return error_response(
                "Only approved laboratorians can scan QR tokens.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        token = (request.data.get("qr_token") or "").strip()
        if not token:
            return error_response("qr_token is required.", status_code=status.HTTP_400_BAD_REQUEST)

        try:
            lab_order = get_lab_order_by_qr_token(token, request.user, request=request)
        except (ValueError, PermissionError) as exc:
            return error_response(str(exc), status_code=status.HTTP_400_BAD_REQUEST)

        locked = lab_order.is_locked()
        remaining = [] if locked else list(get_remaining_tests_for_laboratorian(lab_order))
        data = {
            "lab_order": lab_order,
            "remaining_items": remaining,
            "locked": locked,
            "message": "This lab order is no longer available for completion." if locked else None,
        }
        return success_response("QR scanned.", data=LabOrderLaboratorianScanSerializer(data).data)


@extend_schema(tags=["Lab Orders"])
class LaboratorianCompleteLabOrderItemsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=CompleteLabOrderItemsSerializer)
    def post(self, request, lab_order_id):
        if not is_approved_laboratorian(request.user):
            return error_response(
                "Only approved laboratorians can complete tests.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        lab_order = get_object_or_404(LabOrder, id=lab_order_id)
        serializer = CompleteLabOrderItemsSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                "Invalid input.", errors=serializer.errors, status_code=status.HTTP_400_BAD_REQUEST
            )

        try:
            lab_order = complete_lab_order_items(
                lab_order=lab_order,
                laboratorian=request.user,
                items_payload=serializer.validated_data["items"],
                request=request,
            )
        except (ValueError, PermissionError) as exc:
            return error_response(str(exc), status_code=status.HTTP_400_BAD_REQUEST)

        locked = lab_order.is_locked()
        remaining = [] if locked else list(get_remaining_tests_for_laboratorian(lab_order))
        data = {
            "lab_order": lab_order,
            "remaining_items": remaining,
            "locked": locked,
            "message": "This lab order is no longer available for completion." if locked else None,
        }
        return success_response(
            "Items processed.", data=LabOrderLaboratorianScanSerializer(data).data
        )


@extend_schema(tags=["Lab Results"])
class LabResultCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=LabResultCreateSerializer)
    def post(self, request, lab_order_item_id):
        if not is_approved_laboratorian(request.user):
            return error_response(
                "Only approved laboratorians can create lab results.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        item = get_object_or_404(LabOrderItem, id=lab_order_item_id)
        serializer = LabResultCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                "Invalid input.", errors=serializer.errors, status_code=status.HTTP_400_BAD_REQUEST
            )

        result_data = dict(serializer.validated_data)
        if result_data.get("result_file") is not None:
            result_data["original_file_name"] = getattr(result_data["result_file"], "name", "")

        try:
            lab_result = create_lab_result(item, request.user, result_data, request=request)
        except (ValueError, PermissionError) as exc:
            return error_response(str(exc), status_code=status.HTTP_400_BAD_REQUEST)

        return success_response(
            "Lab result created.",
            data=LabResultSerializer(lab_result).data,
            status_code=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["Lab Results"])
class LabResultDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, lab_result_id):
        lab_result = get_object_or_404(LabResult, id=lab_result_id)

        if request.user.id == lab_result.doctor_id or request.user.id == lab_result.laboratorian_id:
            return success_response(
                "Lab result retrieved.", data=LabResultSerializer(lab_result).data
            )

        if request.user.id == lab_result.patient_id:
            if lab_result.status != LabResultStatus.RELEASED:
                return error_response("Not found.", status_code=status.HTTP_404_NOT_FOUND)
            return success_response(
                "Lab result retrieved.", data=LabResultPatientSerializer(lab_result).data
            )

        return error_response("Not found.", status_code=status.HTTP_404_NOT_FOUND)


@extend_schema(tags=["Lab Results"])
class DoctorLabResultDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, lab_result_id):
        lab_result = get_object_or_404(LabResult, id=lab_result_id)
        if request.user.id != lab_result.doctor_id:
            return error_response("Not found.", status_code=status.HTTP_404_NOT_FOUND)
        return success_response("Lab result retrieved.", data=LabResultSerializer(lab_result).data)


@extend_schema(tags=["Lab Results"])
class PatientLabResultListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LabResultPatientSerializer

    def get_queryset(self):
        if (request_user := getattr(self.request, "user", None)) and (
            request_user.user_type == UserType.PATIENT
        ):
            return LabResult.objects.filter(
                patient=request_user, status=LabResultStatus.RELEASED
            ).select_related("lab_order_item")
        return LabResult.objects.none()

    def list(self, request, *args, **kwargs):
        if request.user.user_type != UserType.PATIENT:
            return error_response(
                "Only patients can list lab results.", status_code=status.HTTP_403_FORBIDDEN
            )
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return success_response("Lab results retrieved.", data=serializer.data)


@extend_schema(tags=["Lab Results"])
class PatientLabResultDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, lab_result_id):
        if request.user.user_type != UserType.PATIENT:
            return error_response(
                "Only patients can access this endpoint.", status_code=status.HTTP_403_FORBIDDEN
            )
        lab_result = get_object_or_404(
            LabResult, id=lab_result_id, patient=request.user, status=LabResultStatus.RELEASED
        )
        return success_response(
            "Lab result retrieved.", data=LabResultPatientSerializer(lab_result).data
        )


@extend_schema(tags=["Lab Results"])
class LabResultCorrectionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=LabResultCorrectionSerializer)
    def post(self, request, lab_result_id):
        lab_result = get_object_or_404(LabResult, id=lab_result_id)
        serializer = LabResultCorrectionSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                "Invalid input.", errors=serializer.errors, status_code=status.HTTP_400_BAD_REQUEST
            )

        reason = serializer.validated_data.get("reason")
        new_data = {k: v for k, v in serializer.validated_data.items() if k != "reason"}
        try:
            lab_result = correct_lab_result(
                lab_result, request.user, new_data, reason, request=request
            )
        except (ValueError, PermissionError) as exc:
            return error_response(str(exc), status_code=status.HTTP_400_BAD_REQUEST)

        return success_response("Lab result corrected.", data=LabResultSerializer(lab_result).data)


@extend_schema(tags=["Lab Results"])
class DoctorReviewLabResultView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=LabResultReviewSerializer)
    def post(self, request, lab_result_id):
        lab_result = get_object_or_404(LabResult, id=lab_result_id)
        serializer = LabResultReviewSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                "Invalid input.", errors=serializer.errors, status_code=status.HTTP_400_BAD_REQUEST
            )

        try:
            lab_result = review_lab_result(
                lab_result,
                request.user,
                doctor_notes=serializer.validated_data.get("doctor_notes"),
                release_to_patient=serializer.validated_data.get("release_to_patient", False),
                request=request,
            )
        except (ValueError, PermissionError) as exc:
            return error_response(str(exc), status_code=status.HTTP_400_BAD_REQUEST)

        return success_response("Lab result reviewed.", data=LabResultSerializer(lab_result).data)


@extend_schema(tags=["Lab Results"])
class DoctorReleaseLabResultView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=LabResultReleaseSerializer)
    def post(self, request, lab_result_id):
        lab_result = get_object_or_404(LabResult, id=lab_result_id)
        try:
            lab_result = release_lab_result_to_patient(lab_result, request.user, request=request)
        except (ValueError, PermissionError) as exc:
            return error_response(str(exc), status_code=status.HTTP_400_BAD_REQUEST)
        return success_response("Lab result released.", data=LabResultSerializer(lab_result).data)


@extend_schema(tags=["Lab Results"])
class DoctorLinkLabResultToMedicalRecordView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=LabResultLinkToMedicalRecordSerializer)
    def post(self, request, lab_result_id):
        lab_result = get_object_or_404(LabResult, id=lab_result_id)
        try:
            lab_result = link_lab_result_to_medical_record(
                lab_result, request.user, request=request
            )
        except (ValueError, PermissionError) as exc:
            return error_response(str(exc), status_code=status.HTTP_400_BAD_REQUEST)
        return success_response(
            "Lab result linked to medical record.", data=LabResultSerializer(lab_result).data
        )
