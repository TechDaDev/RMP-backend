from django.db import models


class UserType(models.TextChoices):
    PATIENT = "patient", "Patient"
    DOCTOR = "doctor", "Doctor"
    PHARMACIST = "pharmacist", "Pharmacist"
    LABORATORIAN = "laboratorian", "Laboratorian"
    STAFF = "staff", "Staff / Admin"


class StaffRole(models.TextChoices):
    SYSTEM_ADMIN = "system_admin", "System Administrator"
    VERIFICATION_OFFICER = "verification_officer", "Verification Officer"
    KNOWLEDGE_BASE_MANAGER = "knowledge_base_manager", "Knowledge Base Manager"
    ANALYTICS_OFFICER = "analytics_officer", "Analytics Officer"
    SUPPORT_SPECIALIST = "support_specialist", "Support Specialist"
    COMPLIANCE_OFFICER = "compliance_officer", "Compliance Officer"


class Gender(models.TextChoices):
    MALE = "male", "Male"
    FEMALE = "female", "Female"


class Governorate(models.TextChoices):
    BAGHDAD = "baghdad", "Baghdad"
    BASRA = "basra", "Basra"
    NINEVEH = "nineveh", "Nineveh"
    ERBIL = "erbil", "Erbil"
    NAJAF = "najaf", "Najaf"
    KARBALA = "karbala", "Karbala"
    DHI_QAR = "dhi_qar", "Dhi Qar"
    MAYSAN = "maysan", "Maysan"
    WASIT = "wasit", "Wasit"
    DIYALA = "diyala", "Diyala"
    ANBAR = "anbar", "Anbar"
    SALAH_AL_DIN = "salah_al_din", "Salah al-Din"
    KIRKUK = "kirkuk", "Kirkuk"
    SULAYMANIYAH = "sulaymaniyah", "Sulaymaniyah"
    DOHUK = "dohuk", "Dohuk"
    QADISIYYAH = "qadisiyyah", "Qadisiyyah"
    MUTHANNA = "muthanna", "Muthanna"
    BABYLON = "babylon", "Babylon"


class VerificationStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    SUSPENDED = "suspended", "Suspended"


class MedicalSpecialty(models.TextChoices):
    GENERAL_MEDICINE = "general_medicine", "General Medicine"
    INTERNAL_MEDICINE = "internal_medicine", "Internal Medicine"
    CARDIOLOGY = "cardiology", "Cardiology"
    DERMATOLOGY = "dermatology", "Dermatology"
    PEDIATRICS = "pediatrics", "Pediatrics"
    GYNECOLOGY = "gynecology", "Gynecology"
    NEUROLOGY = "neurology", "Neurology"
    ENT = "ent", "ENT"
    OPHTHALMOLOGY = "ophthalmology", "Ophthalmology"
    ORTHOPEDICS = "orthopedics", "Orthopedics"
    UROLOGY = "urology", "Urology"
    GASTROENTEROLOGY = "gastroenterology", "Gastroenterology"
    PSYCHIATRY = "psychiatry", "Psychiatry"
    EMERGENCY_MEDICINE = "emergency_medicine", "Emergency Medicine"
    FAMILY_MEDICINE = "family_medicine", "Family Medicine"
    DENTISTRY = "dentistry", "Dentistry"
    ENDOCRINOLOGY = "endocrinology", "Endocrinology"
    PULMONOLOGY = "pulmonology", "Pulmonology"
    NEPHROLOGY = "nephrology", "Nephrology"
    RHEUMATOLOGY = "rheumatology", "Rheumatology"
    OTHER = "other", "Other"


class ConsultationStatus(models.TextChoices):
    SUBMITTED = "submitted", "Submitted"
    ACCEPTED = "accepted", "Accepted"
    DOCTOR_RESPONDED = "doctor_responded", "Doctor Responded"
    CLOSED = "closed", "Closed"
    CANCELLED = "cancelled", "Cancelled"
    REJECTED = "rejected", "Rejected"


class ConsultationDuration(models.TextChoices):
    LESS_THAN_24_HOURS = "less_than_24_hours", "Less than 24 hours"
    ONE_TO_THREE_DAYS = "one_to_three_days", "1-3 days"
    FOUR_TO_SEVEN_DAYS = "four_to_seven_days", "4-7 days"
    ONE_TO_TWO_WEEKS = "one_to_two_weeks", "1-2 weeks"
    MORE_THAN_TWO_WEEKS = "more_than_two_weeks", "More than 2 weeks"
    CHRONIC_RECURRING = "chronic_recurring", "Chronic / recurring"


class SeverityLevel(models.TextChoices):
    MILD = "mild", "Mild"
    MODERATE = "moderate", "Moderate"
    SEVERE = "severe", "Severe"
    VERY_SEVERE = "very_severe", "Very severe"


class DoctorRecommendationType(models.TextChoices):
    GENERAL_ADVICE = "general_advice", "General Advice"
    NEEDS_IN_PERSON_VISIT = "needs_in_person_visit", "Needs In-Person Visit"
    NEEDS_EMERGENCY_CARE = "needs_emergency_care", "Needs Emergency Care"
    NEEDS_LAB_TEST = "needs_lab_test", "Needs Lab Test"
    FOLLOW_UP_REQUIRED = "follow_up_required", "Follow-Up Required"


class MessageSenderRole(models.TextChoices):
    PATIENT = "patient", "Patient"
    DOCTOR = "doctor", "Doctor"


class MessageType(models.TextChoices):
    TEXT = "text", "Text"
    ATTACHMENT = "attachment", "Attachment"
    SYSTEM = "system", "System"


class PrescriptionStatus(models.TextChoices):
    ISSUED = "issued", "Issued"
    PARTIALLY_DISPENSED = "partially_dispensed", "Partially Dispensed"
    FULLY_DISPENSED = "fully_dispensed", "Fully Dispensed"
    EXPIRED = "expired", "Expired"
    CANCELLED = "cancelled", "Cancelled"


class PrescriptionItemStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    DISPENSED = "dispensed", "Dispensed"
    CANCELLED = "cancelled", "Cancelled"


class DispensingAttemptStatus(models.TextChoices):
    DISPENSED = "dispensed", "Dispensed"
    UNAVAILABLE = "unavailable", "Unavailable"


class MedicationRoute(models.TextChoices):
    ORAL = "oral", "Oral"
    TOPICAL = "topical", "Topical"
    INHALATION = "inhalation", "Inhalation"
    INJECTION = "injection", "Injection"
    EYE = "eye", "Eye"
    EAR = "ear", "Ear"
    NASAL = "nasal", "Nasal"
    RECTAL = "rectal", "Rectal"
    OTHER = "other", "Other"


class NotificationType(models.TextChoices):
    ACCOUNT = "account", "Account"
    PROFILE = "profile", "Profile"
    MEDICAL_RECORD = "medical_record", "Medical Record"
    LAB_ORDER = "lab_order", "Lab Order"
    CONSULTATION = "consultation", "Consultation"
    MESSAGE = "message", "Message"
    PRESCRIPTION = "prescription", "Prescription"
    DISPENSING = "dispensing", "Dispensing"
    SYSTEM = "system", "System"


class NotificationPriority(models.TextChoices):
    LOW = "low", "Low"
    NORMAL = "normal", "Normal"
    HIGH = "high", "High"
    URGENT = "urgent", "Urgent"


class MedicalRecordCategory(models.TextChoices):
    BLOOD_GROUP = "blood_group", "Blood Group"
    ALLERGY = "allergy", "Allergy"
    CHRONIC_CONDITION = "chronic_condition", "Chronic Condition"
    CURRENT_MEDICATION = "current_medication", "Current Medication"
    PAST_SURGERY = "past_surgery", "Past Surgery"
    FAMILY_HISTORY = "family_history", "Family History"
    SMOKING_STATUS = "smoking_status", "Smoking Status"
    PREGNANCY_STATUS = "pregnancy_status", "Pregnancy Status"
    GENERAL_NOTE = "general_note", "General Note"
    LAB_REPORT = "lab_report", "Lab Report"
    SONAR_REPORT = "sonar_report", "Sonar Report"
    XRAY_REPORT = "xray_report", "X-Ray Report"
    RADIOLOGY_REPORT = "radiology_report", "Radiology Report"
    PRESCRIPTION_REPORT = "prescription_report", "Prescription Report"
    DISCHARGE_SUMMARY = "discharge_summary", "Discharge Summary"
    UPLOADED_MEDICAL_REPORT = "uploaded_medical_report", "Uploaded Medical Report"


class MedicalRecordVerificationStatus(models.TextChoices):
    SELF_REPORTED = "self_reported", "Self Reported"
    DOCTOR_CONFIRMED = "doctor_confirmed", "Doctor Confirmed"
    LABORATORY_CONFIRMED = "laboratory_confirmed", "Laboratory Confirmed"
    REJECTED = "rejected", "Rejected"
    UNKNOWN = "unknown", "Unknown"


class MedicalRecordSourceRole(models.TextChoices):
    PATIENT = "patient", "Patient"
    DOCTOR = "doctor", "Doctor"
    LABORATORIAN = "laboratorian", "Laboratorian"
    SYSTEM = "system", "System"


class MedicalReportType(models.TextChoices):
    LAB_REPORT = "lab_report", "Lab Report"
    SONAR_REPORT = "sonar_report", "Sonar Report"
    XRAY_REPORT = "xray_report", "X-Ray Report"
    CT_SCAN = "ct_scan", "CT Scan"
    MRI = "mri", "MRI"
    ECG = "ecg", "ECG"
    PRESCRIPTION_IMAGE = "prescription_image", "Prescription Image"
    DISCHARGE_SUMMARY = "discharge_summary", "Discharge Summary"
    DOCTOR_NOTE = "doctor_note", "Doctor Note"
    PATHOLOGY_REPORT = "pathology_report", "Pathology Report"
    MICROBIOLOGY_REPORT = "microbiology_report", "Microbiology Report"
    RADIOLOGY_REPORT = "radiology_report", "Radiology Report"
    OTHER_MEDICAL_REPORT = "other_medical_report", "Other Medical Report"
    NOT_MEDICAL_REPORT = "not_medical_report", "Not Medical Report"
    UNKNOWN = "unknown", "Unknown"


class MedicalReportProcessingStatus(models.TextChoices):
    UPLOADED = "uploaded", "Uploaded"
    QUEUED = "queued", "Queued"
    OCR_PENDING = "ocr_pending", "OCR Pending"
    OCR_COMPLETED = "ocr_completed", "OCR Completed"
    LLM_PENDING = "llm_pending", "LLM Pending"
    LLM_COMPLETED = "llm_completed", "LLM Completed"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"
    FAILED = "failed", "Failed"
    DOCTOR_REVIEWED = "doctor_reviewed", "Doctor Reviewed"


class MedicalReportSource(models.TextChoices):
    CHAT_ATTACHMENT = "chat_attachment", "Chat Attachment"
    CONSULTATION_ATTACHMENT = "consultation_attachment", "Consultation Attachment"
    LAB_RESULT_FILE = "lab_result_file", "Lab Result File"
    MANUAL_UPLOAD = "manual_upload", "Manual Upload"
    SYSTEM_IMPORT = "system_import", "System Import"


class MedicalReportVisibility(models.TextChoices):
    PATIENT_AND_ASSIGNED_DOCTOR = (
        "patient_and_assigned_doctor",
        "Patient and Assigned Doctor",
    )
    DOCTOR_ONLY = "doctor_only", "Doctor Only"
    STAFF_ONLY = "staff_only", "Staff Only"


class BloodGroup(models.TextChoices):
    A_POSITIVE = "a_positive", "A+"
    A_NEGATIVE = "a_negative", "A-"
    B_POSITIVE = "b_positive", "B+"
    B_NEGATIVE = "b_negative", "B-"
    AB_POSITIVE = "ab_positive", "AB+"
    AB_NEGATIVE = "ab_negative", "AB-"
    O_POSITIVE = "o_positive", "O+"
    O_NEGATIVE = "o_negative", "O-"
    UNKNOWN = "unknown", "Unknown"


class KnowledgeDocumentType(models.TextChoices):
    MEDICAL_BOOK = "medical_book", "Medical Book"
    LABORATORY_BOOK = "laboratory_book", "Laboratory Book"
    CLINICAL_GUIDELINE = "clinical_guideline", "Clinical Guideline"
    DRUG_REFERENCE = "drug_reference", "Drug Reference"
    PATIENT_EDUCATION = "patient_education", "Patient Education"
    PLATFORM_POLICY = "platform_policy", "Platform Policy"
    OTHER = "other", "Other"


class KnowledgeApprovalStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    ARCHIVED = "archived", "Archived"


class KnowledgeLanguage(models.TextChoices):
    ENGLISH = "english", "English"
    ARABIC = "arabic", "Arabic"
    KURDISH = "kurdish", "Kurdish"
    MIXED = "mixed", "Mixed"
    OTHER = "other", "Other"


class KnowledgeAudience(models.TextChoices):
    DOCTOR = "doctor", "Doctor"
    PHARMACIST = "pharmacist", "Pharmacist"
    LABORATORIAN = "laboratorian", "Laboratorian"
    PATIENT = "patient", "Patient"
    ADMIN = "admin", "Admin"
    MIXED = "mixed", "Mixed"


class KnowledgeSecurityStatus(models.TextChoices):
    PENDING_SCAN = "pending_scan", "Pending Scan"
    SCAN_CLEAN = "scan_clean", "Scan Clean"
    SCAN_FAILED = "scan_failed", "Scan Failed"
    SCAN_SKIPPED = "scan_skipped", "Scan Skipped"


class KnowledgeProcessingStatus(models.TextChoices):
    UPLOADED = "uploaded", "Uploaded"
    EXTRACTED = "extracted", "Extracted"
    CHUNKED = "chunked", "Chunked"
    FAILED = "failed", "Failed"


class LabOrderStatus(models.TextChoices):
    ISSUED = "issued", "Issued"
    PARTIALLY_COMPLETED = "partially_completed", "Partially Completed"
    FULLY_COMPLETED = "fully_completed", "Fully Completed"
    EXPIRED = "expired", "Expired"
    CANCELLED = "cancelled", "Cancelled"


class LabOrderItemStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class LabCompletionAttemptStatus(models.TextChoices):
    COMPLETED = "completed", "Completed"
    UNAVAILABLE = "unavailable", "Unavailable"


class LabTestCategory(models.TextChoices):
    HEMATOLOGY = "hematology", "Hematology"
    BIOCHEMISTRY = "biochemistry", "Biochemistry"
    IMMUNOLOGY = "immunology", "Immunology"
    MICROBIOLOGY = "microbiology", "Microbiology"
    URINE_STOOL = "urine_stool", "Urine / Stool"
    HORMONES = "hormones", "Hormones"
    BLOOD_BANK = "blood_bank", "Blood Bank"
    OTHER = "other", "Other"


class LabResultStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"
    REVIEWED = "reviewed", "Reviewed"
    RELEASED = "released", "Released"
    CORRECTED = "corrected", "Corrected"
    CANCELLED = "cancelled", "Cancelled"


class LabResultValueType(models.TextChoices):
    TEXT = "text", "Text"
    NUMERIC = "numeric", "Numeric"
    POSITIVE_NEGATIVE = "positive_negative", "Positive / Negative"
    BLOOD_GROUP = "blood_group", "Blood Group"
    FILE_ONLY = "file_only", "File Only"


class LabResultFlag(models.TextChoices):
    NORMAL = "normal", "Normal"
    LOW = "low", "Low"
    HIGH = "high", "High"
    CRITICAL_LOW = "critical_low", "Critical Low"
    CRITICAL_HIGH = "critical_high", "Critical High"
    ABNORMAL = "abnormal", "Abnormal"
    UNKNOWN = "unknown", "Unknown"


class RAGServiceContext(models.TextChoices):
    GENERAL_DOCTOR_QUERY = "general_doctor_query", "General Doctor Query"
    CONSULTATION = "consultation", "Consultation"
    LAB_RESULT = "lab_result", "Lab Result"
    REPORT_CASE_UPDATE = "report_case_update", "Report Case Update"
    MEDICAL_RECORD = "medical_record", "Medical Record"
    PRESCRIPTION = "prescription", "Prescription"
    LAB_ORDER = "lab_order", "Lab Order"


class RAGResponseStatus(models.TextChoices):
    SUCCESS = "success", "Success"
    FAILED = "failed", "Failed"
    NO_CONTEXT = "no_context", "No Context"
    BLOCKED = "blocked", "Blocked"


class RAGSafetyLevel(models.TextChoices):
    DOCTOR_ONLY = "doctor_only", "Doctor Only"
    PATIENT_SAFE = "patient_safe", "Patient Safe"
    UNSAFE = "unsafe", "Unsafe"


class RAGFeedbackRating(models.TextChoices):
    HELPFUL = "helpful", "Helpful"
    PARTIALLY_HELPFUL = "partially_helpful", "Partially Helpful"
    NOT_HELPFUL = "not_helpful", "Not Helpful"
    UNSAFE = "unsafe", "Unsafe"


class RAGFeedbackReviewStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    REVIEWED = "reviewed", "Reviewed"
    DISMISSED = "dismissed", "Dismissed"
    ESCALATED = "escalated", "Escalated"


class RAGSourceRelevance(models.TextChoices):
    RELEVANT = "relevant", "Relevant"
    PARTIALLY_RELEVANT = "partially_relevant", "Partially Relevant"
    NOT_RELEVANT = "not_relevant", "Not Relevant"
    UNKNOWN = "unknown", "Unknown"
