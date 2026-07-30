# Smart Rental Tracking

Equipment rental monitoring built on the Caterpillar hackathon dataset (7 assets, `data/equipment.csv`).
All decision logic lives in pure functions in `src/analytics.py` — no AWS, no network, no framework
imports — so it is fully unit-testable and the dashboard is a thin rendering layer on top.

## Run

```bash
python3 -m venv .venv
.venv/bin/pip install pandas pytest streamlit altair

.venv/bin/python -m pytest -q          # 47 tests
.venv/bin/streamlit run app/dashboard.py
```

Dashboard: http://localhost:8501

## Layout

| Path | Role |
|---|---|
| `data/equipment.csv` | Source dataset, `NULL` strings preserved as in the original sheet |
| `src/models.py` | `Equipment` dataclass mirroring the CSV columns |
| `src/loader.py` | CSV → `Equipment` objects; normalises `NULL`/blank to `None` |
| `src/analytics.py` | Pure logic: utilization, status, overdue, anomalies, site summary |
| `tests/test_analytics.py` | Covers every analytics function against the real dataset rows |
| `app/dashboard.py` | Streamlit UI (black / white / Cat yellow `#FFCC00`) |

## Core metric

`utilization_rate = engine_hours / (engine_hours + idle_hours)`, returning `0.0` when both are zero.
Under-utilized below 20%, healthy at or above 80%. This one number drives the IDLE badge, the
under-utilization anomaly, and the per-site averages.

## Status precedence

`UNASSIGNED > OVERDUE > IDLE > ACTIVE`

An asset nobody owns is the more urgent problem, and it is also the one that makes an overdue date
meaningless — there is no operator to chase for the return. EQX1002 and EQX1007 are both technically
overdue, but they surface as UNASSIGNED.

## What the dataset actually says

Two readings worth stating up front, because they change what the features do:

**1. The NULLs are in Site ID and Last Operator ID, not Check-In Date.** Both EQX1002 and EQX1007 have
valid check-in dates (2025-03-10 and 2025-03-20). So the anomaly is *"checked out with no site
allocation and no operator"* — an asset that is being billed while nobody knows where it is or who has
it. That maps directly to the brief's first pain point, equipment lost or unaccounted for.

**2. Every row has a Check-Out Date, and `check_out − check_in == rental_days` in all 7 cases.** These
are closed historical rentals. Overdue is therefore computed as
`expected_return = check_out_date + rental_days` per spec — the scheduled return of the *next* rental
cycle. At the default `today` of 2025-06-01 all seven are already past that date (5 OVERDUE +
2 UNASSIGNED), so the sidebar date input exists to make the logic demonstrable: **set it to 2025-03-05
to see all four statuses at once** (2 ACTIVE, 2 IDLE, 1 OVERDUE, 2 UNASSIGNED).

| Asset | Utilization | Reading |
|---|---|---|
| EQX1005 | 100% (8 engine / 0 idle) | Healthy baseline — the shape of a well-deployed asset |
| EQX1003 | 94% | Healthy |
| EQX1006 | 33% | Acceptable |
| EQX1004 | 18% | Under-utilized — reallocate before renting another excavator |
| EQX1001 | 13% | Under-utilized |
| EQX1002 | 0% (0 engine / 11 idle, 20 days) | Ghost asset — rented, never used, unassigned |
| EQX1007 | 0% (0 engine / 12 idle, 12 days) | Ghost asset |

The unassigned bucket accounts for **364 idle hours** billed against zero engine hours.

## Feature → expected outcome

| Brief | Where |
|---|---|
| Asset dashboard with live status | Colour-coded badges + per-row utilization bars |
| Check-in / check-out (QR/RFID sim) | Scan widget; state held in `st.session_state` |
| Usage logging | Engine/idle hours per day, rental days, expected return, days to due |
| Summary: rented hours, per site, downtime | Per-Site Summary chart + table from `site_summary()` |
| Overdue alerts and notification | Alerts panel, `is_overdue` / `due_soon(threshold=2)` |
| Anomaly detection | `detect_anomalies()` → plain-language reasons in the alerts panel |

**The check-in guardrail is the fix for EQX1002.** A scan-in is rejected unless both a Site ID and an
Operator ID are supplied, which makes a NULL check-in structurally impossible rather than a data-entry
convention. Verified in a browser: selecting EQX1002 and submitting empty fields is blocked and records
nothing; supplying both clears the UNASSIGNED status.

## Known gaps

- **Fuel usage and GPS location** are in the brief's usage-logging outcome but absent from the dataset,
  so no column was invented for them. Adding them is a loader + dataclass change; the analytics
  signature does not move.
- **Demand forecasting** is not implemented. With 7 closed rentals and no repeat cycles per site there
  is no time series to fit — any forecast would be a fabricated number. The honest version is the
  aggregate the data does support: S003/S004 hold the under-utilized excavators while the unassigned
  bucket carries 364 idle hours, so the recommendation is reallocation before new rentals. Wire real
  forecasting once multiple rental cycles per site exist.
