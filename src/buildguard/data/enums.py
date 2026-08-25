"""Controlled vocabularies for the core data model (Section 8.4).

Defined once here and reused by the data contracts, the synthetic
generator, and the feature pipeline, so the set of valid categories can
never drift between producer and consumer.
"""

from __future__ import annotations

from enum import Enum, StrEnum


class ProjectType(StrEnum):
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    INDUSTRIAL = "industrial"
    INFRASTRUCTURE = "infrastructure"
    MIXED_USE = "mixed_use"


class ConstructionStandard(StrEnum):
    ECONOMY = "economy"
    STANDARD = "standard"
    HIGH_STANDARD = "high_standard"
    LUXURY = "luxury"


class ChangeOrderCategory(StrEnum):
    SCOPE_CHANGE = "scope_change"
    DESIGN_ERROR = "design_error"
    SITE_CONDITION = "site_condition"
    REGULATORY = "regulatory"
    CLIENT_REQUEST = "client_request"
    OTHER = "other"


class ChangeOrderStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class SupplierCategory(StrEnum):
    STRUCTURAL = "structural"
    MEP = "mep"
    FINISHES = "finishes"
    EARTHWORKS = "earthworks"
    FACADE = "facade"
    GENERAL_CONTRACTOR = "general_contractor"
    OTHER = "other"


def values(enum_cls: type[Enum]) -> list[str]:
    """Return the plain string values of a str Enum, for use in Pandera `isin` checks."""
    return [member.value for member in enum_cls]
