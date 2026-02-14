"""Test skill loader."""
import pytest
from pathlib import Path
from core.skills.loader import SkillLoader, SkillMetadata


def test_skill_loader_discover(tmp_path):
    """Test skill discovery from SKILL.md files."""
    skill_dir = tmp_path / "test_vertical"
    skill_dir.mkdir()
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text("""# Test Skill

description: A test skill for unit testing
triggers: ["test", "demo"]
mcp_servers: ["test-server"]
priority: 5
""")

    loader = SkillLoader(str(tmp_path))
    skills = loader.discover_skills()
    assert len(skills) == 1
    assert skills[0].name == "test_skill"
    assert skills[0].triggers == ["test", "demo"]


def test_skill_trigger_matching(tmp_path):
    """Test trigger matching."""
    skill_dir = tmp_path / "task_skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("""# Task Manager

description: Manage tasks
triggers: ["task", "todo", "assign"]
""")

    loader = SkillLoader(str(tmp_path))
    loader.discover_skills()

    matched = loader.match_triggers("Create a new task")
    assert len(matched) == 1
    assert matched[0].name == "task_manager"

    no_match = loader.match_triggers("What is the weather?")
    assert len(no_match) == 0


def test_skill_load_instructions(tmp_path):
    """Test Level 2 instruction loading."""
    skill_dir = tmp_path / "demo"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("""# Demo Skill

description: Demo
triggers: ["demo"]

---

## Instructions

1. Do step one
2. Do step two

## Constraints

- **Constraint**: Always validate input
- **Constraint**: Never exceed rate limits
""")

    loader = SkillLoader(str(tmp_path))
    loader.discover_skills()

    instructions = loader.load_instructions("demo_skill")
    assert instructions is not None
    assert "Do step one" in instructions.instructions
    assert len(instructions.constraints) == 2


def test_skill_load_full(tmp_path):
    """Test Level 3 full loading with scripts."""
    skill_dir = tmp_path / "full_skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("""# Full Skill
description: Full test
triggers: ["full"]
""")
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "run.py").write_text("print('hello')")

    loader = SkillLoader(str(tmp_path))
    loader.discover_skills()

    full = loader.load_full("full_skill")
    assert full is not None
    assert "run.py" in full.scripts
    assert full.scripts["run.py"] == "print('hello')"
