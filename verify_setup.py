#!/usr/bin/env python3
"""Verify experiment setup: tools, API key, and model availability."""

import json
import sys

from openai import OpenAI

from agent_experiment.config import (
    MODELS,
    OPENROUTER_BASE_URL,
    get_api_key,
)
from agent_experiment.tools import TOOL_SCHEMAS, web_search


def check_tools() -> bool:
    print("Checking tools...")
    result = json.loads(web_search("OpenRouter API pricing", max_results=2))
    count = len(result.get("results", []))
    if count == 0:
        print("  WARN: web_search returned 0 results (may be transient)")
    else:
        print(f"  OK: web_search returned {count} results")
    print(f"  OK: {len(TOOL_SCHEMAS)} tool schemas defined")
    return True


def check_api_key() -> bool:
    print("Checking API key...")
    try:
        key = get_api_key()
        print(f"  OK: OPENROUTER_API_KEY set ({key[:8]}...)")
        return True
    except RuntimeError as exc:
        print(f"  FAIL: {exc}")
        return False


def check_models() -> bool:
    print("Checking model availability on OpenRouter...")
    client = OpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=get_api_key(),
    )
    ok = True
    for key, cfg in MODELS.items():
        try:
            response = client.chat.completions.create(
                model=cfg.slug,
                messages=[{"role": "user", "content": "Reply with exactly: OK"}],
                max_tokens=10,
                tools=TOOL_SCHEMAS[:1],
            )
            reply = response.choices[0].message.content or "(tool call)"
            print(f"  OK: {cfg.label} ({cfg.slug}) — {reply[:40]}")
        except Exception as exc:
            print(f"  FAIL: {cfg.label} ({cfg.slug}) — {exc}")
            ok = False
    return ok


def main() -> int:
    tools_ok = check_tools()
    if not check_api_key():
        print("\nSetup incomplete. Add OPENROUTER_API_KEY to .env or environment secrets.")
        return 1
    models_ok = check_models()
    if tools_ok and models_ok:
        print("\nAll checks passed. Run: python run_experiment.py")
        return 0
    print("\nSome checks failed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
