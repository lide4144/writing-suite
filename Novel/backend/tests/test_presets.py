from __future__ import annotations

from pathlib import Path

import pytest

from novel_agent.core.config import Settings
from novel_agent.presets.service import PresetValidationError, validate_preset_yaml


def test_builtin_long_novel_preset_matches_schema() -> None:
    settings = Settings(
        presets_root=str(Path(__file__).resolve().parents[2] / "presets"),
        preset_schema_path=str(Path(__file__).resolve().parents[2] / "schemas" / "preset.schema.json"),
    )
    raw = (Path(settings.presets_root) / "long_novel.yaml").read_text(encoding="utf-8")
    content, schema_version, content_hash = validate_preset_yaml(raw, settings)
    assert content["name"] == "long_novel_high_quality"
    assert schema_version == "1.0"
    assert len(content_hash) == 64


def test_invalid_preset_returns_structured_validation_details(tmp_path: Path) -> None:
    settings = Settings(preset_schema_path=str(Path(__file__).resolve().parents[2] / "schemas" / "preset.schema.json"))
    with pytest.raises(PresetValidationError) as error:
        validate_preset_yaml("name: missing-required-fields\n", settings)
    assert error.value.details
    assert any("schema_version" in item["message"] for item in error.value.details)
