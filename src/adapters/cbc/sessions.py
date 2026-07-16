"""cbc session scanner and history parser.

Scans ~/.codebuddy/projects/ for resumable cbc sessions,
parses JSONL transcripts into CLIConductor history format.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta
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


def list_cbc_sessions(project_cwd: str | None = None, *, project_dir: str | None = None) -> list[dict]:
    """List resumable cbc sessions from ~/.codebuddy/projects/.

    project_cwd: filesystem path → auto-sanitize to cbc project dir
    project_dir:  cbc project dir name directly (e.g. "d-project-CLIConductor")

    Returns a list of dicts with keys: session_id, title, message_count,
    first_timestamp, last_timestamp, model, forked_from.
    """
    sessions: list[dict] = []
    if project_dir:
        proj_dir = Path(os.path.expanduser("~/.codebuddy/projects")) / project_dir
    else:
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




def list_cbc_projects(recent_days: int = 0, min_resume_bytes: int = 0) -> list[dict]:
    """Scan ~/.codebuddy/projects/ and return available project directories.

    recent_days: only include sessions modified within this many days (0 = no filter).
    min_resume_bytes: file must be at least this size to count as resumable.
    Returns list of dicts with keys: project_dir, session_count, resumable_count,
    path_hint, drive, short_label. Projects with 0 resumable sessions are excluded.
    """
    base = Path(os.path.expanduser("~/.codebuddy/projects"))
    if not base.exists():
        return []

    cutoff = datetime.now() - timedelta(days=recent_days) if recent_days > 0 else None

    projects: list[dict] = []
    for child in sorted(base.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not child.is_dir():
            continue
        total_count = 0
        resumable_count = 0
        for f in child.iterdir():
            if f.suffix == ".jsonl" and f.stem != "agent" and f.is_file():
                total_count += 1
                if cutoff and datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                    continue
                if _can_resume(f, min_resume_bytes):
                    resumable_count += 1
        if resumable_count == 0:
            continue

        drive, short_label = _parse_project_label(child.name)

        projects.append({
            "project_dir": child.name,
            "session_count": total_count,
            "resumable_count": resumable_count,
            "path_hint": _project_dir_to_path(child.name),
            "drive": drive,
            "short_label": short_label,
        })

    return projects


def _parse_project_label(dir_name: str) -> tuple[str, str]:
    """Extract drive letter and short label from sanitized project name.

    e.g. d-project-CLIConductor → ("D:", "CLIConductor")
         d-obisidian_plugin    → ("D:", "obisidian_plugin")
    """
    parts = dir_name.split("-")
    if not parts:
        return ("", dir_name)
    drive = parts[0].upper() + ":"
    # Take everything after the drive letter as the short label
    short_label = "-".join(parts[1:]) if len(parts) >= 2 else dir_name
    if not short_label:
        short_label = dir_name
    return drive, short_label


def _project_dir_to_path(dir_name: str) -> str:
    """Reverse cbc's sanitization to create a reasonable path hint.

    e.g. d-project-CLIConductor → D:/project/CLIConductor (best guess).
    """
    parts = dir_name.split("-")
    if not parts:
        return ""
    # Reconstruct: first part starts with drive letter, rest join with /
    drive = parts[0] + ":"  # e.g. "d:"
    rest = "/".join(parts[1:])
    return (drive + "/" + rest).upper()


def project_dir_to_path(dir_name: str) -> str | None:
    """Public wrapper: reverse cbc project dir sanitization to a best-guess filesystem path.

    e.g. "d-project-CLIConductor" → "D:/project/CLIConductor"
    Returns None when reverse can't produce a meaningful path.
    """
    result = _project_dir_to_path(dir_name)
    return result if result else None


def parse_cbc_history(session_id: str, project_cwd: str | None = None, *, project_dir: str | None = None) -> list[dict]:
    """Parse cbc session JSONL into CLIConductor history format.

    project_cwd: filesystem path → auto-sanitize to cbc project dir
    project_dir:  cbc project dir name directly (e.g. "d-project-CLIConductor")

    Returns list of {"role": str, "content": str} blocks.
    """
    if project_dir:
        proj_dir = Path(os.path.expanduser("~/.codebuddy/projects")) / project_dir
    else:
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


def get_raw_usage(session_id: str, project_cwd: str | None = None, *, project_dir: str | None = None) -> list[dict]:
    """Extract rawUsage info from all assistant messages in a cbc session.

    project_cwd: filesystem path → auto-sanitize to cbc project dir
    project_dir:  cbc project dir name directly (e.g. "d-project-CLIConductor")

    Returns list of dicts, each containing rawUsage from one assistant message:
        {"model": str, "rawUsage": dict, "timestamp": str}
    """
    if project_dir:
        proj_dir = Path(os.path.expanduser("~/.codebuddy/projects")) / project_dir
    else:
        proj_dir = _project_dir(project_cwd)
    path = proj_dir / f"{session_id}.jsonl"
    if not path.exists():
        return []

    usage_entries: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if event.get("type") != "message" or event.get("role") != "assistant":
                continue

            pd = event.get("providerData", {})
            raw_usage = pd.get("rawUsage")
            if not raw_usage:
                continue

            usage_entries.append({
                "model": pd.get("model", ""),
                "rawUsage": raw_usage,
                "timestamp": _ts_to_iso(event.get("timestamp", 0)),
            })

    return usage_entries


# ── internals ──

def _read_meta(proj_dir: Path, session_id: str) -> dict:
    meta_path = proj_dir / f"{session_id}.meta.json"
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _can_resume(fpath: Path, min_bytes: int = 0) -> bool:
    """Quick check: is this JSONL large enough to be a valid session?"""
    try:
        return fpath.stat().st_size >= (min_bytes or 1)
    except OSError:
        return False


def _parse_summary(fpath: Path) -> tuple[str, int, str, str, str]:
    """Extract title, count, timestamps and model from a JSONL file."""
    custom_title = ""
    ai_title = ""
    user_title = ""
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

            # Title priority: custom-title > ai-title > user message
            # Track explicitly set titles separately from the user-message
            # fallback so they can override it even when appearing later.
            etype = event.get("type")
            if etype == "custom-title":
                custom_title = _strip_html(event.get("customTitle", ""))
            elif etype == "ai-title" and not custom_title:
                ai_title = _strip_html(event.get("aiTitle", ""))
            elif not user_title and etype == "message" and event.get("role") == "user":
                content = event.get("content") or []
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") in ("input_text", "text"):
                            t = block.get("text", "").strip()
                            if t:
                                user_title = _strip_html(t)[:80]
                                break

    return custom_title or ai_title or user_title, msg_count, first_ts, last_ts, model


def get_session_title(session_id: str, cwd: str | None = None,
                      project_dir: str | None = None) -> str:
    """Extract the title that cbc assigned to a session (custom-title > ai-title)."""
    if project_dir:
        proj_dir = Path(os.path.expanduser("~/.codebuddy/projects")) / project_dir
    elif cwd:
        proj_dir = _project_dir(cwd)
    else:
        return ""
    path = proj_dir / f"{session_id}.jsonl"
    if not path.exists():
        return ""
    title, _, _, _, _ = _parse_summary(path)
    return title


def write_custom_title(session_id: str, title: str, cwd: str | None = None):
    """Write a custom-title event to a cbc session's JSONL file."""
    proj_dir = _project_dir(cwd)
    path = proj_dir / f"{session_id}.jsonl"
    if not path.exists():
        return
    import uuid
    event = {
        "id": str(uuid.uuid4()),
        "timestamp": int(time.time() * 1000),
        "type": "custom-title",
        "customTitle": title,
        "sessionId": session_id,
        "cwd": cwd or "",
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _strip_html(text: str) -> str:
    """Remove HTML tags and system-reminder markers from text."""
    text = re.sub(r"<[^>]*>", "", text)
    return text


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
        # Content is at event["content"] directly (newer cbc format).
        # Fall back to event["message"]["content"] for older sessions.
        content_blocks = event.get("content") or []
        if not content_blocks:
            msg = event.get("message", {})
            content_blocks = msg.get("content", [])
        if not isinstance(content_blocks, list):
            content_blocks = []

        if role == "user":
            text = "".join(
                block.get("text", "")
                for block in content_blocks
                if isinstance(block, dict) and block.get("type") in ("input_text", "text", "user")
            )
            if text.strip():
                return {"role": "user", "content": text.strip()}
        elif role == "assistant":
            text = "".join(
                block.get("text", "")
                for block in content_blocks
                if isinstance(block, dict) and block.get("type") in ("text", "output_text", "assistant")
            )
            if text.strip():
                return {"role": "assistant", "content": text.strip()}

    elif etype == "reasoning":
        # Newer cbc stores reasoning in rawContent, fall back to content
        content_blocks = event.get("rawContent") or event.get("content") or []
        if isinstance(content_blocks, list):
            text = "".join(
                block.get("text", "")
                for block in content_blocks
                if isinstance(block, dict)
            )
            if text.strip():
                return {"role": "thinking", "content": text.strip()}

    elif etype == "function_call":
        # Same format as adapter.extract_assistant_blocks tool_use
        name = event.get("name", "?")
        args_raw = event.get("arguments") or event.get("args") or event.get("input") or {}
        if isinstance(args_raw, dict):
            args_str = json.dumps(args_raw, ensure_ascii=False)[:500]
        else:
            args_str = str(args_raw)[:500]
        return {"role": "tool", "content": f"{name}({args_str})"}

    # function_call_result is intentionally skipped — the live stdout path
    # does not store tool results in session history either.

    return None
