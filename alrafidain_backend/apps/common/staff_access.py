from __future__ import annotations

from apps.common.choices import StaffRole, UserType


def _get_staff_profile(user):
    if not user or not getattr(user, "is_authenticated", False):
        return None
    try:
        return user.staff_profile
    except Exception:
        return None


def has_staff_capability(user, capability: str) -> bool:
    """Role-scoped capability gate for administrative users.

    Superusers are always allowed.
    Non-staff user types are denied.
    """

    if not user or not getattr(user, "is_authenticated", False):
        return False

    if getattr(user, "is_superuser", False):
        return True

    if getattr(user, "user_type", None) != UserType.STAFF:
        return False

    profile = _get_staff_profile(user)
    if profile is None or not getattr(profile, "is_active", False):
        return False

    role = profile.staff_role
    if role == StaffRole.SYSTEM_ADMIN:
        return True

    capability_map = {
        "approve_professionals": bool(getattr(profile, "can_approve_professionals", False)),
        "manage_knowledge_base": bool(getattr(profile, "can_manage_knowledge_base", False)),
        "export_datasets": bool(getattr(profile, "can_export_datasets", False)),
        "view_audit_logs": bool(getattr(profile, "can_view_audit_logs", False)),
        "review_rag_feedback": bool(getattr(profile, "can_export_datasets", False)),
        "view_rag_analytics": bool(getattr(profile, "can_export_datasets", False)),
        "manage_finance": role == StaffRole.FINANCIAL,
    }
    return capability_map.get(capability, False)


def get_allowed_admin_sections(user) -> list[str]:
    """Returns dashboard sections a staff member is allowed to access."""

    sections: list[str] = []

    if has_staff_capability(user, "approve_professionals"):
        sections.append("verification")
    if has_staff_capability(user, "manage_knowledge_base"):
        sections.extend(
            [
                "knowledge_base_documents",
                "knowledge_base_review",
            ]
        )
    if has_staff_capability(user, "review_rag_feedback"):
        sections.append("rag_feedback")
    if has_staff_capability(user, "view_rag_analytics"):
        sections.extend(
            [
                "rag_analytics",
                "rag_dataset_export",
            ]
        )
    if has_staff_capability(user, "view_audit_logs"):
        sections.append("audit_logs")
    if has_staff_capability(user, "manage_finance"):
        sections.extend(
            [
                "finance_dashboard",
                "wallet_transactions",
                "payment_intents",
                "manual_recharge",
                "provider_earnings",
            ]
        )

    # Keep response stable and deterministic.
    return sorted(set(sections))
