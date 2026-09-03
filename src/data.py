"""From the two DuckDB tables to one point-in-time frame per route.

    dataset("tokyo")  ->  one row per trade date of the destination market: the destination and
                          freight settles a trader could read at that day's New York close

Every print carries two stamps. trade_date is the day on the file; settle_utc is the instant it
became readable, the market's local close on that day converted to UTC, so that Singapore,
Amsterdam and London prints on one date sit on one clock. A row is anchored at asof_utc, the New
York close, and each leg joins with merge_asof backward on these instants: the latest settle
already printed, never one that came after the anchor. FX is charged a day late on top, and a leg
older than the tolerance drops the row rather than being carried on.
"""

import pandas as pd

from src import config as c, sql


def to_utc(dates, market):
    """The local wall-clock time of a market on each date, as a UTC instant."""
    tz, time = market
    return (dates + pd.Timedelta(time)).dt.tz_localize(tz).dt.tz_convert("UTC")


def futures(product):
    """One product's settles, every contract, stamped with the instant each became readable."""
    df = sql.query(f"SELECT contract, delivery_month, trade_date, settle FROM futures "
                   f"WHERE product = '{product}'")
    df["settle_utc"] = to_utc(df["trade_date"], c.CLOSE[product])
    return df


def fx():
    """EURUSD bars, each readable at the anchor of the day after its label."""
    df = sql.query("SELECT trade_date AS fx_trade_date, eurusd FROM fx")
    df["fx_available_utc"] = to_utc(df["fx_trade_date"] + pd.Timedelta(days=c.FX_LAG_DAYS), c.ASOF)
    return df


def dataset(route):
    """The two legs of one route on each trade date of its destination market, as of the New
    York close: the delivery-month destination contract and the loading-month freight."""
    r = c.ROUTES[route]
    dest, freight = futures(r["price"]), futures(r["freight"])
    df = dest[["trade_date"]].drop_duplicates().sort_values("trade_date", ignore_index=True)
    df["asof_utc"] = to_utc(df["trade_date"], c.ASOF)
    # the cargo clock: loads on next month's program, sails mid-month, lands after the voyage
    df["loading_month"] = df["trade_date"] + pd.offsets.MonthBegin(1)
    arrival = df["loading_month"] + pd.Timedelta(days=c.LOAD_DAY - 1 + r["laden_days"])
    df["delivery_month"] = arrival.dt.to_period("M").dt.to_timestamp()
    legs = [("dest", dest, "delivery_month"), ("freight", freight, "loading_month")]
    for leg, prices, month in legs:
        prices = prices.add_prefix(leg + "_").rename(columns={f"{leg}_delivery_month": month})
        df = pd.merge_asof(df, prices.sort_values(f"{leg}_settle_utc"), left_on="asof_utc",
                           right_on=f"{leg}_settle_utc", by=month, direction="backward",
                           tolerance=pd.Timedelta(c.TOLERANCE))
    if r["price"] == "TTF":  # EUR/MWh: the row also needs the newest FX bar readable by the anchor
        df = pd.merge_asof(df, fx().sort_values("fx_available_utc"), left_on="asof_utc",
                           right_on="fx_available_utc", direction="backward",
                           tolerance=pd.Timedelta(c.TOLERANCE))
    df = df.dropna().drop(columns=["loading_month", "delivery_month"])  # a stale leg drops the row
    df["staleness_days"] = (df["trade_date"] - df.filter(like="_trade_date").min(axis=1)).dt.days
    return df.set_index("trade_date")
