from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_agent.core.config import Settings
from novel_agent.db.models import Preset, PresetVersion


class PresetValidationError(ValueError):
    def __init__(self, message: str, *, details: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.details = details or []


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _first_existing(configured: str, fallback: Path) -> Path:
    candidate = Path(configured).expanduser()
    return candidate if candidate.exists() else fallback


def schema_path(settings: Settings) -> Path:
    return _first_existing(settings.preset_schema_path, _repository_root() / "schemas" / "preset.schema.json")


def builtin_presets_root(settings: Settings) -> Path:
    return _first_existing(settings.presets_root, _repository_root() / "presets")


def load_schema(settings: Settings) -> dict[str, Any]:
    path = schema_path(settings)
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise PresetValidationError(f"Preset schema is unavailable: {path}") from exc
    if not isinstance(schema, dict):
        raise PresetValidationError("Preset schema must be a JSON object.")
    return schema


def validate_preset_yaml(raw_yaml: str, settings: Settings) -> tuple[dict[str, Any], str, str]:
    try:
        content = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as exc:
        raise PresetValidationError("Preset YAML is invalid.", details=[{"message": str(exc)}]) from exc
    if not isinstance(content, dict):
        raise PresetValidationError("Preset YAML must contain a mapping at its root.")

    validator = Draft202012Validator(load_schema(settings))
    errors = sorted(validator.iter_errors(content), key=lambda error: list(error.absolute_path))
    if errors:
        details = [
            {"path": ".".join(str(item) for item in error.absolute_path), "message": error.message}
            for error in errors[:20]
        ]
        raise PresetValidationError("Preset does not match the configured schema.", details=details)
    schema_version = str(content["schema_version"])
    content_hash = hashlib.sha256(raw_yaml.encode("utf-8")).hexdigest()
    return content, schema_version, content_hash


async def ensure_builtin_presets(session: AsyncSession, settings: Settings) -> int:
    """Insert built-ins once; preset versions remain immutable after insertion."""

    root = builtin_presets_root(settings)
    inserted = 0
    if not root.is_dir():
        return inserted
    for path in sorted(root.glob("*.yaml")):
        raw_yaml = path.read_text(encoding="utf-8")
        content, schema_version, content_hash = validate_preset_yaml(raw_yaml, settings)
        name = str(content["name"])
        preset = (await session.execute(select(Preset).where(Preset.name == name))).scalar_one_or_none()
        if preset is None:
            preset = Preset(name=name, description=f"Built-in preset: {name}")
            session.add(preset)
            await session.flush()
        version_exists = (
            await session.execute(
                select(PresetVersion).where(PresetVersion.preset_id == preset.id, PresetVersion.version == 1)
            )
        ).scalar_one_or_none()
        if version_exists is None:
            session.add(
                PresetVersion(
                    preset_id=preset.id,
                    version=1,
                    content_yaml=raw_yaml,
                    content_json=content,
                    content_hash=content_hash,
                    schema_version=schema_version,
                )
            )
            inserted += 1
    return inserted
