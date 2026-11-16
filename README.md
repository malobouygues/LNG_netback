# US Gulf LNG netback

What is the netback of a US Gulf FOB cargo from Tokyo (JKM), via Panama or the Cape, against Rotterdam (NWE) ?

## Notebooks

| Notebook | Content |
|---|---|
| [`notebooks/01_data.ipynb`](notebooks/01_data.ipynb) | Data pipeline: sources and conventions, raw files into DuckDB, validation, point-in-time stamps, contract selection, `merge_asof` alignment, no-look-ahead assertions, final dataset |
| [`notebooks/02_netback.ipynb`](notebooks/02_netback.ipynb) | Research and results: key findings, method, assumptions (observed / sourced / assumed), cost stack, historical replay, Panama against the Cape, break-even spread, sensitivities, a check against the cargoes that actually sailed (DOE), limitations |

Both are committed with their outputs and read on GitHub without being run.

## Run

```bash
pip install -r requirements.txt
python -m src.download      # optional: appends new settles and refreshes the DOE cargo list, needs tvDatafeed
jupyter lab                 # run notebooks/01_data.ipynb, then notebooks/02_netback.ipynb
```

Notebook 01 builds the database itself. The same two steps from a shell are `python -m src.sql` and `python -m src.data`, run from the repository root.

## Data architecture

```
data/lng/*.csv, data/freight/*.csv   raw files, one per contract; download only ever appends to them
data/flows/doe_lng_cargoes.csv       every US LNG cargo since 2016, as published by DOE
data/lng.duckdb                      built from the files, not committed
  raw_settles                        table: file, trade_date, settle, ingested_at; key (file, trade_date)
  futures                            view: product, contract, delivery_month, trade_date, settle, unit
  panel                              table: one row per route and trade date, both legs as readable at
                                     the New York close, with the date and instant of each settle used
  raw_cargoes, cargoes, flows        DOE list as published; Gulf coast cargoes by ship with their
                                     region; monthly volumes by region
src/config.py                        paths, market closes, every assumption with its unit and source
src/download.py                      TradingView daily bars, one contract at a time
src/sql.py                           raw files -> raw_settles -> futures; idempotent
src/data.py                          contract selection, merge_asof backward on UTC instants, panel
src/netback.py                       the cost stack, USD per loaded MMBtu
```

Loading twice adds no row. A settle keeps its first print; a later difference at the vendor is reported by the download, not written.

## Principal results

Data through 12 November 2026, 471 trade dates since November 2024, USD/MMBtu FOB US Gulf.

| | Tokyo via Panama | Tokyo via the Cape | Rotterdam |
|---|---|---|---|
| Mean netback | 13.82 | 13.28 | 13.86 |
| Mean arb against Rotterdam | -0.04 | -0.58 | |
| Days Tokyo pays more | 41% | 10% | |
| JKM premium over NWE needed to break even | 0.85 | 1.41 | |

The actual JKM premium over NWE averaged 0.80. Freight is the main lever: 10,000 USD/day on BLNG3 moves the Cape arb by 0.25.

Checked against DOE's cargo records over the nineteen cargo months they share (February 2025 to August 2026): 75% of the gas shipped to Asia or Europe went to Europe, and Asia's share was 41% in the months the Panama arb was positive against 19% otherwise. The link does not survive a seasonal adjustment on so short a sample.

## Limits

Settlement marks from one vendor, on contracts with little or no liquidity: relative value, not executable prices. Henry Hub and liquefaction are left out because they cancel between destinations, so the netback is a destination value, not a margin. Cargo size is the median Gulf coast sailing in DOE's records; port costs and the Cape and Rotterdam voyage lengths are assumptions, and notebook 02 shows what each is worth.
