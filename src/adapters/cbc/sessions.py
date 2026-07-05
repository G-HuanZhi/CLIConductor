"""cbc session scanner and history parser.

Scans ~/.codebuddy/projects/ for resumable cbc sessions,
parses JSONL transcripts into CLIConductor history format.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path


def _project_dir(project_cwd: str | None) -> Path:
    """Return the cbc project directory for a given working directory.

    cbc sanitizes paths: D:\\project\\CLIConductor → d-project-CLIConductor.
    """
    base = Path(os.path.expanduser("~/.codebuddy/projects"))
    if project_cwd:
        # match cbc's sanitization: strip drive colon, lowercase,
        # replace \\ and / with -, collapse multiple -
        sanitized = project_cwd.replace(":", "").lower()
        sanitized = sanitized.replace("\\", "-").replace("/", "-")
        sanitized = re.sub(r"-+", "-", sanitized).strip("-")
        return base / sanitized
    return base


def list_cbc_sessions(project_cwd: str | None = None) -> list[dict]:
    """List resumable cbc sessions from ~/.codebuddy/projects/.

    Returns a list of dicts with keys: session_id, title, message_count,
    first_timestamp, last_timestamp, model, forked_from.
    """
    sessions: list[dict] = []
    proj_dir = _project_dir(project_cwd)
    if not proj_dir.exists():
        return sessions

    for fpath in sorted(proj_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if fpath.suffix != ".jsonl" or fpath.stem == "agent":
            continue
        # skip subagent directories
        if fpath.is_dir():
            continue

        session_id = fpath.stem
        meta = _read_meta(proj_dir, session_id)

        try:
            title, msg_count, first_ts, last_ts, model = _parse_summary(fpath)
        except Exception:
            continue

        sessions.append({
            "session_id": session_id,
            "project_dir": proj_dir.name,
            "title": title,
            "message_count": msg_count,
            "first_timestamp": first_ts,
            "last_timestamp": last_ts,
            "model": model,
            "forked_from": meta.get("forkedFrom"),
        })

    return sessions


def parse_cbc_history(session_id: str, project_cwd: str | None = None) -> list[dict]:
    """Parse cbc session JSONL into CLIConductor history format.

    Returns list of {"role": str, "content": str} blocks.
    """
    proj_dir = _project_dir(project_cwd)
    path = proj_dir / f"{session_id}.jsonl"
    if not path.exists():
        return []

    history: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            block = _event_to_block(event)
            if block:
                history.append(block)

    return history


# ── internals ──

def _read_meta(proj_dir: Path, session_id: str) -> dict:
    meta_path = proj_dir / f"{session_id}.meta.json"
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _parse_summary(fpath: Path) -> tuple[str, int, str, str, str]:
    """Extract title, count, timestamps and model from a JSONL file."""
    title = ""
    msg_count = 0
    first_ts = ""
    last_ts = ""
    model = ""

    with open(fpath, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_count += 1

            ts = event.get("timestamp")
            if ts and not first_ts:
                first_ts = _ts_to_iso(ts)
            if ts:
                last_ts = _ts_to_iso(ts)

            if not model and event.get("providerData", {}).get("model"):
                model = event["providerData"]["model"]

            if not title:
                if event.get("type") == "custom-title":
                    title = event.get("customTitle", "")
                elif event.get("type") == "message" and event.get("role") == "user":
                    content = event.get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") in ("input_text", "text"):
                                t = block.get("text", "").strip()
                                if t:
                                    title = t[:80]
                                    break

    return title, msg_count, first_ts, last_ts, model


def _ts_to_iso(ts: int) -> str:
    """Convert epoch ms to ISO string."""
    from datetime import datetime, timezone
    try:
        return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
    except (OSError, ValueError):
        return str(ts)


def _event_to_block(event: dict) -> dict | None:
    """Map a single cbc JSONL event to a CLIConductor history block."""
    etype = event.get("type")

    if etype == "message":
        role = event.get("role")
        msg = event.get("message", {})
        content_blocks = msg.get("content", [])
        if not isinstance(content_blocks, list):
            content_blocks = []

        if role == "user":
            text = "".join(
                block.get("text", "")
                for block in content_blocks
                if isinstance(block, dict) and block.get("type") in ("input_text", "text")
            )
            if text.strip():
                return {"role": "user", "content": text.strip()}
        elif role == "assistant":
            text = "".join(
                block.get("text", "")
                for block in content_blocks
                if isinstance(block, dict) and block.get("type") in ("text", "output_text")
            )
            if text.strip():
                return {"role": "assistant", "content": text.strip()}

    elif etype == "reasoning":
        content_blocks = event.get("content") or []
        if isinstance(content_blocks, list):
            text = "".join(
                block.get("text", "")
                for block in content_blocks
                if isinstance(block, dict)
            )
            if text.strip():
                return {"role": "thinking", "content": text.strip()}

    elif etype == "function_call":
        name = event.get("name", "?")
        args_raw = event.get("args") or event.get("input") or {}
        if isinstance(args_raw, dict):
            args_str = json.dumps(args_raw, ensure_ascii=False)[:500]
        else:
            args_str = str(args_raw)[:500]
        return {"role": "tool", "content": f"tool call: {name}\nargs: {args_str}"}

    elif etype == "function_call_result":
        name = event.get("name", "?")
        output = event.get("output", "")
        if isinstance(output, dict):
            output = output.get("text", str(output))
        if isinstance(output, str):
            output = output[:500]
        else:
            output = str(output)[:500]
        return {"role": "tool", "content": f"tool result ({name}):\n{output}"}

    return None
