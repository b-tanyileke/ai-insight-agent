"""Load and validate client profiles used by the insight pipeline.

Profiles are deliberately kept outside application code as JSON documents.  This
makes the business context reviewable in pull requests and lets future pipeline
stages select a profile without changing their implementation.
"""

import json
import re
from pathlib import Path


class ClientProfileError(ValueError):
    """Raised when a client profile is missing or does not meet the contract."""


PROFILE_DIR = Path(__file__).resolve().parent.parent / "profiles"

REQUIRED_STRING_FIELDS = (
    "id",
    "name",
    "business_type",
    "industry",
    "geography",
    "ai_maturity",
)
REQUIRED_LIST_FIELDS = (
    "strategic_priorities",
    "target_functions",
    "approved_vendors",
    "data_sensitivity",
    "regulatory_considerations",
    "screening_terms",
)
VALID_AI_MATURITY = {"exploring", "piloting", "scaling", "optimizing"}
PROFILE_ID_PATTERN = re.compile(r"^[a-z0-9-]+$")


def _require_non_empty_strings(profile, field_names):
    for field in field_names:
        value = profile.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ClientProfileError(f"'{field}' must be a non-empty string")


def _require_string_lists(profile, field_names):
    for field in field_names:
        value = profile.get(field)
        if not isinstance(value, list) or not value:
            raise ClientProfileError(f"'{field}' must be a non-empty list")
        if any(not isinstance(item, str) or not item.strip() for item in value):
            raise ClientProfileError(f"'{field}' must contain only non-empty strings")


def validate_profile(profile):
    """Validate a profile dictionary and return it unchanged when valid."""
    if not isinstance(profile, dict):
        raise ClientProfileError("profile must be a JSON object")

    _require_non_empty_strings(profile, REQUIRED_STRING_FIELDS)
    _require_string_lists(profile, REQUIRED_LIST_FIELDS)

    required_fields = set(REQUIRED_STRING_FIELDS) | set(REQUIRED_LIST_FIELDS)
    unexpected = set(profile) - required_fields
    if unexpected:
        raise ClientProfileError(
            "profile contains unsupported field(s): " + ", ".join(sorted(unexpected))
        )

    if not PROFILE_ID_PATTERN.fullmatch(profile["id"]):
        raise ClientProfileError("'id' must contain only lowercase letters, numbers, and hyphens")

    if profile["ai_maturity"] not in VALID_AI_MATURITY:
        allowed = ", ".join(sorted(VALID_AI_MATURITY))
        raise ClientProfileError(f"'ai_maturity' must be one of: {allowed}")

    return profile


def profile_path(profile_id, profile_dir=PROFILE_DIR):
    """Return the expected JSON path for a safe, simple profile identifier."""
    if not isinstance(profile_id, str) or not PROFILE_ID_PATTERN.fullmatch(profile_id):
        raise ClientProfileError("profile id must be a non-empty string")
    return Path(profile_dir) / f"{profile_id}.json"


def load_profile(profile_id, profile_dir=PROFILE_DIR):
    """Load one named JSON profile and validate it before returning it."""
    path = profile_path(profile_id, profile_dir)
    if not path.exists():
        raise ClientProfileError(f"profile '{profile_id}' was not found at {path}")

    try:
        with open(path, "r", encoding="utf-8") as file:
            profile = json.load(file)
    except json.JSONDecodeError as exc:
        raise ClientProfileError(f"profile '{profile_id}' is not valid JSON: {exc}") from exc

    return validate_profile(profile)


def list_profiles(profile_dir=PROFILE_DIR):
    """Return available profile ids in stable order without loading them."""
    directory = Path(profile_dir)
    if not directory.exists():
        return []
    return sorted(
        path.stem
        for path in directory.glob("*.json")
        if not path.name.endswith(".schema.json")
    )
