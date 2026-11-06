"""Minimal Primavera P6 XER reader and writer, plus schedule metrics.

XER is plain text: an ERMHDR line, then for each table a %T line (table name),
a %F line (field names) and %R lines (rows), all tab-separated, ending with %E.

Only the subset Second Source needs is written: PROJECT, TASK and TASKRSRC with
cost loading. Real exports carry many more tables and fields; the reader keeps
whatever it finds.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

DATE_FMT = "%Y-%m-%d %H:%M"

Tables = dict[str, list[dict[str, str]]]


def fmt_date(d: date | None) -> str:
    if d is None:
        return ""
    return datetime(d.year, d.month, d.day, 17, 0).strftime(DATE_FMT)


def parse_date(s: str) -> date | None:
    s = s.strip()
    if not s:
        return None
    return datetime.strptime(s, DATE_FMT).date()


def write(path: Path, tables: Tables, export_date: date) -> None:
    lines = [
        "\t".join(
            ["ERMHDR", "20.12", export_date.isoformat(), "Project", "admin", "second-source",
             "dbxDatabaseNoName", "Project Management", "GBP"]
        )
    ]
    for name, rows in tables.items():
        if not rows:
            continue
        fields = list(rows[0].keys())
        lines.append(f"%T\t{name}")
        lines.append("%F\t" + "\t".join(fields))
        for row in rows:
            lines.append("%R\t" + "\t".join(str(row.get(f, "")) for f in fields))
    lines.append("%E")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read(path: Path) -> Tables:
    tables: Tables = {}
    current: str | None = None
    fields: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        parts = raw.split("\t")
        tag = parts[0]
        if tag == "%T":
            current = parts[1]
            tables[current] = []
        elif tag == "%F":
            fields = parts[1:]
        elif tag == "%R" and current is not None:
            values = parts[1:] + [""] * (len(fields) - len(parts[1:]))
            tables[current].append(dict(zip(fields, values, strict=False)))
        elif tag == "%E":
            break
    return tables


@dataclass(frozen=True)
class ScheduleMetrics:
    data_date: date
    bac: float
    ev: float
    pv: float
    baseline_finish: date
    forecast_finish: date

    @property
    def physical_pct(self) -> float:
        return self.ev / self.bac if self.bac else 0.0

    @property
    def spi(self) -> float:
        return self.ev / self.pv if self.pv else 0.0

    @property
    def forecast_slip_days(self) -> int:
        return (self.forecast_finish - self.baseline_finish).days


def planned_fraction(start: date, end: date, at: date) -> float:
    """Linear planned progress of one activity at a date."""
    if at <= start:
        return 0.0
    if at >= end:
        return 1.0
    return (at - start).days / max(1, (end - start).days)


def metrics(tables: Tables) -> ScheduleMetrics:
    project = tables["PROJECT"][0]
    data_date = parse_date(project["last_recalc_date"])
    assert data_date is not None
    cost_by_task: dict[str, float] = {}
    for r in tables.get("TASKRSRC", []):
        cost_by_task[r["task_id"]] = cost_by_task.get(r["task_id"], 0.0) + float(r["target_cost"])

    bac = ev = pv = 0.0
    baseline_finish = forecast_finish = data_date
    for t in tables["TASK"]:
        budget = cost_by_task.get(t["task_id"], 0.0)
        start = parse_date(t["target_start_date"])
        end = parse_date(t["target_end_date"])
        assert start and end
        bac += budget
        ev += budget * float(t["phys_complete_pct"]) / 100.0
        pv += budget * planned_fraction(start, end, data_date)
        finish = parse_date(t.get("act_end_date", "")) or parse_date(t.get("early_end_date", ""))
        baseline_finish = max(baseline_finish, end)
        if finish:
            forecast_finish = max(forecast_finish, finish)
    return ScheduleMetrics(data_date, bac, ev, pv, baseline_finish, forecast_finish)
