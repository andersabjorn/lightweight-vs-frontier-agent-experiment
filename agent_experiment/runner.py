import json
from typing import Any

from openai import OpenAI

from agent_experiment.config import (
    MAX_STEPS,
    OPENROUTER_BASE_URL,
    TEMPERATURE,
    get_api_key,
)
from agent_experiment.metrics import MetricsLogger
from agent_experiment.tasks import ResearchTask
from agent_experiment.tools import TOOL_SCHEMAS, ToolExecutor

SYSTEM_PROMPT = """You are a research agent. Your job is to complete the assigned research task
using the available tools.

Workflow:
1. Use web_search to find relevant sources
2. Use fetch_url to read promising pages in detail
3. Use save_note to record key findings with source URLs
4. When you have enough information, call submit_report with a complete markdown report

Rules:
- Always cite source URLs in your report
- Be factual; if uncertain, say so
- Do not invent prices or model names — verify via tools
- The report must be in markdown with clear sections
- Call submit_report exactly once when done"""


def _message_to_dict(msg: Any) -> dict[str, Any]:
    data: dict[str, Any] = {"role": msg.role}
    if msg.content is not None:
        data["content"] = msg.content
    if msg.tool_calls:
        data["tool_calls"] = [
            {
                "id": tc.id,
                "type": tc.type,
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in msg.tool_calls
        ]
    return data


def run_agent(
    model: str,
    model_label: str,
    task: ResearchTask,
    role: str = "lightweight",
) -> MetricsLogger:
    client = OpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=get_api_key(),
        default_headers={
            "HTTP-Referer": "https://github.com/agent-experiment",
            "X-Title": "Lightweight vs Frontier Agent Experiment",
        },
    )

    logger = MetricsLogger.create(model=model, model_label=model_label, task_id=task.id)
    executor = ToolExecutor(logger)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task.prompt},
    ]

    logger.log_trace("start", {"model": model, "task": task.id, "prompt": task.prompt[:200]})

    status = "max_steps"
    try:
        for step in range(MAX_STEPS):
            logger.record_step()
            logger.log_trace("llm_request", {"step": step + 1, "message_count": len(messages)})

            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                temperature=TEMPERATURE,
            )

            choice = response.choices[0]
            message = choice.message
            logger.record_llm_usage(response.usage, model)
            logger.log_trace(
                "llm_response",
                {
                    "step": step + 1,
                    "finish_reason": choice.finish_reason,
                    "has_tool_calls": bool(message.tool_calls),
                },
            )

            messages.append(_message_to_dict(message))

            if not message.tool_calls:
                # Model responded without tools — nudge it
                if executor.report_submitted:
                    status = "success"
                    break
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Continue research or call submit_report with your final markdown report."
                        ),
                    }
                )
                continue

            for tool_call in message.tool_calls:
                fn = tool_call.function
                result = executor.execute(fn.name, fn.arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    }
                )

                if executor.report_submitted:
                    status = "success"
                    break

            if executor.report_submitted:
                break
    except Exception as exc:
        status = "error"
        logger.log_trace("error", {"message": str(exc)})
        raise
    finally:
        logger.finish(status)
        logger.write_latest_symlink(role)

    return logger
