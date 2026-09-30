from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class TaskStep:
    """One bounded step in a hierarchical execution plan."""

    id: str
    title: str
    instruction: str
    agent: str
    depends_on: tuple[str, ...] = ()
    requires_action: bool = False
    verification: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TaskPlan:
    """A deterministic top-level plan plus ordered dependent subtasks."""

    goal: str
    intent: str
    agent: str
    strategy: str
    steps: tuple[TaskStep, ...] = field(default_factory=tuple)

    @property
    def is_compound(self) -> bool:
        return len(self.steps) > 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "intent": self.intent,
            "agent": self.agent,
            "strategy": self.strategy,
            "is_compound": self.is_compound,
            "steps": [step.as_dict() for step in self.steps],
        }

    def prompt_text(self) -> str:
        lines = [
            f"Execution strategy: {self.strategy}",
            "Follow this bounded plan in order and verify each completed action:",
        ]
        for index, step in enumerate(self.steps, start=1):
            dependencies = (
                f"; after {', '.join(step.depends_on)}"
                if step.depends_on
                else ""
            )
            flags = []
            if step.requires_action:
                flags.append("approval/action")
            if step.verification:
                flags.append("verify")
            suffix = f" [{', '.join(flags)}]" if flags else ""
            lines.append(
                f"{index}. {step.id}: {step.title} — {step.instruction}"
                f"{dependencies}{suffix}"
            )
        return "\n".join(lines)


class HierarchicalTaskPlanner:
    """Deterministic task decomposition used before the LLM executes tools."""

    def build(self, text: str, intent: str, agent: str) -> TaskPlan:
        task = text.strip()

        if agent == "local_development":
            lowered = task.lower()
            needs_repair = any(
                token in lowered
                for token in (
                    "fix", "error", "bug", "broken", "not working",
                    "add a feature", "implement", "modify", "change",
                )
            )
            if needs_repair:
                steps = (
                    TaskStep(
                        "inspect",
                        "Inspect the target",
                        "Read the target file and relevant local context before editing.",
                        "local_development",
                    ),
                    TaskStep(
                        "baseline",
                        "Run a baseline check",
                        "Validate syntax and run the target or relevant tests to capture the current failure.",
                        "local_development",
                        ("inspect",),
                        True,
                        True,
                    ),
                    TaskStep(
                        "diagnose",
                        "Diagnose the failure",
                        "Use the traceback, test output, and inspected code to identify the smallest correct fix.",
                        "local_development",
                        ("baseline",),
                    ),
                    TaskStep(
                        "repair",
                        "Apply the repair",
                        "Edit only the authorized workspace file(s), create backups, and keep the diff focused.",
                        "local_development",
                        ("diagnose",),
                        True,
                    ),
                    TaskStep(
                        "retest",
                        "Retest and self-heal",
                        "Run validation/tests again. If a new failure appears, repeat diagnosis and repair up to the configured attempt limit.",
                        "local_development",
                        ("repair",),
                        True,
                        True,
                    ),
                    TaskStep(
                        "report",
                        "Verify final state",
                        "Review the final result and diff, then report exactly what changed and what passed or failed.",
                        "local_development",
                        ("retest",),
                        False,
                        True,
                    ),
                )
            else:
                steps = (
                    TaskStep(
                        "inspect",
                        "Inspect the target",
                        "Read the requested local file/folder and establish its current state.",
                        "local_development",
                    ),
                    TaskStep(
                        "execute",
                        "Execute the requested local check",
                        "Run the requested Python program or validation only inside the authorized workspace.",
                        "local_development",
                        ("inspect",),
                        True,
                        True,
                    ),
                    TaskStep(
                        "report",
                        "Report verified results",
                        "Summarize the observed output, errors, and next state without inventing success.",
                        "local_development",
                        ("execute",),
                        False,
                        True,
                    ),
                )
            return TaskPlan(
                task,
                intent,
                agent,
                "bounded inspect → execute/repair → verify workflow",
                steps,
            )

        if agent == "gui_vision":
            steps = (
                TaskStep(
                    "observe",
                    "Observe the current screen",
                    "Use semantic vision to identify visible UI elements relevant to the user's goal.",
                    "gui_vision",
                    (),
                    True,
                    True,
                ),
                TaskStep(
                    "act",
                    "Perform the approved semantic action",
                    "Use semantic click/type/hotkey/scroll tools rather than guessed coordinates.",
                    "gui_vision",
                    ("observe",),
                    True,
                ),
                TaskStep(
                    "verify",
                    "Verify the GUI state",
                    "Re-observe the screen when the task changes visible state and report the confirmed result.",
                    "gui_vision",
                    ("act",),
                    True,
                    True,
                ),
            )
            return TaskPlan(
                task,
                intent,
                agent,
                "observe → semantic action → visual verification",
                steps,
            )

        if agent == "repository":
            steps = (
                TaskStep(
                    "inspect_repo",
                    "Inspect repository",
                    "Understand repository structure, entrypoints, tests, and relevant files.",
                    "repository",
                ),
                TaskStep(
                    "plan_change",
                    "Plan the change",
                    "Identify the smallest affected files, dependencies, risks, and verification checks.",
                    "repository",
                    ("inspect_repo",),
                ),
                TaskStep(
                    "verify",
                    "Verify evidence",
                    "Use repository evidence and available tests/checks before presenting the result.",
                    "repository",
                    ("plan_change",),
                    False,
                    True,
                ),
            )
            return TaskPlan(
                task,
                intent,
                agent,
                "repository discovery → scoped change plan → verification",
                steps,
            )

        if agent in {"kali", "cybersecurity", "bugbounty"}:
            steps = (
                TaskStep(
                    "scope",
                    "Confirm scope",
                    "Check that the requested target and action are within configured authorization.",
                    agent,
                    (),
                    False,
                    True,
                ),
                TaskStep(
                    "inspect",
                    "Gather bounded evidence",
                    "Use only the relevant approved security tooling and collect evidence needed for the task.",
                    agent,
                    ("scope",),
                    True,
                ),
                TaskStep(
                    "analyze",
                    "Analyze findings",
                    "Interpret tool output without escalating beyond the requested and authorized scope.",
                    agent,
                    ("inspect",),
                    False,
                    True,
                ),
            )
            return TaskPlan(
                task,
                intent,
                agent,
                "scope → bounded evidence collection → analysis",
                steps,
            )

        if agent == "utility":
            steps = (
                TaskStep(
                    "understand",
                    "Understand the persistent utility request",
                    "Determine whether the user requested memory storage/recall, a scheduler entry, or an application-event watcher.",
                    "utility",
                ),
                TaskStep(
                    "act",
                    "Apply the requested persistent change",
                    "Use the bounded memory or event tools. Do not execute stored procedures merely because they were recalled.",
                    "utility",
                    ("understand",),
                    True,
                ),
                TaskStep(
                    "verify",
                    "Verify persistence",
                    "Read back the created memory/procedure/event record and report the confirmed state.",
                    "utility",
                    ("act",),
                    False,
                    True,
                ),
            )
            return TaskPlan(
                task,
                intent,
                agent,
                "understand → persistent action → verify",
                steps,
            )

        if agent == "research":
            steps = (
                TaskStep(
                    "retrieve",
                    "Retrieve evidence",
                    "Gather relevant local memory or public online sources.",
                    "research",
                ),
                TaskStep(
                    "synthesize",
                    "Synthesize",
                    "Cross-check the retrieved evidence and distinguish facts from uncertainty.",
                    "research",
                    ("retrieve",),
                    False,
                    True,
                ),
            )
            return TaskPlan(
                task,
                intent,
                agent,
                "evidence retrieval → synthesis",
                steps,
            )

        return TaskPlan(
            task,
            intent,
            agent,
            "single specialist execution",
            (
                TaskStep(
                    "execute",
                    "Execute the specialist task",
                    "Complete the requested task using the specialist's available tools and verify the result.",
                    agent,
                    (),
                    False,
                    True,
                ),
            ),
        )


__all__ = ["TaskStep", "TaskPlan", "HierarchicalTaskPlanner"]
