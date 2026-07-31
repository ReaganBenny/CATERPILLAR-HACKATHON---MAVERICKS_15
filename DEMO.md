# Panel demo script

Target: **8 minutes** of demo, leaving room for questions. Three people, three
roles. Rehearse the click-path twice — the second run is always 40% faster.

Set the sidebar date to **2025-06-01** before you start. Do not change it live
unless asked (there is a reason, below).

---

## Roles

| Person | Owns |
|---|---|
| A — Narrative | Problem, data findings, closing. Does not touch a keyboard. |
| B — Driver | Drives the dashboard. Says little; A narrates over them. |
| C — Cloud | Runs the Lambda invoke, shows the email and CloudWatch. |

---

## The arc (8 minutes)

### 0:00–1:00 — Open with the finding, not the architecture

> "Before we built anything we read the seven rows you gave us. Two of them —
> EQX1002 and EQX1007 — have no site and no operator, zero engine hours, and
> eleven to twelve idle hours a day. They were rented, billed, and never used.
> Those two alone account for **364 idle hours charged against zero engine
> hours, and roughly 1,236 litres of diesel burned going nowhere**. Fleet-wide
> the idle burn is over **4,100 litres**. That is what our system exists to
> surface."

**Say "simulated" once, early, and you never have to defend it again:** fuel and
GPS are a separate simulated feed, because the supplied schema carries neither.
The seven supplied rows are untouched — `data/equipment.csv` is byte-identical
to what you were given, which is worth saying out loud.

Do not open with a tech-stack slide. Open with their money.

### 1:00–2:30 — Fleet tab

B clicks **Fleet**. Point at the two orange UNASSIGNED badges and the red
utilization bars.

> "Every asset, live status, utilization per row. Green is healthy — EQX1005 at
> 100%. Red is our problem set."

### 2:30–3:15 — Alerts tab

> "Same data, ranked by urgency, and every alert explains itself in plain
> language a yard manager can act on — not a score."

Read one aloud verbatim: *"0 engine hours over 11 idle hours — rented for 20
days and never used."*

### 3:15–3:45 — Location tab

B clicks **Location**. Point at the two orange markers sitting away from every
registered site.

> "The GPS works — that is the point. We know exactly where the crane is. What
> nobody knows is *why* it is there, because it is assigned to no site and no
> operator. A five-kilometre geofence turns 'lost equipment' into an exception
> you can act on the same day."

### 3:30–4:30 — Check-In / Out tab: the fix

B selects **EQX1002**, leaves the fields empty, clicks **Simulate scan-in**.
The red **Blocked** message appears.

> "This is the fix. A scan-in is refused unless both a site and an operator are
> present. The NULL that created the ghost asset is now structurally impossible,
> not a data-entry convention."

Then fill both fields, submit, and show the status change. **This beat wins the
demo — do not rush it.**

### 4:30–5:30 — Demand Forecast tab

> "Random Forest predicting rental duration. We report **R² of 0.42**, not the
> 0.94 in-sample number, because at seven rows in-sample R² is fiction. An
> earlier version had `rental_days` as both a feature and the target — that leak
> inflated R² to 0.97 while the model learned nothing. We removed it and there
> is now a regression test so it cannot come back."

Judges respect a team that reports the lower, honest number and explains why.

### 5:30–6:30 — Anomaly Cross-Check tab: your differentiator

> "We also ran Isolation Forest, the standard unsupervised approach. It flags
> EQX1005 and EQX1003 — our two *healthiest* machines — and calls both ghost
> assets normal. Agreement with our rules is **zero percent**.
>
> That is not a bug. Five of seven assets are under-utilized, so the
> statistically rare pattern is *a machine being used properly*. Outlier
> detection finds rarity; you asked us to find misuse. On this fleet those are
> opposites. We tested three framings, all failed, so we shipped the rules and
> kept the model as a visible cross-check."

### 6:30–7:30 — Cloud, live

C runs the Lambda invoke from `DEPLOY.md` §2.5 and **opens the alert email on
screen**.

> "That email came from a Lambda on a daily EventBridge schedule, publishing to
> SNS, with CloudWatch alarming if the sweep itself fails. Terraform provisions
> all of it — one `apply` per region a dealer operates in. GitHub Actions runs
> our 72 tests, `terraform validate`, and a dashboard smoke test on every push."

### 7:30–8:00 — Close

> "Working today: dashboard, check-in guardrail, alerting, anomaly detection,
> demand model, deployed AWS pipeline, CI. Roadmap: real IoT telemetry via IoT
> Core, and forecasting once we have repeat rental cycles — which the seven-row
> sample cannot support. We would rather tell you that than show you a number we
> made up."

---

## Q&A — the questions you will actually get

**"Why is your R² only 0.42?"**
> "Because that is the honest cross-validated number on seven samples. In-sample
> it is 0.94. We report the one that predicts unseen data. It still beats
> guessing the mean by 1.1 days."

**"Why rules instead of ML for anomalies?"**
> "We ran the ML — it inverts on this dataset and flags our healthiest assets.
> We can show you the agreement matrix. With more fleet history the ML becomes
> viable; today the rules are correct and explainable to a yard manager."

**"Is this real-time?"**
> "The pipeline is event-driven and real-time capable — Lambda triggers on
> ingest. We are replaying your dataset because we have no live telemetry feed.
> Swapping the CSV loader for IoT Core changes one module."

**"Is the QR scanning real?"**
> "It is simulated in the UI — button-driven, no hardware. The state machine and
> the validation behind it are real; a scanner would call the same code path."

**"Why not Bedrock / more AI?"**
> "We had seven rows. Adding a language model would have produced confident
> sentences with nothing behind them. We spent the effort on measurement
> instead — which is how we found the leakage and the inversion."

**"What would you do with three more months?"**
> "Live IoT ingest, DynamoDB as the source of truth instead of CSV, per-site
> demand forecasting once repeat cycles exist, and fuel plus GPS which your
> current schema does not carry."

---

## Failure drills — decide these now, not on stage

| If this breaks | Do this |
|---|---|
| Laptop / projector dies | Open the Streamlit Cloud URL on a phone |
| Venue wifi dies | Run locally: `streamlit run app/dashboard.py` — no internet needed |
| AWS invoke fails | Show the screenshotted email + CloudWatch logs from §2.6 |
| Streamlit Cloud is asleep | It cold-starts in ~30s; click the wake button *before* you present |
| A judge asks for something unbuilt | "Not built — it is on the roadmap slide." Never bluff. |

**Golden rule:** if something is simulated, say "simulated" before a judge asks.
Volunteering a limitation reads as confidence. Getting caught reads as padding.
