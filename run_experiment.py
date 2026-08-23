#!/usr/bin/env python3
"""Run lightweight vs frontier agent experiment."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from agent_experiment.config import MODELS, RUNS_DIR, get_api_key
from agent_experiment.metrics import MetricsLogger
from agent_experiment.runner import run_agent
from agent_experiment.tasks import get_task


def run_single(model_key: str, task_id: str) -> MetricsLogger:
    model_cfg = MODELS[model_key]
    task = get_task(task_id)
    print(f"\n{'='*60}")
    print(f"Running {model_cfg.label} ({model_cfg.slug})")
    print(f"Task: {task.title}")
    print(f"{'='*60}\n")

    logger = run_agent(
        model=model_cfg.slug,
        model_label=model_cfg.label,
        task=task,
        role=model_cfg.role,
    )

    metrics_path = logger.run_dir / "metrics.json"
    metrics = json.loads(metrics_path.read_text())
    print(f"\nDone: {metrics['completion_status']}")
    print(f"  Steps: {metrics['steps']}, Tool calls: {metrics['tool_calls']}")
    print(f"  Tokens: {metrics['tokens_in']} in / {metrics['tokens_out']} out")
    print(f"  Cost: ${metrics['total_cost_usd']:.4f}")
    print(f"  Time: {metrics['wall_time_sec']}s")
    print(f"  Output: {logger.run_dir}")
    return logger


def write_comparison(light_loggers: list[MetricsLogger], frontier_logger: MetricsLogger) -> Path:
    comparison_path = RUNS_DIR / "comparison.md"
    lines = [
        "# Lightweight vs Frontier — Comparison",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Metrics",
        "",
        "| Model | Status | Steps | Tool calls | Tokens (in/out) | Cost (USD) | Time (s) | Sources |",
        "|-------|--------|-------|------------|-----------------|------------|----------|---------|",
    ]

    all_loggers = light_loggers + [frontier_logger]
    for lg in all_loggers:
        m = json.loads((lg.run_dir / "metrics.json").read_text())
        lines.append(
            f"| {m['model_label']} | {m['completion_status']} | {m['steps']} | "
            f"{m['tool_calls']} | {m['tokens_in']}/{m['tokens_out']} | "
            f"${m['total_cost_usd']:.4f} | {m['wall_time_sec']} | {m['sources_cited']} |"
        )

    # Cost efficiency
    frontier_cost = json.loads((frontier_logger.run_dir / "metrics.json").read_text())[
        "total_cost_usd"
    ]
    lines.extend(["", "## Cost efficiency", ""])
    for lg in light_loggers:
        m = json.loads((lg.run_dir / "metrics.json").read_text())
        if m["total_cost_usd"] > 0:
            ratio = frontier_cost / m["total_cost_usd"]
            lines.append(
                f"- **{m['model_label']}**: {ratio:.1f}x cheaper than frontier "
                f"(${m['total_cost_usd']:.4f} vs ${frontier_cost:.4f})"
            )

    lines.extend(
        [
            "",
            "## Run directories",
            "",
        ]
    )
    for lg in all_loggers:
        lines.append(f"- `{lg.model_label}`: `{lg.run_dir}`")

    lines.extend(
        [
            "",
            "## Next step",
            "",
            "Run evaluation with frontier judge:",
            "```bash",
            f"python evaluate.py {light_loggers[0].run_dir} {frontier_logger.run_dir}",
            "```",
        ]
    )

    comparison_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nComparison written to {comparison_path}")
    return comparison_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Lightweight vs Frontier agent experiment")
    parser.add_argument(
        "--task",
        default="agent_landscape",
        help="Task ID from tasks.py (default: agent_landscape)",
    )
    parser.add_argument(
        "--include-alt",
        action="store_true",
        help="Also run gpt-oss-20b lightweight model",
    )
    parser.add_argument(
        "--only",
        choices=["lightweight", "lightweight_alt", "frontier"],
        help="Run only one model (for debugging)",
    )
    args = parser.parse_args()

    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        get_api_key()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        print("\nAdd OPENROUTER_API_KEY to .env or your environment secrets, then retry.", file=sys.stderr)
        return 1

    if args.only:
        run_single(args.only, args.task)
        return 0

    light_loggers = [run_single("lightweight", args.task)]
    if args.include_alt:
        light_loggers.append(run_single("lightweight_alt", args.task))
    frontier_logger = run_single("frontier", args.task)

    write_comparison(light_loggers, frontier_logger)
    return 0


if __name__ == "__main__":
    sys.exit(main())
