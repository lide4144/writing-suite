"""JSON Schema validation for artifact content (spec §6)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from novel_agent.core.errors import APIError

ARTIFACT_TYPES: tuple[str, ...] = (
    "director_decision",
    "plot_plan",
    "idea_candidates",
    "character_intent",
    "scene_brief",
    "chapter_draft",
    "continuity_report",
    "critic_report",
    "revision_instruction",
    "style_edit_result",
    "canon_patch",
    "chapter_summary",
)


class ArtifactValidationError(APIError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            "ARTIFACT_VALIDATION_FAILED",
            message,
            status_code=422,
            details=details or {},
        )


class ArtifactSchemaRegistry:
    """Loads `schemas/artifacts/*.json` once and validates artifact content."""

    def __init__(self, root: Path, *, schema_version: str = "1.0") -> None:
        self.root = Path(root)
        self.default_schema_version = schema_version
        self._validators: dict[str, Draft202012Validator] = {}
        self._versions: dict[str, str] = {}

    @classmethod
    def from_settings(cls, settings: Any) -> "ArtifactSchemaRegistry":
        return cls(Path(settings.artifact_schemas_root), schema_version=settings.artifact_schema_version)

    def load(self) -> None:
        if not self.root.is_dir():
            raise ArtifactValidationError(
                "The artifact schema directory is missing.",
                details={"root": str(self.root)},
            )
        validators: dict[str, Draft202012Validator] = {}
        versions: dict[str, str] = {}
        for path in sorted(self.root.glob("*.json")):
            try:
                schema = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ArtifactValidationError(
                    "An artifact schema is not valid JSON.",
                    details={"path": str(path), "error": str(exc)},
                ) from exc
            try:
                Draft202012Validator.check_schema(schema)
            except SchemaError as exc:
                raise ArtifactValidationError(
                    "An artifact schema is not a valid JSON Schema.",
                    details={"path": str(path), "error": exc.message},
                ) from exc
            artifact_type = path.stem
            validators[artifact_type] = Draft202012Validator(schema)
            versions[artifact_type] = str(schema.get("x-schema-version", self.default_schema_version))
        if not validators:
            raise ArtifactValidationError(
                "No artifact schemas were found.",
                details={"root": str(self.root)},
            )
        self._validators = validators
        self._versions = versions

    @property
    def loaded(self) -> bool:
        return bool(self._validators)

    def known_types(self) -> tuple[str, ...]:
        self._ensure_loaded()
        return tuple(sorted(self._validators))

    def supports(self, artifact_type: str) -> bool:
        self._ensure_loaded()
        return artifact_type in self._validators

    def schema_version(self, artifact_type: str) -> str:
        self._ensure_loaded()
        self._require(artifact_type)
        return self._versions[artifact_type]

    def validate(self, artifact_type: str, content: dict[str, Any]) -> None:
        """Raise :class:`ArtifactValidationError` when content violates its schema."""

        self._ensure_loaded()
        self._require(artifact_type)
        errors = sorted(self._validators[artifact_type].iter_errors(content), key=lambda error: list(error.path))
        if not errors:
            return
        first = errors[0]
        location = "/".join(str(part) for part in first.path) or "<root>"
        raise ArtifactValidationError(
            f"Artifact '{artifact_type}' failed schema validation at {location}: {first.message}",
            details={
                "artifact_type": artifact_type,
                "location": location,
                "errors": [
                    {
                        "location": "/".join(str(part) for part in error.path) or "<root>",
                        "message": error.message,
                    }
                    for error in errors[:10]
                ],
            },
        )

    def _require(self, artifact_type: str) -> None:
        if artifact_type not in self._validators:
            raise ArtifactValidationError(
                f"Unknown artifact type '{artifact_type}'.",
                details={"artifact_type": artifact_type, "known_types": sorted(self._validators)},
            )

    def _ensure_loaded(self) -> None:
        if not self._validators:
            self.load()
