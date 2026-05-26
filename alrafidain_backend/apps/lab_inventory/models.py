from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.common.models import BaseModel


class LabTestOffering(BaseModel):
    lab = models.ForeignKey(
        "profiles.LaboratorianProfile",
        on_delete=models.CASCADE,
        related_name="test_offerings",
    )
    lab_test = models.ForeignKey(
        "lab_catalog.LabTest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lab_offerings",
    )
    custom_test_name = models.CharField(max_length=255, blank=True, null=True)
    local_name = models.CharField(max_length=255, blank=True, null=True)
    sample_type_override = models.CharField(max_length=150, blank=True, null=True)
    preparation_notes = models.TextField(blank=True, null=True)
    estimated_turnaround_time = models.CharField(max_length=100, blank=True, null=True)
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    currency = models.CharField(max_length=10, default="IQD")
    is_available = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["lab", "is_active"]),
            models.Index(fields=["is_available", "is_active"]),
            models.Index(fields=["lab_test"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["lab", "lab_test"],
                condition=Q(lab_test__isnull=False, is_active=True),
                name="uniq_active_lab_offering_lab_labtest",
            )
        ]

    def clean(self):
        custom_test_name = (self.custom_test_name or "").strip()

        if not self.lab_test and not custom_test_name:
            raise ValidationError(
                {"custom_test_name": "Provide either a catalog lab_test or custom_test_name."}
            )

        if self.price is not None and self.price < 0:
            raise ValidationError({"price": "Price cannot be negative."})

        if self.lab_test and not self.lab_test.is_active:
            raise ValidationError({"lab_test": "Selected catalog lab test is inactive."})

    @property
    def display_name(self):
        if self.lab_test:
            return self.lab_test.display_name
        if self.custom_test_name:
            return self.custom_test_name
        if self.local_name:
            return self.local_name
        return ""

    def __str__(self):
        lab_name = self.lab.laboratory_name or self.lab.user.email
        return f"{self.display_name} @ {lab_name}"
