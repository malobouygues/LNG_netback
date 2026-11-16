"""Fetch the raw csv files into data/. Settles come from TradingView, one file per contract,
and need tvDatafeed; nothing else does, and the csv files are committed, so the repo never has
to run this. Settle files only grow: a rerun adds the settles printed since the last one and
rewrites nothing. The DOE cargo list is republished whole every month and replaces its file.

    python -m src.download
"""

import io
import os
import re
import subprocess
import time

import pandas as pd
from tvDatafeed import Interval, TvDatafeed

from src import config as c

# product -> TradingView symbol root, exchange, folder under data/
FEEDS = {"JKM": ("JKM", "NYMEX", "lng"), "NWM": ("NWM", "NYMEX", "lng"),
         "BLNG2": ("BG2", "NYMEX", "freight"), "BLNG3": ("BG3", "NYMEX", "freight")}
DOE = "https://www.energy.gov/hgeo/articles/natural-gas-imports-and-exports-monthly-"
MONTHS = (-12, 4)  # contracts from a year back to four months out: Tokyo's JKM is M+1 of M+3
BARS = 100         # settles per contract, enough to reach back to a BLNG contract's loading month


def get(tv, symbol, exchange):
    for _ in range(3):  # the socket drops now and then
        bars = tv.get_hist(symbol=symbol, exchange=exchange, interval=Interval.in_daily,
                           n_bars=BARS)
        if bars is not None and not bars.empty:
            return bars


def save(bars, path):
    """Append the new settles to the contract's file. A date already on file keeps its first
    print: the vendor serves only the last BARS days, and a settle is not meant to change."""
    # a daily bar is stamped at its session open, for CME the evening before: +6h lands it on
    # its trade date, whatever the season
    new = bars["close"]
    new.index = (new.index + pd.Timedelta(hours=6)).normalize()
    if path.exists():
        old = pd.read_csv(path, header=None, index_col=0, parse_dates=True)[1]
        again = new.reindex(old.index)  # the dates fetched a second time
        changed = again.notna() & (again != old)
        if changed.any():
            print(f"{path.stem}: {changed.sum()} settles differ from the file, first print kept")
        new = pd.concat([old, new[~new.index.isin(old.index)]])
    new = new.sort_index()
    new.to_csv(path, header=False, date_format="%Y-%m-%d")


def doe():
    """Every US LNG cargo since 2016, from DOE's Natural Gas Imports and Exports Monthly. The
    workbook name carries its date range, so the link is read off the year's page; the one
    sheet used is kept as csv, columns as published. curl, because energy.gov refuses urllib."""
    curl = ["curl", "-sS", "-L", "--retry", "3", "--max-time", "300", "-A", "Mozilla/5.0"]
    year = pd.Timestamp.now().year
    page = subprocess.run(curl + [DOE + str(year)], capture_output=True, check=True).stdout
    href = re.search(r'href="([^"]*LNG%20Exports%20and%20Re-Exports%20Details[^"]*\.xlsx)"',
                     page.decode("utf-8", "ignore")).group(1)
    book = subprocess.run(curl + ["https://www.energy.gov" + href], capture_output=True,
                          check=True).stdout
    cargoes = pd.read_excel(io.BytesIO(book), sheet_name="By Vessel and ISO Container")
    (c.DATA / "flows").mkdir(exist_ok=True)
    cargoes.to_csv(c.DATA / "flows" / "doe_lng_cargoes.csv", index=False, date_format="%Y-%m-%d")
    print(f"DOE: {len(cargoes)} cargoes to {cargoes['Arrival/Departure Date'].max():%Y-%m-%d}")


def main():
    doe()
    os.environ["TZ"] = "UTC"  # tvDatafeed returns the stamps in the machine's local time
    time.tzset()
    tv = TvDatafeed()
    now = pd.Timestamp.now().to_period("M")
    for product, (symbol, exchange, folder) in FEEDS.items():
        for month in pd.period_range(now + MONTHS[0], now + MONTHS[1], freq="M"):
            code = f"{c.MONTH_CODES[month.month - 1]}{month.year}"
            bars = get(tv, symbol + code, exchange)
            if bars is None:  # never the continuous series: one file, one contract
                print(f"{product}{code}: nothing returned, skipped")
                continue
            save(bars, c.DATA / folder / f"{product}{code}.csv")
            print(f"{product}{code}: {len(bars)} rows")


if __name__ == "__main__":
    main()
