# Deploy runbook

Follow top to bottom. Every command is copy-pasteable. Timings are realistic,
not optimistic.

**Do the Streamlit Cloud step first.** It is the demo safety net — if the venue
wifi, your laptop, or AWS misbehaves during the panel, a public URL still works
from a phone.

---

## 1. Public demo URL — Streamlit Community Cloud (~15 min, free)

Nothing to install. The repo is already shaped correctly (`requirements.txt` at
root, entry point `app/dashboard.py`).

1. Go to https://share.streamlit.io and sign in **with GitHub**.
2. *Create app* → *Deploy a public app from GitHub*.
3. Fill in:
   - Repository: `gkarthik29/Mavericks_15-Caterpillar-Hackathon`
   - Branch: `main`
   - Main file path: `app/dashboard.py`
4. Deploy. First build takes 3–5 minutes (scikit-learn is the slow part).
5. Copy the resulting URL. **Put it on the last slide and in the chat.**

> If the build fails on a dependency, loosen the pins in `requirements.txt`
> (drop `==x.y.z` to `>=`) and push — Streamlit Cloud redeploys automatically.

---

## 2. AWS deployment (~30–45 min)

### 2.1 Configure credentials

```bash
aws configure
# Access key, secret key, region (use ap-south-1 for India), output: json
aws sts get-caller-identity        # must print your account ID
```

If `aws` is missing: `brew install awscli`.

### 2.2 Apply the stack

```bash
cd infra
terraform init
terraform plan  -var="alert_email=YOUR@EMAIL.COM"
terraform apply -var="alert_email=YOUR@EMAIL.COM"    # type: yes
```

Creates: DynamoDB table, SNS topic + email subscription, Lambda, EventBridge
schedule, CloudWatch log group + error alarm, and a $5 budget guardrail.

**The Lambda needs no layers** — `loader.py` is stdlib-only, so the package is a
few KB and there is no pandas-layer ARN to hunt down.

### 2.3 Confirm the SNS subscription

AWS emails you a confirmation link. **Click it.** Until you do, no alert is
delivered. Check spam.

### 2.4 Seed the table

```bash
cd ..
pip install boto3
python scripts/seed_dynamodb.py \
  --table "$(cd infra && terraform output -raw dynamodb_table)" \
  --region ap-south-1
```

### 2.5 Fire a real alert — this is your demo moment

```bash
aws lambda invoke \
  --function-name "$(cd infra && terraform output -raw lambda_function_name)" \
  --payload '{"today":"2025-06-01"}' --cli-binary-format raw-in-base64-out \
  /tmp/out.json && cat /tmp/out.json
```

An email should arrive within seconds listing 5 overdue and 2 unassigned assets.
**Rehearse this once, then leave the email unopened so you can open it live.**

### 2.6 Grab evidence (in case live fails)

```bash
aws logs tail "$(cd infra && terraform output -raw log_group)" --since 10m
```

Screenshot: the CloudWatch logs, the DynamoDB table with 7 items, and the alert
email. Put them on a backup slide.

---

## 3. Teardown — do this after the panel

```bash
cd infra && terraform destroy -var="alert_email=YOUR@EMAIL.COM"
```

Everything is free-tier-shaped, but destroy anyway so nothing accrues.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `AccessDenied` on apply | IAM user lacks permissions | Attach `PowerUserAccess` + `IAMFullAccess`, or use an admin key |
| No email arrives | Subscription unconfirmed | Click the link in the AWS confirmation email; re-check spam |
| `ResourceNotFoundException` on seed | Wrong table/region | Use `terraform output -raw dynamodb_table` verbatim |
| Lambda `ImportModuleError` | Stale zip | `terraform apply` again; `archive_file` rehashes on source change |
| Budget resource errors | Budgets are us-east-1 scoped in some accounts | Comment out `aws_budgets_budget` and re-apply; it is a guardrail, not a feature |
| Streamlit Cloud build fails | Pinned versions unavailable | Loosen `requirements.txt` pins and push |

## What is genuinely deployed vs. simulated — say this accurately

- **Deployed and real:** DynamoDB, Lambda, SNS email, EventBridge schedule,
  CloudWatch logs + alarm, GitHub Actions CI.
- **Simulated:** the QR/RFID scan (button-driven, no hardware), and the
  "real-time" telemetry, which replays the supplied dataset.
- **Not built:** Bedrock, API Gateway, IoT Core. They are on the roadmap slide,
  not claimed as working.
