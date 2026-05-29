import os
import uuid


def _uuid_filename(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return f"{uuid.uuid4()}{ext}"


def profile_image_upload_path(instance, filename: str) -> str:
    return f"profiles/{instance.user_id}/{_uuid_filename(filename)}"


def doctor_license_upload_path(instance, filename: str) -> str:
    return f"licenses/doctors/{instance.user_id}/{_uuid_filename(filename)}"


def pharmacist_license_upload_path(instance, filename: str) -> str:
    return f"licenses/pharmacists/{instance.user_id}/{_uuid_filename(filename)}"


def pharmacy_license_upload_path(instance, filename: str) -> str:
    return f"licenses/pharmacies/{instance.user_id}/{_uuid_filename(filename)}"


def laboratorian_license_upload_path(instance, filename: str) -> str:
    return f"licenses/laboratorians/{instance.user_id}/{_uuid_filename(filename)}"


def laboratory_license_upload_path(instance, filename: str) -> str:
    return f"licenses/laboratories/{instance.user_id}/{_uuid_filename(filename)}"


def consultation_attachment_upload_path(instance, filename: str) -> str:
    return f"consultations/{instance.consultation_id}/{_uuid_filename(filename)}"


def message_attachment_upload_path(instance, filename: str) -> str:
    return f"messages/{instance.message.consultation_id}/{_uuid_filename(filename)}"


def lab_result_file_upload_path(instance, filename: str) -> str:
    return (
        "lab-results/"
        f"{instance.lab_order_id}/"
        f"{instance.lab_order_item_id}/"
        f"{_uuid_filename(filename)}"
    )


def knowledge_document_upload_path(instance, filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    doc_id = str(instance.pk) if instance.pk else str(uuid.uuid4())
    return f"knowledge-base/documents/{doc_id}/{uuid.uuid4()}{ext}"


def medical_report_upload_path(instance, filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return f"medical_reports/{instance.patient_id}/{uuid.uuid4()}{ext}"


def wallet_recharge_receipt_upload_path(instance, filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    request_id = str(instance.pk) if instance.pk else str(uuid.uuid4())
    return f"payments/recharge-receipts/{request_id}/{uuid.uuid4()}{ext}"
