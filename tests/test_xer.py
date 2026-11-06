from datetime import date
from pathlib import Path

import pytest

from second_source import xer

SCHEDULE = Path(__file__).resolve().parents[1] / "portfolios" / "hard" / "contracts" / "C001" / "schedule.xer"


def test_roundtrip_preserves_tables_and_metrics(tmp_path):
    tables = xer.read(SCHEDULE)
    path = tmp_path / "schedule.xer"
    xer.write(path, tables, date(2026, 12, 31))
    text = path.read_text()
    assert text.startswith("ERMHDR")
    assert text.rstrip().endswith("%E")

    back = xer.read(path)
    assert set(back) == {"PROJECT", "TASK", "TASKRSRC"}
    assert len(back["TASK"]) == len(tables["TASK"])

    a, b = xer.metrics(tables), xer.metrics(back)
    assert b.bac == pytest.approx(a.bac)
    assert b.ev == pytest.approx(a.ev)
    assert b.pv == pytest.approx(a.pv)
    assert b.forecast_finish == a.forecast_finish


def test_planned_fraction_is_linear_and_clamped():
    s, e = date(2026, 1, 1), date(2026, 1, 11)
    assert xer.planned_fraction(s, e, date(2025, 12, 1)) == 0.0
    assert xer.planned_fraction(s, e, date(2026, 1, 6)) == pytest.approx(0.5)
    assert xer.planned_fraction(s, e, date(2026, 2, 1)) == 1.0
