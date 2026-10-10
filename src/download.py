"""Fetch the raw csv files into data/ from TradingView, one per contract. Needs tvDatafeed;
nothing else does, and the csv files are committed, so the repo never has to run this.

    python -m src.download
"""

import os
import time

import pandas as pd
from tvDatafeed import Interval, TvDatafeed

from src import config as c

# product -> TradingView symbol root, exchange, folder under data/
FEEDS = {"JKM": ("JKM", "NYMEX", "lng"), "NWM": ("NWM", "NYMEX", "lng"),
         "BLNG2": ("BG2", "NYMEX", "freight"), "BLNG3": ("BG3", "NYMEX", "freight")}
MONTHS = (-12, 4)  # contracts from a year back to four months out: Tokyo's JKM is M+1 of M+3
BARS = 100         # settles per contract, enough to reach back to a BLNG contract's loading month


def get(tv, symbol, exchange):
    for _ in range(3):  # the socket drops now and then
        bars = tv.get_hist(symbol=symbol, exchange=exchange, interval=Interval.in_daily,
                           n_bars=BARS)
        if bars is not None and not bars.empty:
            return bars


def save(bars, path):
    # a daily bar is stamped at its session open, for CME the evening before: +6h lands it on
    # its trade date, whatever the season
    close = bars["close"]
    close.index = close.index + pd.Timedelta(hours=6)
    close.to_csv(path, header=False, date_format="%Y-%m-%d")


def main():
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
