import sys
from datetime import date, datetime
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import analytics as an
import ml
from loader import load_equipment
from models import Equipment

CAT_YELLOW = "#FFCC00"
BLACK = "#000000"
WHITE = "#FFFFFF"

STATUS_COLORS = {
    an.ACTIVE: "#2E7D32",
    an.IDLE: "#757575",
    an.OVERDUE: "#C62828",
    an.UNASSIGNED: "#EF6C00",
}

st.set_page_config(page_title="Smart Rental Tracking", page_icon="🚜", layout="wide")

st.markdown(f"""
<style>
  .stApp {{ background: {BLACK}; color: {WHITE}; }}
  header[data-testid="stHeader"] {{ background: {BLACK}; }}
  section[data-testid="stSidebar"] {{ background: #111; border-right: 2px solid {CAT_YELLOW}; }}
  h1, h2, h3, h4 {{ color: {WHITE} !important; }}
  .cat-header {{ border-bottom: 4px solid {CAT_YELLOW}; padding-bottom: 12px; margin-bottom: 8px; }}
  .cat-title {{ font-size: 2.1rem; font-weight: 800; letter-spacing: .5px; }}
  .cat-title span {{ background: {CAT_YELLOW}; color: {BLACK}; padding: 0 10px; }}
  .cat-sub {{ color: #BDBDBD; font-size: .9rem; margin-top: 6px; }}
  .kpi {{ background: #141414; border: 1px solid #2A2A2A; border-top: 3px solid {CAT_YELLOW};
          padding: 14px 16px; height: 100%; }}
  .kpi-label {{ color: #9E9E9E; font-size: .72rem; text-transform: uppercase; letter-spacing: 1px; }}
  .kpi-value {{ color: {WHITE}; font-size: 1.9rem; font-weight: 700; line-height: 1.2; }}
  .badge {{ padding: 3px 10px; border-radius: 10px; color: {WHITE}; font-size: .72rem;
            font-weight: 700; letter-spacing: .5px; white-space: nowrap; }}
  table.cat {{ width: 100%; border-collapse: collapse; font-size: .86rem; }}
  table.cat th {{ background: {CAT_YELLOW}; color: {BLACK}; text-align: left; padding: 9px 10px;
                  font-size: .74rem; text-transform: uppercase; letter-spacing: .6px; }}
  table.cat td {{ padding: 9px 10px; border-bottom: 1px solid #262626; color: {WHITE}; }}
  table.cat tr:hover td {{ background: #1A1A1A; }}
  .bar-track {{ background: #333; height: 9px; width: 110px; border-radius: 5px; display: inline-block;
                vertical-align: middle; overflow: hidden; }}
  .bar-fill {{ height: 9px; border-radius: 5px; }}
  .bar-text {{ font-variant-numeric: tabular-nums; margin-left: 8px; font-size: .8rem; }}
  .alert {{ border-left: 4px solid; padding: 10px 14px; margin-bottom: 8px; background: #141414; }}
  .alert-id {{ font-weight: 700; color: {CAT_YELLOW}; }}
  .alert-reason {{ color: #CFCFCF; font-size: .84rem; margin-top: 3px; }}
  .ghost-note {{ background: #141414; border-left: 4px solid {CAT_YELLOW}; padding: 12px 14px;
                 font-size: .86rem; color: #DDD; }}
  button[kind="primary"] {{ background: {CAT_YELLOW} !important; color: {BLACK} !important;
                            border: none !important; font-weight: 700 !important; }}

  /* Navigation bar: horizontal tabs replace vertical scrolling between features.
     Streamlit 1.60 renders tabs via react-aria (data-testid=stTab), not baseweb. */
  [role="tablist"] {{ gap: 3px !important; background: #0C0C0C;
                      border-bottom: 2px solid {CAT_YELLOW} !important; padding: 0 !important; }}
  [data-testid="stTab"] {{ background: #161616; border-radius: 0 !important;
                           padding: 12px 22px !important; }}
  [data-testid="stTab"], [data-testid="stTab"] * {{ color: #B0B0B0 !important;
                           font-size: .82rem !important; font-weight: 700 !important;
                           letter-spacing: .6px; text-transform: uppercase; }}
  [data-testid="stTab"]:hover {{ background: #222; }}
  [data-testid="stTab"]:hover * {{ color: {WHITE} !important; }}
  [data-testid="stTab"][aria-selected="true"] {{ background: {CAT_YELLOW} !important; }}
  [data-testid="stTab"][aria-selected="true"] * {{ color: {BLACK} !important; }}
  /* Kill the default sliding underline so the filled tab reads as the indicator. */
  [role="tablist"]::after, [data-testid="stTab"]::after {{ display: none !important; }}
  [data-testid="stTabPanel"] {{ padding-top: 18px; }}
</style>
""", unsafe_allow_html=True)

fleet = load_equipment()


# ML runs against the source dataset and is cached so it trains once per session
# rather than on every widget interaction.
@st.cache_data(show_spinner=False)
def load_demand_model():
    return ml.predict_demand(load_equipment())


@st.cache_data(show_spinner=False)
def load_demand_aggregate():
    return ml.demand_by_type_site(load_equipment())


@st.cache_data(show_spinner=False)
def load_crosscheck():
    return ml.isolation_forest_crosscheck(load_equipment())


@st.cache_data(show_spinner=False)
def load_disagreement():
    return ml.crosscheck_disagreement(load_equipment())


# --- session state: simulated QR/RFID check-in/out overrides ---
if "overrides" not in st.session_state:
    st.session_state.overrides = {}
if "last_scan" not in st.session_state:
    st.session_state.last_scan = None


def apply_overrides(rows):
    out = []
    for row in rows:
        override = st.session_state.overrides.get(row.equipment_id)
        if override is None:
            out.append(row)
            continue
        out.append(Equipment(
            equipment_id=row.equipment_id,
            type=row.type,
            site_id=override.get("site_id", row.site_id),
            check_in_date=override.get("check_in_date", row.check_in_date),
            check_out_date=override.get("check_out_date", row.check_out_date),
            engine_hours_per_day=row.engine_hours_per_day,
            idle_hours_per_day=row.idle_hours_per_day,
            rental_days=override.get("rental_days", row.rental_days),
            operator_id=override.get("operator_id", row.operator_id),
        ))
    return out


def util_bar(rate):
    color = "#2E7D32" if rate >= an.HEALTHY_UTILIZATION_THRESHOLD else (
        CAT_YELLOW if rate >= an.UNDER_UTILIZED_THRESHOLD else "#C62828")
    pct = int(round(rate * 100))
    return (f'<div class="bar-track"><div class="bar-fill" style="width:{pct}%;background:{color}"></div></div>'
            f'<span class="bar-text">{pct}%</span>')


def build_alerts(rows, today):
    """Most urgent first: unassigned, then overdue, then due-soon, then anomalies."""
    severity = {an.UNASSIGNED: 0, an.OVERDUE: 1, "DUE SOON": 2, "ANOMALY": 3}
    alerts = []
    for row in rows:
        reasons = an.detect_anomalies(row)
        remaining = an.days_until_due(row, today)

        if an.is_unassigned(row):
            alerts.append((severity[an.UNASSIGNED], row.equipment_id, an.UNASSIGNED,
                           "Unaccounted for — no operator or site on record", reasons))
        elif an.is_overdue(row, today):
            alerts.append((severity[an.OVERDUE], row.equipment_id, an.OVERDUE,
                           f"{abs(remaining)} days past expected return "
                           f"({an.expected_return(row.check_out_date, row.rental_days)})", reasons))
        elif an.due_soon(row, today):
            alerts.append((severity["DUE SOON"], row.equipment_id, "DUE SOON",
                           f"Due back in {remaining} day(s) — confirm return or extension", reasons))
        elif reasons:
            alerts.append((severity["ANOMALY"], row.equipment_id, "ANOMALY",
                           "Usage pattern outside healthy range", reasons))

    alerts.sort(key=lambda a: (a[0], a[1]))
    return alerts


# --- sidebar ---
with st.sidebar:
    st.markdown(f"### <span style='color:{CAT_YELLOW}'>Controls</span>", unsafe_allow_html=True)
    today = st.date_input("Today (drives overdue logic)", value=date(2025, 6, 1))
    st.caption(
        "Every rental in the source sheet is already past its return date at "
        "2025-06-01. Set this to **2025-03-05** to see a mixed board "
        "(ACTIVE / IDLE / OVERDUE / UNASSIGNED all present)."
    )
    st.divider()
    st.markdown("**Thresholds**")
    st.caption(
        f"Under-utilized below {an.UNDER_UTILIZED_THRESHOLD:.0%} · "
        f"healthy at or above {an.HEALTHY_UTILIZATION_THRESHOLD:.0%} · "
        "due-soon window 2 days"
    )
    if st.session_state.overrides:
        st.divider()
        st.markdown("**Simulated scans this session**")
        for eid, ov in st.session_state.overrides.items():
            state = "checked out" if ov.get("check_out_date") else "checked in"
            st.caption(f"{eid} — {state}")
        if st.button("Reset scans"):
            st.session_state.overrides = {}
            st.session_state.last_scan = None
            st.rerun()

rows = apply_overrides(fleet)

# --- header (always visible) ---
stamp = st.session_state.last_scan or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
st.markdown(f"""
<div class="cat-header">
  <div class="cat-title"><span>CAT</span>&nbsp; SMART RENTAL TRACKING</div>
  <div class="cat-sub">Fleet telemetry · last updated {stamp} · treating source data as live feed</div>
</div>
""", unsafe_allow_html=True)

# --- KPI row (always visible, so fleet status is never a click away) ---
statuses = [an.status(r, today) for r in rows]
fleet_util = sum(an.row_utilization(r) for r in rows) / len(rows)
alerts = build_alerts(rows, today)

kpis = [
    ("Total assets", len(rows)),
    ("Active", statuses.count(an.ACTIVE)),
    ("Overdue", statuses.count(an.OVERDUE)),
    ("Unassigned", statuses.count(an.UNASSIGNED)),
    ("Fleet avg utilization", f"{fleet_util:.0%}"),
]
for col, (label, value) in zip(st.columns(5), kpis):
    col.markdown(
        f'<div class="kpi"><div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div></div>',
        unsafe_allow_html=True,
    )

st.write("")

# --- navigation bar ---
tab_fleet, tab_alerts, tab_sites, tab_scan, tab_demand, tab_ml = st.tabs([
    "Fleet",
    f"Alerts ({len(alerts)})",
    "Site Analytics",
    "Check-In / Out",
    "Demand Forecast",
    "Anomaly Cross-Check",
])

# --- Fleet: the asset dashboard ---
with tab_fleet:
    st.markdown("#### Asset Dashboard")
    header = ("Equipment", "Type", "Site", "Operator", "Status", "Utilization",
              "Engine h/day", "Idle h/day", "Rental days", "Expected return", "Days to due")
    body = ""
    for row in rows:
        state = an.status(row, today)
        badge = f'<span class="badge" style="background:{STATUS_COLORS[state]}">{state}</span>'
        due = an.expected_return(row.check_out_date, row.rental_days) if row.check_out_date else None
        remaining = an.days_until_due(row, today)
        remaining_text = "open rental" if remaining is None else (
            f"{remaining} d" if remaining >= 0 else f"{abs(remaining)} d late")
        body += (
            "<tr>"
            f"<td><b>{row.equipment_id}</b></td><td>{row.type}</td>"
            f"<td>{row.site_id or '—'}</td><td>{row.operator_id or '—'}</td>"
            f"<td>{badge}</td><td>{util_bar(an.row_utilization(row))}</td>"
            f"<td>{row.engine_hours_per_day:g}</td><td>{row.idle_hours_per_day:g}</td>"
            f"<td>{row.rental_days}</td><td>{due.isoformat() if due else '—'}</td>"
            f"<td>{remaining_text}</td></tr>"
        )
    st.markdown(
        '<table class="cat"><thead><tr>' + "".join(f"<th>{h}</th>" for h in header) +
        "</tr></thead><tbody>" + body + "</tbody></table>",
        unsafe_allow_html=True,
    )

# --- Alerts ---
with tab_alerts:
    st.markdown("#### Alerts — most urgent first")
    if not alerts:
        st.success("No alerts — every asset is assigned, on schedule, and within healthy utilization.")
    else:
        colors = {an.UNASSIGNED: STATUS_COLORS[an.UNASSIGNED], an.OVERDUE: STATUS_COLORS[an.OVERDUE],
                  "DUE SOON": CAT_YELLOW, "ANOMALY": "#757575"}
        for _, eid, kind, headline, reasons in alerts:
            reason_html = "".join(f"<div class='alert-reason'>• {r}</div>" for r in reasons)
            st.markdown(
                f'<div class="alert" style="border-color:{colors[kind]}">'
                f'<span class="badge" style="background:{colors[kind]};'
                f'color:{BLACK if kind == "DUE SOON" else WHITE}">{kind}</span> '
                f'<span class="alert-id">{eid}</span>'
                f'<div class="alert-reason">{headline}</div>{reason_html}</div>',
                unsafe_allow_html=True,
            )

# --- Site Analytics ---
with tab_sites:
    st.markdown("#### Per-Site Summary")
    summary = an.site_summary(rows)
    chart_df = pd.DataFrame([
        {"Site": site, "Measure": measure, "Hours": v[key]}
        for site, v in sorted(summary.items())
        for measure, key in [("Engine hours", "total_engine_hours"), ("Idle hours", "total_idle_hours")]
    ])

    left, right = st.columns([1.1, 1])
    with left:
        chart = (
            alt.Chart(chart_df)
            .mark_bar()
            .encode(
                x=alt.X("Site:N", axis=alt.Axis(labelAngle=0, labelColor="#DDD", titleColor="#DDD")),
                y=alt.Y("Hours:Q", axis=alt.Axis(labelColor="#DDD", titleColor="#DDD", grid=True)),
                xOffset="Measure:N",
                color=alt.Color(
                    "Measure:N",
                    scale=alt.Scale(domain=["Engine hours", "Idle hours"], range=["#2E7D32", CAT_YELLOW]),
                    legend=alt.Legend(orient="top", title=None, labelColor="#DDD"),
                ),
                tooltip=["Site", "Measure", "Hours"],
            )
            .properties(height=300)
            .configure_view(strokeWidth=0)
            .configure_axis(gridColor="#262626", domainColor="#444")
        )
        st.altair_chart(chart, use_container_width=True)
    with right:
        table_df = pd.DataFrame([
            {"Site": site, "Assets": v["count"], "Engine h": v["total_engine_hours"],
             "Idle h": v["total_idle_hours"], "Downtime h": v["downtime_hours"],
             "Avg util": f"{v['avg_utilization']:.0%}"}
            for site, v in sorted(summary.items())
        ])
        st.dataframe(table_df, hide_index=True, width="stretch")

# --- Check-in / Check-out (QR/RFID simulation) ---
with tab_scan:
    st.markdown("#### Check-in / Check-out — QR / RFID scan simulation")
    st.markdown(
        '<div class="ghost-note">A scan-in cannot be recorded without both a site and an operator. '
        'That constraint is exactly what would have prevented <b>EQX1002</b> and <b>EQX1007</b> from '
        'sitting in the fleet as ghost assets — rented, billed, and unaccounted for.</div>',
        unsafe_allow_html=True,
    )
    st.write("")

    ids = [r.equipment_id for r in rows]
    by_id = {r.equipment_id: r for r in rows}

    pick_col, form_col = st.columns([1, 2])
    with pick_col:
        selected_id = st.selectbox("Equipment ID", ids)
        selected = by_id[selected_id]
        currently_out = selected.check_out_date is not None
        st.markdown(
            f'<span class="badge" style="background:{STATUS_COLORS[an.status(selected, today)]}">'
            f'{an.status(selected, today)}</span>', unsafe_allow_html=True)
        st.caption(
            f"Site {selected.site_id or '—'} · Operator {selected.operator_id or '—'} · "
            f"{'checked out ' + selected.check_out_date.isoformat() if currently_out else 'on site'}"
        )

    with form_col:
        if currently_out:
            st.markdown("**Scan in** — returns the asset to active service")
            # Keys are scoped per equipment so switching assets re-prefills from that
            # asset's own record instead of carrying over the previous selection.
            site_in = st.text_input("Site ID", value=selected.site_id or "", key=f"site_in_{selected_id}")
            op_in = st.text_input("Operator ID", value=selected.operator_id or "", key=f"op_in_{selected_id}")
            days_in = st.number_input("Rental days", min_value=1, max_value=365,
                                      value=max(selected.rental_days, 1), key=f"days_in_{selected_id}")
            if st.button("Simulate scan-in", type="primary"):
                if not site_in.strip() or not op_in.strip():
                    st.error("Blocked: a scan-in requires both a Site ID and an Operator ID. "
                             "This is the guardrail that makes a NULL check-in impossible.")
                else:
                    st.session_state.overrides[selected_id] = {
                        "site_id": site_in.strip(), "operator_id": op_in.strip(),
                        "check_in_date": today, "check_out_date": None,
                        "rental_days": int(days_in),
                    }
                    st.session_state.last_scan = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    st.rerun()
        else:
            st.markdown("**Scan out** — closes the rental and stops the billing clock")
            st.caption(f"Check-out will be recorded as {today.isoformat()}.")
            if st.button("Simulate scan-out", type="primary"):
                st.session_state.overrides[selected_id] = {
                    "site_id": selected.site_id, "operator_id": selected.operator_id,
                    "check_in_date": selected.check_in_date, "check_out_date": today,
                    "rental_days": selected.rental_days,
                }
                st.session_state.last_scan = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                st.rerun()

# --- Demand Forecast (ML) ---
# Trained on the source dataset rather than the session-modified fleet: the model
# describes historical rental behaviour, not simulated scans.
with tab_demand:
    st.markdown("#### Demand Prediction — Random Forest")

    demand = load_demand_model()
    m = demand.metrics

    mc = st.columns(4)
    mc[0].markdown(f'<div class="kpi"><div class="kpi-label">Honest R² (leave-one-out)</div>'
                   f'<div class="kpi-value">{m["loo_r2"]}</div></div>', unsafe_allow_html=True)
    mc[1].markdown(f'<div class="kpi"><div class="kpi-label">Mean abs error</div>'
                   f'<div class="kpi-value">{m["loo_mae_days"]}d</div></div>', unsafe_allow_html=True)
    mc[2].markdown(f'<div class="kpi"><div class="kpi-label">Naive baseline error</div>'
                   f'<div class="kpi-value">{m["baseline_mae_days"]}d</div></div>', unsafe_allow_html=True)
    mc[3].markdown(f'<div class="kpi"><div class="kpi-label">Training samples</div>'
                   f'<div class="kpi-value">{m["n_samples"]}</div></div>', unsafe_allow_html=True)

    st.markdown(
        f'<div class="ghost-note">Target is <b>rental_days</b>, so it is excluded from the features — '
        f'including it leaks the label and inflates R² to {m["in_sample_r2"]} while teaching the model '
        f'nothing. Metrics are leave-one-out cross-validated; at n={m["n_samples"]} a train/test split '
        f'silently degenerates to train == test. The model beats the always-predict-the-mean baseline '
        f'by {round(m["baseline_mae_days"] - m["loo_mae_days"], 1)} days — a real but modest gain, '
        f'which is the honest ceiling on {m["n_samples"]} rentals.</div>',
        unsafe_allow_html=True,
    )
    st.write("")

    dl, dr = st.columns([1.4, 1])
    with dl:
        st.dataframe(demand.predictions, hide_index=True, width="stretch")
    with dr:
        st.caption("Feature importance")
        st.dataframe(
            pd.DataFrame({"Feature": list(demand.feature_importances),
                          "Importance": list(demand.feature_importances.values())}),
            hide_index=True, width="stretch",
        )

    st.caption("Pre-positioning view — lowest utilization first, i.e. reallocate before renting more:")
    st.dataframe(load_demand_aggregate(), hide_index=True, width="stretch")

# --- Anomaly cross-check (secondary signal, deliberately shown) ---
with tab_ml:
    st.markdown("#### Anomaly Cross-Check — Isolation Forest vs. Rules")

    disagreement = load_disagreement()
    st.markdown(
        f'<div class="alert" style="border-color:{CAT_YELLOW}">'
        f'<span class="badge" style="background:{CAT_YELLOW};color:{BLACK}">FINDING</span> '
        f'<span class="alert-id">Agreement rate: {disagreement["agreement_rate"]:.0%}</span>'
        f'<div class="alert-reason">{disagreement["verdict"]}</div>'
        f'<div class="alert-reason">Flagged by the model only: '
        f'{", ".join(disagreement["flagged_by_ml_only"]) or "none"} — these are the '
        f'best-utilized machines in the fleet.</div>'
        f'<div class="alert-reason">Caught by the rules only: '
        f'{", ".join(disagreement["flagged_by_rules_only"]) or "none"} — including both ghost assets.</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.dataframe(load_crosscheck(), hide_index=True, width="stretch")
    st.caption("Rule-based detection is the shipping signal. The unsupervised model is shown as a "
               "cross-check because on this fleet it inverts: under-utilization is the majority, so "
               "statistical rarity points at the healthy assets.")
