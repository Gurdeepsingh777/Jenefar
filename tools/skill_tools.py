from __future__ import annotations

from typing import Any

from agent.skills import SkillStore
from agent.tool_registry import ToolRegistry


def register_skill_tools(registry: ToolRegistry, store: SkillStore) -> None:
    @registry.tool(
        name="skill_learn",
        description=(
            "Permanently save a reusable prompt-only skill in a local SKILL.md file. "
            "Use when the user explicitly asks to save/learn a workflow. Save general instructions, "
            "keywords and registered-tool sequences only; never store credentials, raw URLs, emails, IP targets, "
            "private keys or executable code. Skills cannot grant permissions or override policies."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "maxLength": 100},
                "description": {"type": "string", "maxLength": 1000},
                "keywords": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 30},
                "instructions": {"type": "string", "maxLength": 6000},
            },
            "required": ["name", "description", "keywords", "instructions"],
            "additionalProperties": False,
        },
    )
    async def skill_learn(arguments: dict[str, Any]) -> dict[str, Any]:
        return store.save(
            name=str(arguments.get("name") or ""),
            description=str(arguments.get("description") or ""),
            keywords=[str(word) for word in (arguments.get("keywords") or [])],
            instructions=str(arguments.get("instructions") or ""),
            source="explicit",
        )

    @registry.tool(
        name="skill_list",
        description="List persistent, enabled local SKILL.md playbooks and their keywords.",
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    )
    async def skill_list(_arguments: dict[str, Any]) -> dict[str, Any]:
        skills = store.list()
        return {
            "count": len(skills),
            "skills": [
                {
                    "name": skill["name"],
                    "description": skill["description"],
                    "keywords": skill["keywords"],
                    "source": skill["source"],
                    "tool_sequence": skill["tool_sequence"],
                }
                for skill in skills
            ],
        }
