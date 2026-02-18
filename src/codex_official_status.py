from __future__ import annotations

import json
import queue
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class OfficialRateLimitsSnapshot:
    plan_type: str | None
    account_type: str | None
    account_email: str | None
    limit_id: str | None
    primary_used_percent: float | None
    primary_window_minutes: int | None
    primary_resets_at_epoch: int | None
    secondary_used_percent: float | None
    secondary_window_minutes: int | None
    secondary_resets_at_epoch: int | None


@dataclass(frozen=True)
class OfficialTokenCountSnapshot:
    source: str | None
    timestamp_utc: str | None
    model_context_window: int | None
    total_tokens: int | None
    last_tokens: int | None


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_utc_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _read_jsonrpc_results(
    timeout_seconds: int,
    requests: list[tuple[int, str, Any]],
) -> dict[int, dict[str, Any]]:
    process = subprocess.Popen(
        ["codex", "app-server", "--listen", "stdio://"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out_queue: queue.Queue[str] = queue.Queue()

    def _reader() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            out_queue.put(line)

    reader_thread = threading.Thread(target=_reader, daemon=True)
    reader_thread.start()

    assert process.stdin is not None
    for req_id, method, params in requests:
        message = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()

    responses: dict[int, dict[str, Any]] = {}
    remaining = {req_id for req_id, _, _ in requests}
    deadline = datetime.now(timezone.utc).timestamp() + timeout_seconds

    try:
        while remaining and datetime.now(timezone.utc).timestamp() < deadline:
            timeout_left = max(deadline - datetime.now(timezone.utc).timestamp(), 0.05)
            try:
                line = out_queue.get(timeout=timeout_left)
            except queue.Empty:
                break

            text = line.strip()
            if not text:
                continue

            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue

            req_id = payload.get("id")
            if not isinstance(req_id, int):
                continue
            if req_id not in remaining:
                continue
            responses[req_id] = payload
            remaining.remove(req_id)
    finally:
        process.terminate()
        try:
            process.wait(timeout=1.5)
        except subprocess.TimeoutExpired:
            process.kill()

    return responses


def read_official_rate_limits(timeout_seconds: int = 6) -> OfficialRateLimitsSnapshot | None:
    requests = [
        (
            1,
            "initialize",
            {
                "clientInfo": {
                    "name": "discord-codex-gateway",
                    "version": "1.0",
                },
                "capabilities": {
                    "experimentalApi": True,
                },
            },
        ),
        (
            2,
            "account/read",
            {
                "refreshToken": False,
            },
        ),
        (
            3,
            "account/rateLimits/read",
            None,
        ),
    ]

    try:
        results = _read_jsonrpc_results(timeout_seconds=timeout_seconds, requests=requests)
    except Exception:
        return None

    account_result = results.get(2, {}).get("result", {})
    account = account_result.get("account", {}) if isinstance(account_result, dict) else {}

    rate_result = results.get(3, {}).get("result", {})
    rate_limits = rate_result.get("rateLimits", {}) if isinstance(rate_result, dict) else {}

    if not isinstance(rate_limits, dict) or not rate_limits:
        return None

    primary = rate_limits.get("primary", {})
    secondary = rate_limits.get("secondary", {})

    return OfficialRateLimitsSnapshot(
        plan_type=str(rate_limits.get("planType")) if rate_limits.get("planType") is not None else str(account.get("planType")) if account.get("planType") is not None else None,
        account_type=str(account.get("type")) if account.get("type") is not None else None,
        account_email=str(account.get("email")) if account.get("email") is not None else None,
        limit_id=str(rate_limits.get("limitId")) if rate_limits.get("limitId") is not None else None,
        primary_used_percent=_coerce_float(primary.get("usedPercent")) if isinstance(primary, dict) else None,
        primary_window_minutes=_coerce_int(primary.get("windowDurationMins")) if isinstance(primary, dict) else None,
        primary_resets_at_epoch=_coerce_int(primary.get("resetsAt")) if isinstance(primary, dict) else None,
        secondary_used_percent=_coerce_float(secondary.get("usedPercent")) if isinstance(secondary, dict) else None,
        secondary_window_minutes=_coerce_int(secondary.get("windowDurationMins")) if isinstance(secondary, dict) else None,
        secondary_resets_at_epoch=_coerce_int(secondary.get("resetsAt")) if isinstance(secondary, dict) else None,
    )


def read_latest_token_count_snapshot(sessions_root: Path | None = None) -> OfficialTokenCountSnapshot | None:
    root = sessions_root or (Path.home() / ".codex" / "sessions")
    if not root.exists():
        return None

    files = sorted(root.rglob("rollout-*.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not files:
        return None

    for path in files[:120]:
        source: str | None = None
        latest_token_payload: dict[str, Any] | None = None
        latest_token_timestamp: str | None = None

        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    event_type = entry.get("type")
                    payload = entry.get("payload")
                    if event_type == "session_meta" and isinstance(payload, dict):
                        source_value = payload.get("source")
                        if source_value is not None:
                            source = str(source_value)
                        continue

                    if event_type != "event_msg" or not isinstance(payload, dict):
                        continue
                    if payload.get("type") != "token_count":
                        continue

                    latest_token_payload = payload
                    timestamp_value = entry.get("timestamp")
                    latest_token_timestamp = str(timestamp_value) if timestamp_value is not None else None
        except OSError:
            continue

        if latest_token_payload is None:
            continue

        info = latest_token_payload.get("info", {})
        if not isinstance(info, dict):
            continue

        total_usage = info.get("total_token_usage", {})
        last_usage = info.get("last_token_usage", {})

        total_tokens = _coerce_int(total_usage.get("total_tokens")) if isinstance(total_usage, dict) else None
        last_tokens = _coerce_int(last_usage.get("total_tokens")) if isinstance(last_usage, dict) else None
        model_context_window = _coerce_int(info.get("model_context_window"))

        return OfficialTokenCountSnapshot(
            source=source,
            timestamp_utc=latest_token_timestamp,
            model_context_window=model_context_window,
            total_tokens=total_tokens,
            last_tokens=last_tokens,
        )

    return None


def read_local_total_tokens_last_days(
    days: int = 7,
    sessions_root: Path | None = None,
    max_files: int = 2500,
) -> int | None:
    if days <= 0:
        return None

    root = sessions_root or (Path.home() / ".codex" / "sessions")
    if not root.exists():
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    files = sorted(root.rglob("rollout-*.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not files:
        return None

    total_tokens_sum = 0
    matched_files = 0

    for path in files[:max_files]:
        try:
            if path.stat().st_mtime < (cutoff.timestamp() - 86_400):
                continue
        except OSError:
            continue

        per_file_max_tokens: int | None = None

        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if entry.get("type") != "event_msg":
                        continue
                    payload = entry.get("payload")
                    if not isinstance(payload, dict) or payload.get("type") != "token_count":
                        continue

                    event_time = _parse_utc_timestamp(entry.get("timestamp"))
                    if event_time is None or event_time < cutoff:
                        continue

                    info = payload.get("info")
                    if not isinstance(info, dict):
                        continue
                    last_usage = info.get("last_token_usage")
                    if not isinstance(last_usage, dict):
                        continue
                    total_tokens = _coerce_int(last_usage.get("total_tokens"))
                    if total_tokens is None or total_tokens < 0:
                        continue

                    if per_file_max_tokens is None or total_tokens > per_file_max_tokens:
                        per_file_max_tokens = total_tokens
        except OSError:
            continue

        if per_file_max_tokens is None:
            continue

        total_tokens_sum += per_file_max_tokens
        matched_files += 1

    if matched_files == 0:
        return None
    return total_tokens_sum


def format_epoch_utc(epoch_seconds: int | None) -> str:
    if not isinstance(epoch_seconds, int):
        return "desconhecido"
    try:
        dt = datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
    except (ValueError, OSError):
        return "desconhecido"
    return dt.strftime("%Y-%m-%d %H:%M UTC")
