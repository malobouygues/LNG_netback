# US Gulf LNG netback toolkit

What a US Gulf FOB cargo nets back from Tokyo (JKM) against Rotterdam (TTF), and the arb between them. 54 contracts, 516 panel rows over 271 trade dates from 2025-01-02 to 2026-02-04, four modules, 21 tests.

The deliverable is one panel, `netback_usd_mmbtu` per `(route, trade_date)`, and one spread:

```
arb = netback_tokyo - netback_rotterdam        USD/MMBtu, FOB US Gulf
```

Positive means Asia out-bids Europe for the marginal US cargo. Negative means it stays in the Atlantic.

## Data

Four sources. The PIT timestamp is when a trader could act on the print, not the date on the file.

| Source | What | Unit | PIT timestamp |
|---|---|---|---|
| CME/NYMEX JKM (Platts) futures | DES Japan/Korea, delivery month | USD/MMBtu | trade date 16:30 Asia/Singapore, no DST |
| ICE Endex TTF futures | Dutch hub, delivery month | EUR/MWh | trade date 17:00 Europe/Amsterdam, DST-aware |
| CME LNG freight BLNG2/BLNG3-174 | Baltic round-trip TCE, US Gulf to Continent and to Japan | USD/day | trade date 16:00 Europe/London, DST-aware |
| EURUSD daily bars (TradingView FX_IDC) | USD per EUR | | label date plus 1 day, 17:00 America/New_York |

Each localises to UTC at ingestion, so a store holds one unambiguous instant per print.

The panel for trade date D is anchored at 17:00 America/New_York on D, the last of the four closes. Availability is proven rather than assumed: the builder raises if a joined settle or availability timestamp falls after the anchor. Every join carries a 5-calendar-day tolerance, so a contract that stops trading drops out instead of being carried forward indefinitely.

Four checks stand between a CSV and the panel, and each refuses rather than repairs: a settle printing after its contract can plausibly trade, a duplicate `(contract, trade_date)`, a non-positive LNG price, and any joined price stamped after the row's anchor.

Two layers, one direction. The raw CSVs are the immutable input and are never edited in place. DuckDB is the store and the query layer, rebuilt from scratch by `python src/data.py`, so it is never a second copy of the truth. It is DuckDB rather than SQLite for the native `TIMESTAMP WITH TIME ZONE`: the PIT instants survive the trip instead of flattening to text. `sql/schema.sql` holds the DDL and the keys, `sql/views.sql` the arb view; the questions worth asking live in the notebooks, next to the reasoning that prompted them.

## Contract selection

Month-based, so the choice cannot jump with the day of the trade date.

- Loading month: the calendar month after the trade month, which is the next loading program.
- Delivery month: the month holding the 15th of the loading month plus the voyage. Rotterdam at 10 days stays in the loading month, Tokyo at 20 days via Panama lands in the next one.
- Freight is the loading-month BLNG contract, fixed when the ship is. Destination is the delivery-month JKM or TTF contract, which is what the cargo sells against.

## Calculation

Every component is USD per loaded MMBtu, so they subtract exactly:

```
netback = P_dest - boiloff - regas - freight - canal - port
```

- `P_dest`: JKM as quoted. TTF is EUR/MWh, converted at `EUR/MWh * EURUSD / 3.412142`.
- `boiloff = P_dest * (1 - (1-r)^d)`, r = 0.15% per laden day. Boil-off eats the remaining cargo, so it compounds, and the lost energy is valued where it would have sold.
- `regas`: TTF is a post-regas hub price, so the Rotterdam leg nets back a terminal fee on delivered energy. JKM is DES and nets nothing back.
- `freight = rate * (one_way * 2 + port_days) / cargo`. Baltic BLNG rates are round-trip TCE, so the cargo pays the ballast leg home.
- `canal` and `port`: lump sums spread over the cargo, Panama tolls on the Tokyo route only.

Every assumption is a named constant in [src/config.py](src/config.py), each with its unit.

## Limitations

- Round-trip freight basis. BLNG assessments are read as round-trip TCE and the cargo is charged 2 one-way legs plus 2 port days of hire. A desk that reads BLNG as one-way-equivalent sets `round_trip_factor` to 1.0, which is a config change, not a code change.
- Panama Canal at base tolls. $1.0m round trip, about $0.29/MMBtu. Post-2023 auction premia run to multiples of that, and congestion can force Suez or Cape routing at 30-plus days. The fixed 20-day voyage does not flex with canal conditions.
- Regas is a placeholder. $0.50/MMBtu, a Gate-anchored order of magnitude. It needs refreshing from published terminal tariffs before the Rotterdam leg is traded.
- FX bar labelling is unverified. The vendor does not document whether a daily bar is stamped at session open or close, so every bar is charged the worst case, available at label plus 1 day, 17:00 New York. The panel therefore prices TTF off the previous bar. That is conservative under either convention and costs basis points at daily granularity.
- Settle anchors are wall-clock conventions: 16:30 Singapore for the Platts window, 17:00 Amsterdam, 16:00 London. They are consistent and documented, but not exchange-verified publication times, and would need checking before any intraday use.
- JKM contract-month semantics. The delivery-month contract stands in for the DES price of a cargo arriving that month, while JKM month M actually settles on assessments from roughly the 16th of M-2 to the 15th of M-1. This is the standard desk simplification.
- Mid-month loading anchor. A real cargo has a laycan; the 15th-of-month convention is what makes contract selection deterministic.
- Ballast-leg economics. Boil-off is charged on the laden leg only, and heel and return-leg bunkers sit inside the round-trip hire. No insurance, commissions, credit or working capital.
- This routes a cargo, it does not price a lift. Liquefaction tolling, around 115% of Henry Hub plus a fixed fee, is sunk once the cargo is lifted and is out of scope, so the netback is not full FOB profitability.
- One unofficial vendor. 40 daily bars per contract through the unofficial TradingView API, with no cross-source check. The poison gate exists for this reason: the earlier fetcher could silently write continuous front-month data into a per-contract file, so any settle printing after a contract can plausibly trade is now refused at load.
- Negative freight is real. BLNG2 printed about -$1,100/day in the February 2025 Atlantic glut, so the freight loader deliberately does not check the sign. The LNG loader does, because a non-positive gas price is bad data.
- One year of trade dates. Enough to watch the arb flip, not enough for a seasonality claim.
- The two routes cover different spans. Rotterdam starts 2025-02-03 because the FX file starts then, and Tokyo ends 2026-01-30 because a February trade date needs JKMJ2026, which the committed CSVs do not include. Comparisons between routes belong on the 245 dates both cover.

## Layout

```
data/lng/           immutable raw CSVs, one file per contract
data/freight/
data/fx/
data/lng.duckdb     built by src/data.py, gitignored
src/config.py       paths, market conventions, every physical assumption with its unit
src/data.py         ingestion, timestamps, the cargo clock, the joins, staleness, the store
src/netback.py      the voyage economics and the arb
src/fetch.py        how the CSVs were downloaded; kept local, not committed
sql/schema.sql      DDL, explicit types, primary keys, units per table
sql/views.sql       v_netback_arb
src/test.py         21 tests, all on invariants
notebooks/          01 the data and its controls, 02 the netback and the arb
```

Read `src/config.py` for the assumptions, `src/data.py` for where the data comes from
and when it was knowable, `src/netback.py` for what the voyage leaves. That is the
whole model.

## Invariants

- A timestamp column is either a naive `trade_date` or an explicit `*_timestamp_utc`. There is no third kind.
- Every DST-zone localisation passes `nonexistent="shift_forward", ambiguous="raise"`, so a boundary anomaly fails instead of guessing.
- A per-contract raw file holds only that contract's settles. Enforced at fetch, which skips rather than substitutes, and again at load by the expiry gate.
- The panel never carries a price older than the 5-day tolerance, and never one stamped after the row's anchor. Both raise.
- The arb exists twice, in `netback.arb` and in `sql/views.sql`. A test asserts they agree.
- Data flows one way. Raw CSVs are never modified in place, DuckDB is rebuilt from them, and the notebooks read DuckDB only.

## Running it

```bash
python src/data.py
pytest src/test.py
```

Needs pandas, duckdb, matplotlib and pytest.

`src/data.py` reads the committed CSVs and writes `data/lng.duckdb`, which is gitignored.
Pass the file to pytest explicitly: `test.py` matches neither of pytest's default
collection patterns.

The charts live in the notebooks, which are committed with their outputs, so they read
on GitHub without being run. Nothing writes an image file.

Rerunning the notebooks needs jupyter. `src/fetch.py` is how the CSVs were downloaded,
needs tvDatafeed and is gitignored; nothing here needs it, because the CSVs are
committed.
