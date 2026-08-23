#!/usr/bin/env python3
"""Evaluate agent reports with rubric scoring and frontier judge."""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

from agent_experiment.config import JUDGE_MODEL, OPENROUTER_BASE_URL, RUNS_DIR, get_api_key
from agent_experiment.metrics import count_verifiable_claims, extract_urls

RUBRIC_DIMENSIONS = [
    "task_coverage",
    "factual_accuracy",
    "source_citations",
    "actionable_recommendation",
    "limitations_awareness",
]

RUBRIC_DESCRIPTIONS = {
    "task_coverage": "Does the report cover frameworks, model sizes, costs, and recommendations?",
    "factual_accuracy": "Are facts (prices, model names, capabilities) plausible and consistent?",
    "source_citations": "Are claims backed by cited URLs?",
    "actionable_recommendation": "Is there a clear, usable recommendation for 20-30B vs frontier?",
    "limitations_awareness": "Does the report acknowledge uncertainty and limitations?",
}

JUDGE_PROMPT = """You are an impartial evaluator scoring research reports.

Score each dimension from 1 (poor) to 5 (excellent).

Dimensions:
1. task_coverage — {task_coverage}
2. factual_accuracy — {factual_accuracy}
3. source_citations — {source_citations}
4. actionable_recommendation — {actionable_recommendation}
5. limitations_awareness — {limitations_awareness}

Report to evaluate (label: {label}):
---
{report}
---

Respond with ONLY valid JSON in this exact format:
{{
  "task_coverage": <1-5>,
  "factual_accuracy": <1-5>,
  "source_citations": <1-5>,
  "actionable_recommendation": <1-5>,
  "limitations_awareness": <1-5>,
  "total": <sum of above>,
  "summary": "<2-3 sentence justification>"
}}"""


def load_run(run_path: Path) -> dict:
    run_path = run_path.resolve()
    metrics = json.loads((run_path / "metrics.json").read_text())
    report = (run_path / "report.md").read_text() if (run_path / "report.md").exists() else ""
    return {
        "path": run_path,
        "metrics": metrics,
        "report": report,
        "label": metrics.get("model_label", run_path.name),
    }


def judge_report(client: OpenAI, report: str, label: str) -> dict:
    prompt = JUDGE_PROMPT.format(
        label=label,
        report=report[:12000],
        **RUBRIC_DESCRIPTIONS,
    )
    response = client.chat.completions.create(
        model=JUDGE_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    content = response.choices[0].message.content or ""
    match = re.search(r"\{[\s\S]*\}", content)
    if not match:
        return {"error": "Failed to parse judge response", "raw": content}
    return json.loads(match.group())


def objective_metrics(report: str, run_metrics: dict) -> dict:
    urls = extract_urls(report)
    return {
        "sources_cited": len(urls),
        "fetched_urls": run_metrics.get("fetched_urls", 0),
        "report_length_chars": len(report),
        "verifiable_claims_estimate": count_verifiable_claims(report),
        "completion_status": run_metrics.get("completion_status"),
        "cost_usd": run_metrics.get("total_cost_usd"),
        "wall_time_sec": run_metrics.get("wall_time_sec"),
    }


def write_evaluation(
    runs: list[dict],
    scores: list[dict],
    output_path: Path,
) -> None:
    lines = [
        "# Evaluation Report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Judge model: `{JUDGE_MODEL}`",
        "",
        "## Rubric Scores (1-5 per dimension)",
        "",
        "| Model | Coverage | Facts | Sources | Recommendation | Limitations | **Total** |",
        "|-------|----------|-------|---------|----------------|-------------|-----------|",
    ]

    for run, score in zip(runs, scores):
        if "error" in score:
            lines.append(f"| {run['label']} | ERROR | - | - | - | - | - |")
            continue
        lines.append(
            f"| {run['label']} | {score['task_coverage']} | {score['factual_accuracy']} | "
            f"{score['source_citations']} | {score['actionable_recommendation']} | "
            f"{score['limitations_awareness']} | **{score['total']}/25** |"
        )

    lines.extend(["", "## Judge Summaries", ""])
    for run, score in zip(runs, scores):
        lines.append(f"### {run['label']}")
        if "error" in score:
            lines.append(f"Error: {score['error']}")
        else:
            lines.append(score.get("summary", ""))
        lines.append("")

    lines.extend(["", "## Objective Metrics", ""])
    for run in runs:
        obj = objective_metrics(run["report"], run["metrics"])
        lines.append(f"### {run['label']}")
        lines.append(f"- Completion: {obj['completion_status']}")
        lines.append(f"- Cost: ${obj['cost_usd']:.4f}")
        lines.append(f"- Time: {obj['wall_time_sec']}s")
        lines.append(f"- Sources cited: {obj['sources_cited']}")
        lines.append(f"- URLs fetched during run: {obj['fetched_urls']}")
        lines.append(f"- Report length: {obj['report_length_chars']} chars")
        lines.append("")

    if len(scores) >= 2 and "total" in scores[0] and "total" in scores[1]:
        light_total = scores[0]["total"]
        frontier_total = scores[1]["total"]
        light_cost = runs[0]["metrics"]["total_cost_usd"]
        frontier_cost = runs[1]["metrics"]["total_cost_usd"]
        pct = (light_total / frontier_total * 100) if frontier_total else 0
        cost_ratio = (frontier_cost / light_cost) if light_cost > 0 else 0

        lines.extend(
            [
                "## Key Insight",
                "",
                f"- Lightweight scored **{pct:.0f}%** of frontier quality ({light_total}/25 vs {frontier_total}/25)",
                f"- Frontier cost **{cost_ratio:.1f}x** lightweight (${frontier_cost:.4f} vs ${light_cost:.4f})",
                "",
            ]
        )
        if pct >= 70 and cost_ratio >= 5:
            lines.append(
                "> **Hypothesis supported:** Lightweight reaches ~70%+ quality at a fraction of the cost. "
                "Specific knowledge (tools + structured task) partially compensates for scale."
            )
        elif pct < 70:
            lines.append(
                "> **Scale wins:** Lightweight falls short on quality. Frontier model depth matters for this research task."
            )
        else:
            lines.append(
                "> **Mixed result:** Quality gap is moderate; cost savings may or may not justify the trade-off."
            )

    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate agent experiment runs")
    parser.add_argument("lightweight_run", type=Path, help="Path to lightweight run directory")
    parser.add_argument("frontier_run", type=Path, help="Path to frontier run directory")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=RUNS_DIR / "evaluation.md",
        help="Output evaluation markdown path",
    )
    args = parser.parse_args()

    runs = [load_run(args.lightweight_run), load_run(args.frontier_run)]

    for run in runs:
        if not run["report"]:
            print(f"Warning: No report.md in {run['path']}", file=sys.stderr)

    client = OpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=get_api_key(),
        default_headers={
            "HTTP-Referer": "https://github.com/agent-experiment",
            "X-Title": "Agent Experiment Evaluator",
        },
    )

    print("Judging reports with frontier model...")
    scores = []
    for run in runs:
        print(f"  Evaluating {run['label']}...")
        score = judge_report(client, run["report"], run["label"])
        scores.append(score)
        if "total" in score:
            print(f"    Score: {score['total']}/25")

    write_evaluation(runs, scores, args.output)
    print(f"\nEvaluation written to {args.output}")

    eval_json = args.output.with_suffix(".json")
    eval_json.write_text(
        json.dumps(
            {
                "runs": [str(r["path"]) for r in runs],
                "scores": scores,
                "judge_model": JUDGE_MODEL,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"JSON scores: {eval_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
