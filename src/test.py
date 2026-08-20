"""Invariants that would cost money if they broke: when a price was knowable, which
contract a cargo prices against, and what the voyage leaves at the flange."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import pytest

import config
import data
import netback
from config import MMBTU_PER_MWH

SUMMER, WINTER = pd.Timestamp("2025-06-10"), pd.Timestamp("2026-01-15")
SCHEMA = Path(__file__).parents[1] / "sql" / "schema.sql"


def write(folder, name, rows):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text("\n".join(f"{d},{v}" for d, v in rows) + "\n")


@pytest.fixture()
def raw(tmp_path):
    """Two June trade dates. June trades load in July, so Tokyo delivers in August and
    Rotterdam in July. The 2025-06-10 FX bar is deliberately wild: it must not be used."""
    write(tmp_path / "lng", "JKMQ2025.csv", [("2025-06-09", 12.00), ("2025-06-10", 12.22)])
    write(tmp_path / "lng", "TTFN2025.csv", [("2025-06-09", 34.00), ("2025-06-10", 34.638)])
    write(tmp_path / "freight", "BLNG3N2025.csv", [("2025-06-09", 44000.0), ("2025-06-10", 44667.0)])
    write(tmp_path / "freight", "BLNG2N2025.csv", [("2025-06-09", 36000.0), ("2025-06-10", 37000.0)])
    write(tmp_path / "fx", "eurusd_daily.csv",
          [("2025-06-06", 1.1390), ("2025-06-09", 1.14211), ("2025-06-10", 1.5000)])
    return tmp_path


def panel_from(raw) -> pd.DataFrame:
    return data.build_panel(
        data.load_lng(raw / "lng"),
        data.load_freight(raw / "freight"),
        data.load_fx(raw / "fx"),
    )


def instant(date, tz, offset):
    return data.to_utc(pd.Series([date]) + offset, tz).iloc[0]


def row(panel, route, date=SUMMER):
    return panel[(panel["route"] == route) & (panel["trade_date"] == date)].iloc[0]


# --- when a price was knowable ------------------------------------------------


@pytest.mark.parametrize(
    ("product", "summer", "winter"),
    [("JKM", "08:30", "08:30"), ("TTF", "15:00", "16:00"), ("BLNG2", "15:00", "16:00")],
)
def test_settle_anchors_track_dst(product, summer, winter):
    tz, offset = config.SETTLE_ANCHORS[product]
    assert instant(SUMMER, tz, offset).strftime("%H:%M") == summer
    assert instant(WINTER, tz, offset).strftime("%H:%M") == winter


def test_fx_is_usable_only_at_the_next_new_york_close():
    tz, offset = config.FX_AVAILABLE
    assert instant(SUMMER, tz, offset) == pd.Timestamp("2025-06-11 21:00", tz="UTC")
    assert instant(WINTER, tz, offset) == pd.Timestamp("2026-01-16 22:00", tz="UTC")


def test_panel_anchor_falls_after_every_settle_that_day():
    tz, offset = config.ASOF
    for date in (SUMMER, WINTER):
        anchor = instant(date, tz, offset)
        for product, (ptz, poffset) in config.SETTLE_ANCHORS.items():
            assert instant(date, ptz, poffset) < anchor, product


def test_fx_uses_the_previous_bar(raw):
    # the 06-10 bar prints 1.50; using it would be look-ahead
    assert row(panel_from(raw), "us_gulf_to_rotterdam")["eurusd"] == pytest.approx(1.14211)


def test_future_rows_cannot_change_the_past(raw):
    before = panel_from(raw)
    with (raw / "lng" / "JKMQ2025.csv").open("a") as fh:
        fh.write("2025-06-11,99.0\n")
    after = panel_from(raw)

    merged = before.merge(after, on=["route", "trade_date"], suffixes=("_before", "_after"))
    assert len(merged) == len(before)
    assert (merged["netback_usd_mmbtu_before"] == merged["netback_usd_mmbtu_after"]).all()


def test_a_settle_after_the_anchor_is_refused(raw):
    lng = data.load_lng(raw / "lng")
    lng["settle_timestamp_utc"] += pd.Timedelta(days=1)
    with pytest.raises(ValueError, match="look-ahead"):
        data.build_panel(lng, data.load_freight(raw / "freight"), data.load_fx(raw / "fx"))


# --- staleness ----------------------------------------------------------------


def test_a_price_staler_than_the_tolerance_drops_the_row(raw):
    write(raw / "freight", "BLNG3N2025.csv", [("2025-06-02", 44000.0)])  # 7 days before
    panel = panel_from(raw)
    assert (panel["route"] == "us_gulf_to_tokyo").sum() == 0
    assert (panel["route"] == "us_gulf_to_rotterdam").sum() > 0


def test_a_price_inside_the_tolerance_is_carried_and_flagged(raw):
    write(raw / "freight", "BLNG3N2025.csv", [("2025-06-06", 44000.0)])  # 3 and 4 days before
    tokyo = panel_from(raw).set_index(["route", "trade_date"]).loc["us_gulf_to_tokyo"]
    assert tokyo.loc[pd.Timestamp("2025-06-09"), "max_staleness_days"] == 3
    assert tokyo.loc[pd.Timestamp("2025-06-10"), "max_staleness_days"] == 4
    assert (tokyo["freight_rate_usd_day"] == 44000.0).all()


# --- which contract, and what it leaves ---------------------------------------


def test_cargo_clock():
    for day in ("2025-01-05", "2025-01-25"):  # the day of the month must not matter
        assert data.loading_month(pd.Timestamp(day)) == pd.Timestamp("2025-02-01")
    assert data.loading_month(pd.Timestamp("2025-12-31")) == pd.Timestamp("2026-01-01")

    february = pd.Timestamp("2025-02-01")
    assert data.delivery_month(february, 10) == february  # load 15 Feb, arrive 25 Feb
    assert data.delivery_month(february, 20) == pd.Timestamp("2025-03-01")  # arrive 7 Mar
    assert data.delivery_month(pd.Timestamp("2025-12-01"), 20) == pd.Timestamp("2026-01-01")


def test_contracts_follow_the_cargo(raw):
    panel = panel_from(raw)
    tokyo, rotterdam = row(panel, "us_gulf_to_tokyo"), row(panel, "us_gulf_to_rotterdam")
    assert (tokyo["dest_contract"], tokyo["freight_contract"]) == ("JKMQ2025", "BLNG3N2025")
    assert (rotterdam["dest_contract"], rotterdam["freight_contract"]) == ("TTFN2025", "BLNG2N2025")


def test_tokyo_netback(raw):
    got = row(panel_from(raw), "us_gulf_to_tokyo")
    price = 12.22
    boiloff = price * (1 - (1 - 0.0015) ** 20)
    freight = 44667.0 * (20 * 2 + 2) / 3_500_000
    canal, port = 1_000_000 / 3_500_000, 200_000 / 3_500_000
    assert got["netback_usd_mmbtu"] == pytest.approx(price - boiloff - freight - canal - port)


def test_rotterdam_netback(raw):
    got = row(panel_from(raw), "us_gulf_to_rotterdam")
    price = 34.638 * 1.14211 / MMBTU_PER_MWH  # EUR/MWh on the previous FX bar
    boiloff = price * (1 - (1 - 0.0015) ** 10)
    freight = 37000.0 * (10 * 2 + 2) / 3_500_000
    regas, port = 0.50 * (1 - 0.0015) ** 10, 200_000 / 3_500_000
    assert got["dest_price_usd_mmbtu"] == pytest.approx(price)
    assert got["canal_cost_usd_mmbtu"] == 0.0  # no canal on the Atlantic leg
    assert got["netback_usd_mmbtu"] == pytest.approx(price - boiloff - freight - regas - port)


def test_costs_subtract_exactly(raw):
    panel = panel_from(raw)
    costs = [c for c in panel if c.endswith("_cost_usd_mmbtu")]
    rebuilt = panel["dest_price_usd_mmbtu"] - panel[costs].sum(axis=1)
    assert (rebuilt == panel["netback_usd_mmbtu"]).all()


# --- the SQL copy -------------------------------------------------------------


def test_duckdb_keeps_the_numbers_and_the_instants(raw, tmp_path):
    panel = panel_from(raw)
    con = duckdb.connect(str(tmp_path / "t.duckdb"))
    con.execute(SCHEMA.read_text())
    con.execute("INSERT INTO netback_panel SELECT * FROM panel")
    back = con.execute("SELECT * FROM netback_panel ORDER BY route, trade_date").df()

    assert len(back) == len(panel)
    assert back["netback_usd_mmbtu"].sub(panel["netback_usd_mmbtu"]).abs().max() < 1e-9
    # DuckDB has a real TIMESTAMP WITH TIME ZONE, so the instants survive; SQLite would
    # have flattened them. It hands them back in the session zone, so compare in UTC.
    assert back["asof_timestamp_utc"].dt.tz is not None
    assert back["asof_timestamp_utc"].dt.tz_convert("UTC").astype("datetime64[ns, UTC]").equals(
        panel["asof_timestamp_utc"]
    )


# --- the gates that catch bad files -------------------------------------------


def test_poison_gate_refuses_a_foreign_series(tmp_path):
    # a March 2025 JKM file holding April settles is a fetcher that fell back to the
    # continuous front month
    write(tmp_path / "lng", "JKMH2025.csv", [("2025-02-10", 14.0), ("2025-04-10", 13.0)])
    with pytest.raises(ValueError, match="not this contract"):
        data.load_lng(tmp_path / "lng")


def test_duplicate_settles_raise(tmp_path):
    write(tmp_path / "lng", "JKMQ2025.csv", [("2025-06-09", 12.0), ("2025-06-09", 12.1)])
    with pytest.raises(ValueError, match="duplicate"):
        data.load_lng(tmp_path / "lng")


@pytest.mark.parametrize("value", ["abc", "nan"])
def test_a_bad_price_fails_the_build(tmp_path, value):
    write(tmp_path / "lng", "JKMQ2025.csv", [("2025-06-09", value)])
    with pytest.raises(ValueError):
        data.load_lng(tmp_path / "lng")


def test_the_sql_view_and_the_python_arb_agree(raw, tmp_path):
    """The arb exists twice, in netback.arb and in sql/views.sql. They must match."""
    panel = panel_from(raw)
    con = duckdb.connect(str(tmp_path / "t.duckdb"))
    con.execute(SCHEMA.read_text())
    con.register("panel", panel)
    con.execute("INSERT INTO netback_panel SELECT * FROM panel")
    con.execute((SCHEMA.parent / "views.sql").read_text())

    from_sql = con.execute("SELECT * FROM v_netback_arb ORDER BY trade_date").df()
    from_python = netback.arb(panel)
    assert from_sql["arb_usd_mmbtu"].sub(from_python["arb_usd_mmbtu"]).abs().max() < 1e-12
