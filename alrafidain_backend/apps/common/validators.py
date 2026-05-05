import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

_IRAQI_PHONE_RE = re.compile(r"^(077|078|075|079)\d{8}$")


def iraqi_phone_validator(value: str) -> None:
    if not _IRAQI_PHONE_RE.match(value):
        raise ValidationError(
            _(
                "Enter a valid Iraqi phone number starting with 077, 078, 075, "
                "or 079 and exactly 11 digits."
            ),
            code="invalid_iraqi_phone",
        )
