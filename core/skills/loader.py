"""
AgentOS Skill Loader — 3-Level Progressive Disclosure

Prevents context window overflow by loading skills on demand:

Level 1: Metadata only (~50 tokens per skill)
  -> Loaded at startup. 50 skills x 50 tokens = 2.5K tokens.
  -> Contains: name, description, triggers, MCP server refs

Level 2: Full SKILL.md instructions (~500-1000 tokens)
  -> Loaded when skill is triggered by query match
  -> Contains: step-by-step instructions, examples, constraints

Level 3: Scripts + resources
  -> Loaded only when executing the skill
  -> Contains: executable code, templates, data files
"""
from __future__ import annotations
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Optional
import re


class SkillMetadata(BaseModel):
    """Level 1: Lightweight skill metadata for trigger matching."""
    name: str
    description: str
    triggers: list[str] = Field(default_factory=list)
    mcp_servers: list[str] = Field(default_factory=list)
    priority: int = 0
    path: str = ""


class SkillInstructions(BaseModel):
    """Level 2: Full instructions loaded on trigger."""
    metadata: SkillMetadata
    instructions: str  # Full SKILL.md content
    examples: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class SkillFull(BaseModel):
    """Level 3: Complete skill with scripts and resources."""
    instructions: SkillInstructions
    scripts: dict[str, str] = Field(default_factory=dict)  # filename -> content
    resources: dict[str, str] = Field(default_factory=dict)  # filename -> content


class SkillLoader:
    """Progressive disclosure skill loader."""

    def __init__(self, skills_dir: str = "verticals"):
        self.skills_dir = Path(skills_dir)
        self._metadata_cache: dict[str, SkillMetadata] = {}

    def discover_skills(self) -> list[SkillMetadata]:
        """Level 1: Scan for SKILL.md files and extract metadata."""
        skills = []
        for skill_md in self.skills_dir.rglob("SKILL.md"):
            metadata = self._parse_skill_metadata(skill_md)
            if metadata:
                self._metadata_cache[metadata.name] = metadata
                skills.append(metadata)
        return skills

    def match_triggers(self, query: str) -> list[SkillMetadata]:
        """Find skills whose triggers match the query."""
        query_lower = query.lower()
        matched = []
        for skill in self._metadata_cache.values():
            for trigger in skill.triggers:
                if trigger.lower() in query_lower:
                    matched.append(skill)
                    break
        matched.sort(key=lambda s: s.priority, reverse=True)
        return matched

    def load_instructions(self, skill_name: str) -> Optional[SkillInstructions]:
        """Level 2: Load full SKILL.md content."""
        metadata = self._metadata_cache.get(skill_name)
        if not metadata or not metadata.path:
            return None

        skill_md_path = Path(metadata.path)
        if not skill_md_path.exists():
            return None

        content = skill_md_path.read_text()
        examples = re.findall(r'```example\n(.*?)```', content, re.DOTALL)
        constraints = re.findall(r'- \*\*Constraint\*\*: (.*)', content)

        return SkillInstructions(
            metadata=metadata,
            instructions=content,
            examples=examples,
            constraints=constraints,
        )

    def load_full(self, skill_name: str) -> Optional[SkillFull]:
        """Level 3: Load scripts and resources."""
        instructions = self.load_instructions(skill_name)
        if not instructions:
            return None

        skill_dir = Path(instructions.metadata.path).parent
        scripts = {}
        resources = {}

        for f in skill_dir.glob("scripts/*"):
            if f.is_file():
                scripts[f.name] = f.read_text()

        for f in skill_dir.glob("resources/*"):
            if f.is_file():
                resources[f.name] = f.read_text()

        return SkillFull(
            instructions=instructions,
            scripts=scripts,
            resources=resources,
        )

    def _parse_skill_metadata(self, skill_md: Path) -> Optional[SkillMetadata]:
        """Extract metadata from SKILL.md header."""
        try:
            content = skill_md.read_text()
            name_match = re.search(r'#\s+(.+)', content)
            desc_match = re.search(r'description:\s*(.+)', content, re.IGNORECASE)
            triggers_match = re.search(r'triggers:\s*\[(.+?)\]', content, re.IGNORECASE)

            name = name_match.group(1).strip() if name_match else skill_md.parent.name
            description = desc_match.group(1).strip() if desc_match else ""
            triggers = (
                [t.strip().strip('"\'') for t in triggers_match.group(1).split(",")]
                if triggers_match else []
            )

            return SkillMetadata(
                name=name.lower().replace(" ", "_"),
                description=description,
                triggers=triggers,
                path=str(skill_md),
            )
        except Exception:
            return None
