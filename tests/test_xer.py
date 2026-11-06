from datetime import date

import pytest

from second_source import xer
from second_source.simulator import generate


def test_roundtrip_preserves_tables_and_metrics(tmp_path):
    c = generate(1, seed=0)[0]
    path = tmp_path / "schedule.xer"
    xer.write(path, c.xer_tables, date(2026, 12, 31))
    text = path.read_text()
    assert text.startswith("ERMHDR")
    assert text.rstrip().endswith("%E")

    back = xer.read(path)
    assert set(back) == {"PROJECT", "TASK", "TASKRSRC"}
    assert len(back["TASK"]) == len(c.xer_tables["TASK"])

    a, b = xer.metrics(c.xer_tables), xer.metrics(back)
    assert b.bac == pytest.approx(a.bac)
    assert b.ev == pytest.approx(a.ev)
    assert b.pv == pytest.approx(a.pv)
    assert b.forecast_finish == a.forecast_finish


def test_planned_fraction_is_linear_and_clamped():
    s, e = date(2026, 1, 1), date(2026, 1, 11)
    assert xer.planned_fraction(s, e, date(2025, 12, 1)) == 0.0
    assert xer.planned_fraction(s, e, date(2026, 1, 6)) == pytest.approx(0.5)
    assert xer.planned_fraction(s, e, date(2026, 2, 1)) == 1.0
