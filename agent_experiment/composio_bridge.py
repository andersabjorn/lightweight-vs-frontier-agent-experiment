"""Bridge to Composio OpenRouter proxy_execute via local subprocess helper.

When running inside Cursor with Composio MCP, the agent orchestrator calls
proxy_execute directly. This module supports a file-based bridge for local
runner integration when COMPOSIO_BRIDGE_DIR is set.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any


def composio_proxy_chat(
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    temperature: float,
    session_id: str = "",
) -> dict[str, Any]:
    bridge_dir = os.environ.get("COMPOSIO_BRIDGE_DIR")
    if bridge_dir:
        return _file_bridge_request(
            bridge_dir=Path(bridge_dir),
            model=model,
            messages=messages,
            tools=tools,
            temperature=temperature,
        )
    raise RuntimeError(
        "Composio backend requires COMPOSIO_BRIDGE_DIR for local runs, "
        "or run via run_composio_workbench.py in Composio workbench."
    )


def _file_bridge_request(
    *,
    bridge_dir: Path,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    temperature: float,
) -> dict[str, Any]:
    bridge_dir.mkdir(parents=True, exist_ok=True)
    req_id = uuid.uuid4().hex
    req_path = bridge_dir / f"req_{req_id}.json"
    resp_path = bridge_dir / f"resp_{req_id}.json"

    req_path.write_text(
        json.dumps(
            {
                "model": model,
                "messages": messages,
                "tools": tools,
                "temperature": temperature,
            }
        ),
        encoding="utf-8",
    )

    for _ in range(120):
        if resp_path.exists():
            data = json.loads(resp_path.read_text(encoding="utf-8"))
            req_path.unlink(missing_ok=True)
            resp_path.unlink(missing_ok=True)
            if "error" in data:
                raise RuntimeError(data["error"])
            return data
        time.sleep(0.5)

    raise TimeoutError("Composio bridge timed out waiting for response")
