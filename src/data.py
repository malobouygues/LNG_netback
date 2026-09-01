"""Ingestion and alignment: CSVs in, one point-in-time frame per route out, then DuckDB.

Each source prints on its own local wall clock, so every price is stamped with the UTC
instant a trader could have acted on it. Joins run backward with an explicit tolerance, and
each row records how old its oldest input is.

    python -m src.data
"""

import re

import duckdb
import pandas as pd

from src import config as c, netback

CONTRACT_RE = re.compile(r"^(BLNG2|BLNG3|JKM|TTF)([FGHJKMNQUVXZ])(\d{4})$")


# --- when each price was knowable ---------------------------------------------
def to_utc(naive, tz):
    return (naive.dt.tz_localize(tz, nonexistent="shift_forward", ambiguous="raise")
                 .dt.tz_convert("UTC"))


def read_prices(path):
    """One headerless date,value file. Read as text then coerced, so a new sentinel fails
    the build rather than arriving as a silent NaN."""
    raw = pd.read_csv(path, header=None, names=["date", "value"], dtype=str)
    if raw.empty or raw.isna().any(axis=None):
        raise ValueError(f"{path.name}: empty file or blank field")
    return pd.DataFrame({
        "trade_date": pd.to_datetime(raw["date"], format="%Y-%m-%d").astype("datetime64[ns]"),
        "settle": pd.to_numeric(raw["value"], errors="raise").astype("float64"),
    })


def expiry_cutoff(product, delivery_month):
    """Latest date this contract can still print a settle, with slack for holidays."""
    if product == "JKM":  # expires mid M-1, on the Platts assessment window
        previous = delivery_month - pd.Timedelta(days=1)
        return pd.Timestamp(previous.year, previous.month, 22)
    if product == "TTF":  # expires about two business days before the month starts
        return delivery_month
    # BLNG settles on the average of the month's assessments, so it trades through it
    return delivery_month + pd.offsets.MonthBegin(1) + pd.Timedelta(days=6)


def load_futures(folder, products):
    frames = []
    for path in sorted(folder.glob("*.csv")):
        match = CONTRACT_RE.match(path.stem)
        if match is None or match.group(1) not in products:
            raise ValueError(f"{path.name}: not one of {products}")
        product, code, year = match.group(1), match.group(2), int(match.group(3))
        delivery_month = pd.Timestamp(year, c.MONTH_CODES[code], 1)
        prices = read_prices(path)

        # A settle printing after the contract can plausibly trade means the file holds some
        # other series, which is exactly what a fetcher falling back to the continuous front
        # month produces. Refuse it rather than net back a wrong month.
        cutoff = expiry_cutoff(product, delivery_month)
        late = prices[prices["trade_date"] > cutoff]
        if not late.empty:
            raise ValueError(f"{path.stem}: {len(late)} rows after {cutoff.date()}, not this contract")

        tz, offset = c.SETTLE_ANCHORS[product]
        frames.append(prices.assign(
            product=product, contract=path.stem, delivery_month=delivery_month,
            settle_timestamp_utc=to_utc(prices["trade_date"] + offset, tz)))

    if not frames:
        raise FileNotFoundError(f"no contract CSVs under {folder}")
    df = pd.concat(frames, ignore_index=True)
    if df.duplicated(["contract", "trade_date"]).any():
        raise ValueError(f"{folder.name}: duplicate (contract, trade_date)")
    columns = ["product", "contract", "delivery_month", "trade_date", "settle_timestamp_utc", "settle"]
    return df[columns].sort_values(["contract", "trade_date"], ignore_index=True)


def load_lng(folder=c.LNG_DIR):
    """JKM in USD/MMBtu and TTF in EUR/MWh, two units sharing one settle column."""
    df = load_futures(folder, ("JKM", "TTF"))
    if (df["settle"] <= 0).any():
        raise ValueError("LNG settle at or below zero")
    return df


def load_freight(folder=c.FREIGHT_DIR):
    """BLNG2 and BLNG3 in USD per charter day. No sign check: BLNG2 printed about
    -1,100 USD/day in the February 2025 Atlantic glut, and that was real."""
    return load_futures(folder, ("BLNG2", "BLNG3"))


def load_fx(folder=c.FX_DIR):
    df = read_prices(folder / "eurusd_daily.csv").rename(columns={"settle": "eurusd"})
    if df.duplicated("trade_date").any():
        raise ValueError("duplicate FX trade dates")
    tz, offset = c.FX_AVAILABLE
    df["available_timestamp_utc"] = to_utc(df["trade_date"] + offset, tz)
    return (df[["trade_date", "available_timestamp_utc", "eurusd"]]
            .sort_values("trade_date", ignore_index=True))


# --- which contract, and aligning it to the trade date ------------------------
def loading_month(trade_date):
    """A spot cargo loads on the next program, so the month after the trade month."""
    year, month = ((trade_date.year + 1, 1) if trade_date.month == 12
                   else (trade_date.year, trade_date.month + 1))
    return pd.Timestamp(year, month, 1)


def delivery_month(loading, laden_days):
    """Where the cargo lands: mid-month sailing plus the voyage. Rotterdam at 10 days stays
    in the loading month, Tokyo at 20 days via Panama lands in the next one."""
    arrival = loading + pd.Timedelta(days=c.LOAD_DAY - 1 + laden_days)
    return pd.Timestamp(arrival.year, arrival.month, 1)


def join_settles(left, store, on, prefix):
    right = store[["contract", "trade_date", "settle", "settle_timestamp_utc"]].rename(
        columns={"contract": on, "settle": f"{prefix}_settle",
                 "settle_timestamp_utc": f"{prefix}_settle_utc"})
    right[f"{prefix}_price_date"] = right["trade_date"]
    return pd.merge_asof(left, right.sort_values("trade_date"), on="trade_date", by=on,
                         direction="backward", tolerance=c.TOLERANCE)


def reject_lookahead(df, column, label):
    late = df[df[column].notna() & (df[column] > df["asof_timestamp_utc"])]
    if not late.empty:
        raise ValueError(f"look-ahead: {len(late)} rows where the {label} lands after the anchor")


def trade_dates(lng):
    """The grid: one row per LNG market day, carrying that day's anchor."""
    grid = pd.Series(sorted(lng["trade_date"].unique()), name="trade_date").to_frame()
    tz, offset = c.ASOF
    grid["asof_timestamp_utc"] = to_utc(grid["trade_date"] + offset, tz)
    return grid


def align(spec, grid, lng, freight, fx):
    """Everything a trader could see on a date for one route, and how old it is."""
    dest_product, freight_product, laden_days, canal_usd, regas_usd = spec

    df = grid.copy()
    loading = df["trade_date"].map(loading_month)
    delivery = loading.map(lambda month: delivery_month(month, laden_days))
    df["dest_contract"] = delivery.map(lambda m: f"{dest_product}{c.CODE_BY_MONTH[m.month]}{m.year}")
    df["freight_contract"] = loading.map(lambda m: f"{freight_product}{c.CODE_BY_MONTH[m.month]}{m.year}")

    df = join_settles(df, lng[lng["product"] == dest_product], "dest_contract", "dest")
    df = join_settles(df, freight[freight["product"] == freight_product], "freight_contract", "freight")
    reject_lookahead(df, "dest_settle_utc", "destination settle")
    reject_lookahead(df, "freight_settle_utc", "freight settle")

    needed = ["dest_settle", "freight_settle"]
    if dest_product == "TTF":
        # A bar labelled D is only available at D+1 17:00 New York, which is after this row's
        # anchor, so allow_exact_matches=False leaves only labels up to D-1, provably known.
        df = pd.merge_asof(df, fx.assign(fx_price_date=fx["trade_date"]).sort_values("trade_date"),
                           on="trade_date", direction="backward", tolerance=c.TOLERANCE,
                           allow_exact_matches=False)
        reject_lookahead(df, "available_timestamp_utc", "FX bar")
        needed.append("eurusd")
    else:
        df["eurusd"] = float("nan")  # JKM is quoted in USD and needs no conversion

    df = df.dropna(subset=needed)
    ages = [(df["trade_date"] - df[col]).dt.days for col in df if col.endswith("_price_date")]
    return df.assign(max_staleness_days=pd.concat(ages, axis=1).max(axis=1).astype("int64"))


def build_panel(lng, freight, fx):
    """One row per (route, trade_date), on the days the LNG market traded."""
    grid = trade_dates(lng)
    panel = pd.concat([netback.price(name, spec, align(spec, grid, lng, freight, fx))
                       for name, spec in c.ROUTES.items()], ignore_index=True)
    if panel.duplicated(["route", "trade_date"]).any():
        raise ValueError("panel has duplicate (route, trade_date)")
    return panel.sort_values(["route", "trade_date"], ignore_index=True)


# --- the store ----------------------------------------------------------------
def main():
    lng, freight, fx = load_lng(), load_freight(), load_fx()
    panel = build_panel(lng, freight, fx)

    c.DB_PATH.unlink(missing_ok=True)
    with duckdb.connect(str(c.DB_PATH)) as con:
        con.execute((c.SQL_DIR / "schema.sql").read_text())
        for table, frame in [("lng_futures_daily", lng), ("freight_futures_daily", freight),
                             ("fx_daily", fx), ("netback_panel", panel)]:
            con.register("frame", frame)  # name the DataFrame so SQL can select from it
            con.execute(f"INSERT INTO {table} SELECT * FROM frame")
            print(f"{table}: {len(frame)} rows")
        con.execute((c.SQL_DIR / "views.sql").read_text())
    print(f"wrote {c.DB_PATH}")


if __name__ == "__main__":
    main()
