from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class ScheduledEvent:
    id: int
    name: str
    kind: str
    prompt: str
    enabled: bool
    timezone: str
    run_at: str | None = None
    interval_seconds: int | None = None
    daily_time: str | None = None
    event_type: str | None = None
    filter_json: str = "{}"
    next_run_at: str | None = None
    last_run_at: str | None = None
    run_count: int = 0


class EventEngine:
    """Persistent scheduler + event-rule engine.

    Supported triggers:
      - once: absolute UTC/offset-aware timestamp
      - interval: repeated duration in seconds
      - daily: local HH:MM in an IANA timezone
      - watch: explicit event_type + optional JSON equality filters

    The engine itself does not execute shell commands or bypass tool approvals.
    Dispatching a due prompt back into Jenefar leaves all normal tool gates active.
    """

    def __init__(self, path: str | Path = "data/events.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    def _init_db(self) -> None:
        with self._connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS scheduled_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    timezone TEXT NOT NULL DEFAULT 'UTC',
                    run_at TEXT,
                    interval_seconds INTEGER,
                    daily_time TEXT,
                    event_type TEXT,
                    filter_json TEXT NOT NULL DEFAULT '{}',
                    next_run_at TEXT,
                    last_run_at TEXT,
                    run_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_scheduled_events_name
                    ON scheduled_events(name);
                """
            )

    @staticmethod
    def _parse_iso(value: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    @staticmethod
    def _iso(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _zone(name: str) -> ZoneInfo:
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone: {name}") from exc

    @classmethod
    def _row(cls, row: sqlite3.Row) -> ScheduledEvent:
        return ScheduledEvent(
            id=int(row["id"]),
            name=str(row["name"]),
            kind=str(row["kind"]),
            prompt=str(row["prompt"]),
            enabled=bool(row["enabled"]),
            timezone=str(row["timezone"]),
            run_at=row["run_at"],
            interval_seconds=int(row["interval_seconds"]) if row["interval_seconds"] is not None else None,
            daily_time=row["daily_time"],
            event_type=row["event_type"],
            filter_json=str(row["filter_json"] or "{}"),
            next_run_at=row["next_run_at"],
            last_run_at=row["last_run_at"],
            run_count=int(row["run_count"]),
        )

    @staticmethod
    def _validate_name(name: str) -> str:
        value = " ".join(str(name).split()).strip()
        if not value or len(value) > 120:
            raise ValueError("Event name must be 1-120 characters.")
        return value

    @staticmethod
    def _validate_prompt(prompt: str) -> str:
        value = str(prompt).strip()
        if not value or len(value) > 6000:
            raise ValueError("Event prompt must be 1-6000 characters.")
        return value

    def _insert(
        self,
        *,
        name: str,
        kind: str,
        prompt: str,
        timezone_name: str,
        run_at: str | None = None,
        interval_seconds: int | None = None,
        daily_time: str | None = None,
        event_type: str | None = None,
        filter_payload: dict[str, Any] | None = None,
        next_run_at: datetime | None = None,
    ) -> ScheduledEvent:
        clean_name = self._validate_name(name)
        clean_prompt = self._validate_prompt(prompt)
        tz = self._zone(timezone_name)
        if kind in {"once", "interval", "daily"} and next_run_at is None:
            raise ValueError("next_run_at is required for scheduled events.")
        if kind == "interval" and (interval_seconds is None or int(interval_seconds) < 60):
            raise ValueError("interval_seconds must be at least 60 seconds.")
        if kind == "daily":
            if not daily_time or len(daily_time) != 5 or daily_time[2] != ":":
                raise ValueError("daily_time must use HH:MM.")
            hour, minute = (int(part) for part in daily_time.split(":"))
            if not 0 <= hour <= 23 or not 0 <= minute <= 59:
                raise ValueError("daily_time must be a valid 24-hour clock time.")
        filter_json = json.dumps(filter_payload or {}, ensure_ascii=False, sort_keys=True)
        now = self._iso(datetime.now(timezone.utc))
        with self._connect() as con:
            try:
                cur = con.execute(
                    """
                    INSERT INTO scheduled_events(
                        name, kind, prompt, enabled, timezone, run_at, interval_seconds,
                        daily_time, event_type, filter_json, next_run_at, created_at
                    ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        clean_name,
                        kind,
                        clean_prompt,
                        str(tz),
                        run_at,
                        interval_seconds,
                        daily_time,
                        event_type,
                        filter_json,
                        self._iso(next_run_at) if next_run_at else None,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"An event named '{clean_name}' already exists.") from exc
            row = con.execute(
                "SELECT * FROM scheduled_events WHERE id = ?", (int(cur.lastrowid),)
            ).fetchone()
        return self._row(row)

    def schedule_once(self, name: str, prompt: str, run_at: str) -> ScheduledEvent:
        when = self._parse_iso(run_at)
        return self._insert(
            name=name,
            kind="once",
            prompt=prompt,
            timezone_name="UTC",
            run_at=self._iso(when),
            next_run_at=when,
        )

    def schedule_interval(
        self,
        name: str,
        prompt: str,
        every_seconds: int,
        *,
        start_at: str | None = None,
    ) -> ScheduledEvent:
        seconds = int(every_seconds)
        if seconds < 60:
            raise ValueError("every_seconds must be at least 60.")
        start = self._parse_iso(start_at) if start_at else datetime.now(timezone.utc) + timedelta(seconds=seconds)
        return self._insert(
            name=name,
            kind="interval",
            prompt=prompt,
            timezone_name="UTC",
            interval_seconds=seconds,
            next_run_at=start,
        )

    def _next_daily(self, daily_time: str, timezone_name: str, *, after: datetime) -> datetime:
        local_after = after.astimezone(self._zone(timezone_name))
        hour, minute = (int(part) for part in daily_time.split(":"))
        candidate = local_after.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= local_after:
            candidate += timedelta(days=1)
        return candidate

    def schedule_daily(
        self,
        name: str,
        prompt: str,
        daily_time: str,
        *,
        timezone_name: str = "UTC",
        start_at: str | None = None,
    ) -> ScheduledEvent:
        start = self._parse_iso(start_at) if start_at else datetime.now(timezone.utc)
        next_run = self._next_daily(daily_time, timezone_name, after=start)
        return self._insert(
            name=name,
            kind="daily",
            prompt=prompt,
            timezone_name=timezone_name,
            daily_time=daily_time,
            next_run_at=next_run,
        )

    def watch(
        self,
        name: str,
        event_type: str,
        prompt: str,
        *,
        filters: dict[str, Any] | None = None,
    ) -> ScheduledEvent:
        clean_type = " ".join(str(event_type).split()).strip().lower()
        if not clean_type or len(clean_type) > 120:
            raise ValueError("event_type must be 1-120 characters.")
        return self._insert(
            name=name,
            kind="watch",
            prompt=prompt,
            timezone_name="UTC",
            event_type=clean_type,
            filter_payload=filters or {},
        )

    def list(self, *, include_disabled: bool = True) -> list[ScheduledEvent]:
        sql = "SELECT * FROM scheduled_events"
        params: tuple[Any, ...] = ()
        if not include_disabled:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY id DESC"
        with self._connect() as con:
            rows = con.execute(sql, params).fetchall()
        return [self._row(row) for row in rows]

    def cancel(self, name: str) -> bool:
        with self._connect() as con:
            cur = con.execute(
                "UPDATE scheduled_events SET enabled = 0 WHERE name = ?",
                (str(name).strip(),),
            )
        return cur.rowcount > 0

    def due(self, now: datetime | None = None) -> list[ScheduledEvent]:
        current = now or datetime.now(timezone.utc)
        current_utc = self._iso(current)
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT * FROM scheduled_events
                WHERE enabled = 1
                  AND kind IN ('once', 'interval', 'daily', 'watch')
                  AND next_run_at IS NOT NULL
                  AND next_run_at <= ?
                ORDER BY next_run_at ASC, id ASC
                """,
                (current_utc,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def _reschedule(self, event: ScheduledEvent, *, now: datetime) -> None:
        if event.kind == "once":
            enabled = 0
            next_run = None
        elif event.kind == "watch":
            enabled = 1
            next_run = None
        elif event.kind == "interval":
            enabled = 1
            next_run = now + timedelta(seconds=int(event.interval_seconds or 60))
        elif event.kind == "daily":
            enabled = 1
            next_run = self._next_daily(
                str(event.daily_time),
                event.timezone,
                after=now,
            )
        else:
            return
        with self._connect() as con:
            con.execute(
                """
                UPDATE scheduled_events
                SET enabled = ?, next_run_at = ?, last_run_at = ?,
                    run_count = run_count + 1
                WHERE id = ?
                """,
                (
                    enabled,
                    self._iso(next_run) if next_run else None,
                    self._iso(now),
                    event.id,
                ),
            )

    @staticmethod
    def _matches_filters(payload: dict[str, Any], filters: dict[str, Any]) -> bool:
        return all(payload.get(str(key)) == value for key, value in filters.items())

    def emit(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        now: datetime | None = None,
    ) -> list[ScheduledEvent]:
        clean_type = " ".join(str(event_type).split()).strip().lower()
        data = payload or {}
        current = now or datetime.now(timezone.utc)
        matched: list[ScheduledEvent] = []
        for event in self.list(include_disabled=False):
            if event.kind != "watch" or event.event_type != clean_type:
                continue
            try:
                filters = json.loads(event.filter_json or "{}")
            except json.JSONDecodeError:
                filters = {}
            if self._matches_filters(data, filters):
                matched.append(event)
                with self._connect() as con:
                    con.execute(
                        """
                        UPDATE scheduled_events
                        SET next_run_at = ?
                        WHERE id = ?
                        """,
                        (self._iso(current), event.id),
                    )
        return matched

    def run_due(
        self,
        callback: Callable[[str, ScheduledEvent], Any],
        *,
        now: datetime | None = None,
        max_jobs: int = 10,
    ) -> list[dict[str, Any]]:
        current = now or datetime.now(timezone.utc)
        results: list[dict[str, Any]] = []
        for event in self.due(current)[: max(1, int(max_jobs))]:
            try:
                result = callback(event.prompt, event)
                results.append({
                    "event": event.name,
                    "event_id": event.id,
                    "status": "ok",
                    "result": result,
                })
            except Exception as exc:
                results.append({
                    "event": event.name,
                    "event_id": event.id,
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                })
            finally:
                self._reschedule(event, now=current)
        return results

    def sleep_until_next(self, default_seconds: float = 30.0) -> float:
        with self._connect() as con:
            row = con.execute(
                """
                SELECT MIN(next_run_at) AS next_run
                FROM scheduled_events
                WHERE enabled = 1 AND next_run_at IS NOT NULL
                """
            ).fetchone()
        if not row or not row["next_run"]:
            return max(1.0, float(default_seconds))
        try:
            seconds = (
                self._parse_iso(str(row["next_run"])) - datetime.now(timezone.utc)
            ).total_seconds()
        except ValueError:
            return max(1.0, float(default_seconds))
        return max(0.2, min(float(default_seconds), seconds))


__all__ = ["EventEngine", "ScheduledEvent"]
