"""Load the raw csv files into data/lng.duckdb, and read it back.

    python -m src.sql

Two layers. raw_settles holds the files as they are: one row per file and trade date, stamped
with ingested_at, the time the file was last downloaded. Loading is idempotent: the primary key
is the file and the trade date, a row already there is left alone, so running it twice adds
nothing and a settle keeps its first print.

futures is the clean layer, a view on raw_settles: the contract is the file name, product,
month code and year, so JKMH2025.csv is March 2025 JKM, and each settle carries its unit. It
keeps the trade date on the file; when a print became readable is data.py's business.

raw_cargoes is DOE's list of every US LNG cargo, as published. DOE republishes the whole list
every month, so the table is replaced, which is idempotent too. cargoes is its clean view: the
cargoes that left the Gulf coast by ship, with the region each went to.
"""

from datetime import datetime, timezone

import duckdb

from src import config as c


def query(sql):
    with duckdb.connect(c.DB, read_only=True) as con:
        con.execute("SET TimeZone = 'UTC'")  # instants read back in UTC on any machine
        return con.sql(sql).df()


def write(table, df):
    """Replace one derived table (the panel) with a frame."""
    with duckdb.connect(c.DB) as con:
        con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM df")


def build():
    """Load the csv files into raw_settles and (re)create the futures view."""
    with duckdb.connect(c.DB) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS raw_settles (
                file VARCHAR,            -- folder and file name under data/
                trade_date DATE,
                settle DOUBLE,
                ingested_at TIMESTAMP,   -- UTC, when the file was last downloaded
                PRIMARY KEY (file, trade_date)
            )""")
        before = con.sql("SELECT COUNT(*) FROM raw_settles").fetchone()[0]
        for path in sorted(c.DATA.glob("lng/*.csv")) + sorted(c.DATA.glob("freight/*.csv")):
            ingested_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            ingested_at = ingested_at.replace(tzinfo=None, microsecond=0)
            con.execute(f"""
                INSERT INTO raw_settles
                SELECT ?, trade_date, settle, ?
                FROM read_csv('{path}', header = false,
                              columns = {{'trade_date': 'DATE', 'settle': 'DOUBLE'}})
                ON CONFLICT DO NOTHING""", [f"{path.parent.name}/{path.name}", ingested_at])
        after = con.sql("SELECT COUNT(*) FROM raw_settles").fetchone()[0]
        print(f"{after - before:,} rows added to raw_settles, {after:,} in total")

        # the contract is the file name; its last five characters are the month code and the year
        con.execute(f"""
            CREATE OR REPLACE VIEW futures AS
            SELECT left(contract, length(contract) - 5) AS product, contract,
                   make_date(right(contract, 4)::INTEGER,
                             strpos('{c.MONTH_CODES}', contract[-5]), 1) AS delivery_month,
                   trade_date, settle,
                   CASE WHEN contract LIKE 'BLNG%' THEN 'USD/day' ELSE 'USD/MMBtu' END AS unit
            FROM (SELECT parse_filename(file, true) AS contract, trade_date, settle
                  FROM raw_settles)""")

        path = c.DATA / "flows" / "doe_lng_cargoes.csv"
        ingested_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        ingested_at = ingested_at.replace(tzinfo=None, microsecond=0)
        con.execute(f"CREATE OR REPLACE TABLE raw_cargoes AS "
                    f"SELECT *, ? AS ingested_at FROM read_csv('{path}')", [ingested_at])
        # US-produced gas, by ship, from a Louisiana or Texas terminal: the cargo the netback prices
        con.execute(f"""
            CREATE OR REPLACE VIEW cargoes AS
            SELECT "Arrival/Departure Date" AS departure_date, "Tanker" AS tanker,
                   "Point of Entry or Exit" AS terminal, "Docket Term" AS term,
                   "Country" AS country,
                   CASE WHEN "Country" IN {tuple(c.ASIA)} THEN 'asia'
                        WHEN "Country" IN {tuple(c.EUROPE)} THEN 'europe'
                        ELSE 'other' END AS region,
                   "Volume (MMCF)" AS mmcf
            FROM raw_cargoes
            WHERE "Activity" = 'Exports' AND "Mode of Transport" = 'Vessel'
              AND ("Point of Entry or Exit" LIKE '%, LA' OR "Point of Entry or Exit" LIKE '%, TX')
              AND "Arrival/Departure Date" IS NOT NULL""")
        print(f"{con.sql('SELECT COUNT(*) FROM raw_cargoes').fetchone()[0]:,} rows in raw_cargoes")


if __name__ == "__main__":
    build()
    print(query("SELECT product, unit, COUNT(DISTINCT contract) AS contracts, "
                "MIN(trade_date) AS first, MAX(trade_date) AS last, COUNT(*) AS settles "
                "FROM futures GROUP BY 1, 2 ORDER BY 1"))
