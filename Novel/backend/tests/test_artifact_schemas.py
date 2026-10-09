"""Contract tests for the 12 artifact content schemas.

These schemas describe the ``content`` object of an artifact envelope
(``artifact_id`` / ``type`` / ``schema_version`` / ... live on the envelope,
never inside ``content``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import pytest
from jsonschema import Draft202012Validator

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

# /home/lide/Novel/backend/tests/test_artifact_schemas.py -> /home/lide/Novel
SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas" / "artifacts"


def _schema_path(artifact_type: str) -> Path:
    return SCHEMA_DIR / f"{artifact_type}.json"


def _load_schema(artifact_type: str) -> dict[str, Any]:
    return json.loads(_schema_path(artifact_type).read_text(encoding="utf-8"))


def _load_schema_text(artifact_type: str) -> str:
    return _schema_path(artifact_type).read_text(encoding="utf-8")


def _iter_subschemas(node: Any) -> Iterator[dict[str, Any]]:
    """Yield every schema object nested anywhere in a schema document."""
    if isinstance(node, list):
        for item in node:
            yield from _iter_subschemas(item)
        return
    if not isinstance(node, dict):
        return
    yield node
    for key, value in node.items():
        if key in {"properties", "patternProperties", "$defs", "definitions"} and isinstance(value, dict):
            for sub in value.values():
                yield from _iter_subschemas(sub)
        elif key in {"items", "additionalProperties", "contains", "not", "propertyNames", "if", "then", "else"}:
            yield from _iter_subschemas(value)
        elif key in {"allOf", "anyOf", "oneOf", "prefixItems"} and isinstance(value, list):
            yield from _iter_subschemas(value)


def _candidate(index: int) -> dict[str, Any]:
    return {
        "candidate_id": f"cand_{index:02d}",
        "summary": f"候选走向 {index}：主角在黑塔地窖发现被翻动过的档案。",
        "risk_level": ("safe", "moderate", "wild")[index % 3],
        "plausibility": 0.5,
        "surprise": 0.4,
        "canon_dependencies": ["黑塔地窖存在"],
        "side_effects": ["看守人产生怀疑"],
    }


def _critic_problem() -> dict[str, Any]:
    return {
        "severity": "high",
        "location": "12-2 第 14 段",
        "type": "pacing",
        "description": "发现档案被翻动后没有任何反应描写，节奏塌陷。",
        "evidence": "「她看着空抽屉，然后离开了。」",
        "suggested_action": "补充两到三句生理与心理反应，再推进下一场景。",
    }


VALID_SAMPLES: dict[str, dict[str, Any]] = {
    "director_decision": {
        "selected_candidate_id": "cand_07",
        "rationale": "在可信度与意外度之间取得最佳平衡，且不违反既有 Canon。",
        "risk_level": "moderate",
    },
    "plot_plan": {
        "chapter_number": 12,
        "chapter_goal": "让主角拿到父亲留下的档案，并意识到有人先来过。",
        "scenes": [
            {"scene_id": "12-1", "purpose": "进入黑塔地窖，建立压抑基调。"},
            {"scene_id": "12-2", "purpose": "发现档案被翻动，抛出悬念。"},
        ],
    },
    "idea_candidates": {
        "candidates": [_candidate(index) for index in range(10)],
    },
    "character_intent": {
        "character_id": "alice",
        "knowledge_scope": ["父亲失踪", "黑塔地窖的存在"],
        "motivation": "找到父亲留下的档案。",
        "reaction": "先保持沉默，随后逼近看守人追问。",
        "constraints": ["不知道父亲是黑塔的建造者"],
    },
    "scene_brief": {
        "scene_id": "34-2",
        "pov_character_id": "alice",
        "location_id": "black_tower_basement",
        "objective": "寻找父亲留下的档案。",
        "conflict": "发现有人先来过。",
        "required_facts": ["房间没有窗", "档案编号 K19"],
        "forbidden_events": ["揭示父亲身份", "出现魔法", "角色死亡"],
        "tone": ["压抑", "安静", "逐渐不安"],
        "target_words": 1800,
    },
    "chapter_draft": {
        "chapter_number": 12,
        "title": "地窖里的脚印",
        "text": "地窖里没有窗，只有一盏将要熄灭的灯。她数着台阶往下走，第七级是新的。",
        "word_count": 1820,
        "scene_ids": ["12-1", "12-2"],
    },
    "continuity_report": {
        "score": 0.82,
        "issues": [
            {
                "severity": "medium",
                "type": "prop_continuity",
                "description": "档案编号在上一章是 K19，本章写成 K91。",
                "location": "12-2 第 14 段",
                "evidence": "「编号 K91 的档案」",
            }
        ],
        "facts_checked": ["房间没有窗", "档案编号 K19"],
        "hard_failures": [],
    },
    "critic_report": {
        "scores": {
            "tension": 0.78,
            "pacing": 0.61,
            "characterization": 0.7,
            "prose": 0.74,
            "novelty": 0.55,
            "emotional_impact": 0.66,
            "continuity": 0.9,
        },
        "problems": [_critic_problem()],
    },
    "revision_instruction": {
        "chapter_number": 12,
        "instructions": ["补写主角发现档案被翻动后的即时反应。", "保留档案编号 K19 不变。"],
        "problems": [
            {
                "severity": "high",
                "location": "12-2 第 14 段",
                "type": "pacing",
                "description": "发现档案被翻动后没有任何反应描写，节奏塌陷。",
                "evidence": "「她看着空抽屉，然后离开了。」",
            }
        ],
        "preserve_facts": ["档案编号 K19"],
    },
    "style_edit_result": {
        "text": "地窖里没有窗。灯将熄未熄，她数着台阶往下走——第七级是新的。",
        "word_count": 1795,
        "fact_diff": {"added": [], "removed": [], "changed": ["台阶描写由概述改为细节"]},
        "style_notes": ["减少句子连接词，缩短句长以提升压迫感。"],
    },
    "canon_patch": {
        "operations": [
            {
                "op": "add",
                "entity_type": "location",
                "canonical_name": "黑塔地窖",
                "data": {
                    "description": "黑塔地下二层的石室，没有窗。",
                    "aliases": ["地窖"],
                    "tags": ["黑塔", "密室"],
                },
                "valid_from_chapter": 12,
            },
            {
                "op": "update",
                "entity_type": "fact",
                "canonical_name": "档案编号",
                "data": {"predicate": "编号", "object_value": "K19", "confidence": 0.9},
            },
        ],
        "rationale": "本章首次进入黑塔地窖，需要把地点与档案编号写入 Canon。",
    },
    "chapter_summary": {
        "chapter_number": 12,
        "summary": "主角进入黑塔地窖寻找父亲的档案，发现抽屉已被翻动，档案编号与记忆中不符。",
        "key_events": ["进入黑塔地窖", "发现档案被翻动"],
        "character_states": [
            {"character_id": "alice", "state": "警觉，开始怀疑看守人。"},
        ],
        "open_threads": ["谁先来过地窖"],
    },
}


def _invalid_director_decision() -> dict[str, Any]:
    return {
        "selected_candidate_id": "cand_07",
        "rationale": "看起来最刺激。",
        "risk_level": "reckless",  # 不在 safe|moderate|wild 枚举内
    }


def _invalid_plot_plan() -> dict[str, Any]:
    return {
        "chapter_number": 12,
        "chapter_goal": "让主角拿到档案。",
        "scenes": [],  # 违反 minItems: 1
    }


def _invalid_idea_candidates() -> dict[str, Any]:
    return {"candidates": [_candidate(index) for index in range(9)]}  # 少于 10 条


def _invalid_character_intent() -> dict[str, Any]:
    return {
        "character_id": "alice",
        "reaction": "先沉默，再追问。",
    }  # 缺少必需字段 motivation


def _invalid_scene_brief() -> dict[str, Any]:
    sample = dict(VALID_SAMPLES["scene_brief"])
    sample["target_words"] = 50  # 违反 minimum: 100
    return sample


def _invalid_chapter_draft() -> dict[str, Any]:
    return {
        "chapter_number": 12,
        "word_count": 1820,
    }  # 缺少必需字段 text


def _invalid_continuity_report() -> dict[str, Any]:
    sample = dict(VALID_SAMPLES["continuity_report"])
    sample["score"] = 1.4  # 超过 maximum: 1
    return sample


def _invalid_critic_report() -> dict[str, Any]:
    sample = json.loads(json.dumps(VALID_SAMPLES["critic_report"]))
    del sample["scores"]["continuity"]  # scores 缺少必需维度
    return sample


def _invalid_revision_instruction() -> dict[str, Any]:
    sample = json.loads(json.dumps(VALID_SAMPLES["revision_instruction"]))
    sample["rewrite_whole_chapter"] = True  # 违反 additionalProperties: false
    return sample


def _invalid_style_edit_result() -> dict[str, Any]:
    return {
        "text": "改写后的正文。",
        "fact_diff": {"added": [], "removed": []},  # 缺少必需键 changed
    }


def _invalid_canon_patch() -> dict[str, Any]:
    return {
        "operations": [
            {
                "op": "upsert",  # 不在 add|update|delete 枚举内
                "entity_type": "location",
                "canonical_name": "黑塔地窖",
            }
        ],
        "rationale": "补充地点设定。",
    }


def _invalid_chapter_summary() -> dict[str, Any]:
    return {
        "chapter_number": 12,
        "summary": "主角进入地窖。",
        "character_states": [{"character_id": "alice"}],  # 缺少必需字段 state
    }


INVALID_SAMPLES: dict[str, dict[str, Any]] = {
    "director_decision": _invalid_director_decision(),
    "plot_plan": _invalid_plot_plan(),
    "idea_candidates": _invalid_idea_candidates(),
    "character_intent": _invalid_character_intent(),
    "scene_brief": _invalid_scene_brief(),
    "chapter_draft": _invalid_chapter_draft(),
    "continuity_report": _invalid_continuity_report(),
    "critic_report": _invalid_critic_report(),
    "revision_instruction": _invalid_revision_instruction(),
    "style_edit_result": _invalid_style_edit_result(),
    "canon_patch": _invalid_canon_patch(),
    "chapter_summary": _invalid_chapter_summary(),
}


def test_artifact_type_list_covers_the_twelve_contracts() -> None:
    assert len(ARTIFACT_TYPES) == 12
    assert len(set(ARTIFACT_TYPES)) == 12
    assert set(VALID_SAMPLES) == set(ARTIFACT_TYPES)
    assert set(INVALID_SAMPLES) == set(ARTIFACT_TYPES)


def test_schema_directory_points_at_repository_schemas_artifacts() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    assert SCHEMA_DIR == repo_root / "schemas" / "artifacts"
    assert SCHEMA_DIR.is_dir()


@pytest.mark.parametrize("artifact_type", ARTIFACT_TYPES)
def test_schema_file_exists(artifact_type: str) -> None:
    path = _schema_path(artifact_type)
    assert path.is_file(), f"missing schema file: {path}"


@pytest.mark.parametrize("artifact_type", ARTIFACT_TYPES)
def test_schema_is_valid_draft_2020_12(artifact_type: str) -> None:
    schema = _load_schema(artifact_type)
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"] == f"https://novel-agent.local/schemas/artifacts/{artifact_type}.json"
    assert schema["title"] == artifact_type
    assert schema["type"] == "object"
    assert schema["required"], "every artifact schema must declare required fields"
    assert "schema_version" not in json.dumps(schema), "schema_version belongs to the artifact envelope"


@pytest.mark.parametrize("artifact_type", ARTIFACT_TYPES)
def test_schema_root_is_closed_and_self_contained(artifact_type: str) -> None:
    schema = _load_schema(artifact_type)
    assert schema["additionalProperties"] is False
    assert "$ref" not in _load_schema_text(artifact_type)


@pytest.mark.parametrize("artifact_type", ARTIFACT_TYPES)
def test_every_object_schema_is_closed(artifact_type: str) -> None:
    schema = _load_schema(artifact_type)
    for subschema in _iter_subschemas(schema):
        is_object_schema = subschema.get("type") == "object" or "properties" in subschema
        if is_object_schema:
            assert subschema.get("additionalProperties") is False, (
                f"{artifact_type}: object schema without additionalProperties: false -> "
                f"{sorted(subschema.get('properties', {}))}"
            )


@pytest.mark.parametrize("artifact_type", ARTIFACT_TYPES)
def test_valid_sample_passes(artifact_type: str) -> None:
    validator = Draft202012Validator(_load_schema(artifact_type))
    errors = sorted(validator.iter_errors(VALID_SAMPLES[artifact_type]), key=lambda e: list(e.path))
    assert not errors, f"{artifact_type} valid sample rejected: {[e.message for e in errors]}"


@pytest.mark.parametrize("artifact_type", ARTIFACT_TYPES)
def test_invalid_sample_is_rejected(artifact_type: str) -> None:
    validator = Draft202012Validator(_load_schema(artifact_type))
    errors = list(validator.iter_errors(INVALID_SAMPLES[artifact_type]))
    assert errors, f"{artifact_type} invalid sample unexpectedly validated"


def test_idea_candidates_sample_sits_on_the_min_items_boundary() -> None:
    assert len(VALID_SAMPLES["idea_candidates"]["candidates"]) == 10
    assert len(INVALID_SAMPLES["idea_candidates"]["candidates"]) == 9


def test_scene_brief_valid_sample_covers_every_required_field() -> None:
    schema = _load_schema("scene_brief")
    assert set(VALID_SAMPLES["scene_brief"]) == set(schema["required"])
