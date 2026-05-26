from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.common.models import BaseModel


class PharmacyDrugInventory(BaseModel):
    class StockStatus(models.TextChoices):
        IN_STOCK = "in_stock", "In Stock"
        LOW_STOCK = "low_stock", "Low Stock"
        OUT_OF_STOCK = "out_of_stock", "Out of Stock"
        UNAVAILABLE = "unavailable", "Unavailable"

    pharmacy = models.ForeignKey(
        "profiles.PharmacistProfile",
        on_delete=models.CASCADE,
        related_name="inventory_items",
    )
    drug = models.ForeignKey(
        "medical_catalog.Drug",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pharmacy_inventory_items",
    )
    custom_drug_name = models.CharField(max_length=255, blank=True, null=True)
    brand_name = models.CharField(max_length=255, blank=True, null=True)
    form = models.CharField(max_length=100, blank=True, null=True)
    strength = models.CharField(max_length=100, blank=True, null=True)
    route = models.CharField(max_length=100, blank=True, null=True)
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    currency = models.CharField(max_length=10, default="IQD")
    stock_status = models.CharField(
        max_length=20,
        choices=StockStatus.choices,
        default=StockStatus.IN_STOCK,
    )
    quantity = models.PositiveIntegerField(null=True, blank=True)
    is_available = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["pharmacy", "is_active"]),
            models.Index(fields=["stock_status", "is_available"]),
            models.Index(fields=["drug"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["pharmacy", "drug"],
                condition=Q(drug__isnull=False, is_active=True),
                name="uniq_active_inventory_pharmacy_drug",
            )
        ]

    def clean(self):
        custom_drug_name = (self.custom_drug_name or "").strip()

        if not self.drug and not custom_drug_name:
            raise ValidationError(
                {"custom_drug_name": "Provide either a catalog drug or custom_drug_name."}
            )

        if self.price is not None and self.price < 0:
            raise ValidationError({"price": "Price cannot be negative."})

    @property
    def display_name(self):
        if self.drug:
            base_name = self.drug.name
        else:
            base_name = (self.custom_drug_name or "").strip()

        parts = [base_name]

        resolved_strength = (self.strength or "").strip() or (
            (self.drug.strength or "").strip() if self.drug else ""
        )
        resolved_form = (self.form or "").strip() or (
            (self.drug.form or "").strip() if self.drug else ""
        )

        if resolved_strength:
            parts.append(resolved_strength)
        if resolved_form:
            parts.append(resolved_form)

        return " ".join(p for p in parts if p).strip()

    def __str__(self):
        return f"{self.display_name} @ {self.pharmacy.pharmacy_name or self.pharmacy.user.email}"
