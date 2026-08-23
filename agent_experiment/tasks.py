from dataclasses import dataclass


@dataclass(frozen=True)
class ResearchTask:
    id: str
    title: str
    prompt: str
    success_criteria: list[str]


TASKS: dict[str, ResearchTask] = {
    "agent_landscape": ResearchTask(
        id="agent_landscape",
        title="Lightweight Agent Stacks 2026",
        prompt="""Map lightweight agent stacks in 2026. Compare at least 4 frameworks
(LangGraph, smolagents, OpenAI Agents SDK, and at least one more), model sizes
(7B–30B), and inference providers (OpenRouter, Together, Groq, local/Ollama).

Deliver a structured report with:
1. Overview of frameworks and their strengths/weaknesses for lightweight agents
2. Comparison of model sizes (7B, 14B, 20B, 30B) for agent tasks
3. Cost estimates per typical research task (tokens + USD)
4. Concrete recommendation: when is 20–30B enough vs when is a frontier model needed?
5. Source citations (URLs) for all facts you cite

Use the tools to search and fetch information. Save important findings with
save_note as you work. Finish with submit_report when the report is complete.""",
        success_criteria=[
            "Covers at least 4 agent frameworks",
            "Compares model sizes 7B–30B",
            "Includes cost estimates with sources",
            "Provides actionable recommendation (20–30B vs frontier)",
            "Cites URLs for factual claims",
        ],
    ),
}


def get_task(task_id: str) -> ResearchTask:
    if task_id not in TASKS:
        available = ", ".join(TASKS.keys())
        raise ValueError(f"Unknown task '{task_id}'. Available: {available}")
    return TASKS[task_id]
