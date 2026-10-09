from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
import yaml

from novel_agent.core.config import Settings
from novel_agent.core.errors import APIError
from novel_agent.projects.filesystem import ProjectFilesystem


def test_project_initialization_creates_spec_tree_and_git_commit(tmp_path: Path) -> None:
    filesystem = ProjectFilesystem(Settings(projects_root=str(tmp_path)))
    project_id = uuid4()
    root = filesystem.initialize(
        project_id=project_id,
        slug="demo-novel",
        name="Demo Novel",
        kind="sandbox",
        preset_version_id=None,
    )

    expected_files = {
        "project.yaml",
        ".gitignore",
        "canon/world.md",
        "canon/rules.yaml",
        "canon/facts.yaml",
        "plot/ending.md",
        "plot/arcs.yaml",
        "plot/rolling_plan.yaml",
        "timeline/events.yaml",
        "mysteries/threads.yaml",
        "characters/.gitkeep",
        "locations/.gitkeep",
        "chapters/.gitkeep",
        "artifacts/.gitkeep",
        "snapshots/.gitkeep",
    }
    assert {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    } == expected_files
    manifest = yaml.safe_load((root / "project.yaml").read_text(encoding="utf-8"))
    assert manifest["project_id"] == str(project_id)
    assert manifest["kind"] == "sandbox"

    commit = filesystem.commit_manifest(root, "test: no-op manifest commit")
    assert len(commit) == 40


def test_slugify_and_path_guard() -> None:
    assert ProjectFilesystem.slugify("  Hello, World! ") == "hello-world"
    assert ProjectFilesystem.slugify("!!!", fallback_id=uuid4()).startswith("project-")

    filesystem = ProjectFilesystem(Settings(projects_root="/tmp/novel-project-root"))
    with pytest.raises(APIError) as error:
        filesystem.path_for_slug("../outside")
    assert error.value.code == "PROJECT_PATH_INVALID"
