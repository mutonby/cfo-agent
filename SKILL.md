---
name: cfo-agent
description: Your AI CFO — automated bank transaction tracking, expense categorization, invoice matching, anomaly detection, and weekly/monthly financial reports. Use when managing business expenses, tracking burn rate, matching invoices to payments, detecting unusual charges, analyzing spending trends, controlling subscriptions, or generating CFO-style reports for startups and small businesses.
---

# CFO Agent

Automated bank transaction tracking with Google Sheets sync, invoice matching, anomaly detection, and CFO-style financial reporting.

## Quick Start

1. Copy skill to your Clawdbot skills directory
2. Copy `config.example.json` to `config.json` and fill in credentials
3. Set up Google OAuth credentials in `~/.claude/.google/`
4. Add hourly check to your HEARTBEAT.md

## Configuration

### config.json

```json
{
  "ponto": {
    "client_id": "your-ponto-client-id",
    "client_secret": "your-ponto-client-secret",
    "account_id": "your-ponto-account-id"
  },
  "google": {
    "spreadsheet_id": "your-google-sheet-id",
    "folder_id": "your-drive-folder-id"
  }
}
```

### Google OAuth

Place in `~/.claude/.google/`:
- `client_secret.json` - OAuth client credentials from Google Cloud Console
- `token.json` - Auto-generated after first authorization

## Scripts

| Script | Purpose |
|--------|---------|
| `check_new_transactions.py` | Hourly check - syncs new transactions, detects anomalies, requests invoices |
| `sync_transactions.py` | Bulk sync of all recent transactions |
| `weekly_report.py` | Weekly CFO summary (balance, spending trends, projections) |
| `monthly_report.py` | Comprehensive monthly report with subscription analysis |

## Heartbeat Integration

Add to HEARTBEAT.md for hourly transaction checks:

```markdown
## Ponto Check (~hourly)

If >1 hour since last check:
python3 /path/to/ponto-invoices/scripts/check_new_transactions.py

If new transactions: notify user with list and request invoices.
If alerts (high severity): notify immediately.
```

## Features

### Transaction Sync
- Connects to Ponto banking API hourly
- Auto-categorizes expenses (AI Tools, Cloud, Marketing, etc.)
- Adds to Google Sheets with vendor extraction

### Anomaly Detection
- 🚨 New vendor with payment >€500
- 📊 Payment >2x historical average for vendor
- 💰 Any payment >€1000
- 🆕 First-time vendor

### Invoice Matching
When user sends PDF/image:
1. Extract vendor, date, amount via vision
2. Match to expense in Sheet (±5% tolerance)
3. Upload to Drive with descriptive name
4. Update Sheet status to "✅ Invoiced"

### Weekly Report (Mondays)
- Account balance
- Week vs previous week spending
- Month-to-date vs same day last month
- Top 5 expenses, category breakdown
- End-of-month projection

### Monthly Report (1st of month)
- Executive summary with comparisons
- Category and vendor breakdowns
- Subscription control (essential vs non-essential)
- KPIs: burn rate, runway, AI/infra costs %
- Automated insights and recommendations

## Sheet Structure

| Column | Field |
|--------|-------|
| A | Date |
| B | Concept |
| C | Category |
| D | Amount € |
| E | Original Amount |
| F | Currency |
| G | Vendor |
| H | Invoice (link) |
| I | Status |
| J | Notes |
| K | Ponto ID |

## Auto-Categories

| Category | Vendors |
|----------|---------|
| AI Tools | OpenAI, Anthropic, Mistral, OpenRouter, ElevenLabs |
| Infrastructure: Cloud | Google Cloud, AWS, Contabo, Hetzner |
| Infrastructure: Domains | Namecheap, Geniuslink, GoDaddy |
| Marketing | Google Ads, Facebook Ads |
| SaaS Business | Stripe, Chargeflow, various APIs |

## Cron Jobs (optional)

```
# Weekly report - Mondays 09:00 UTC
0 9 * * 1  python3 /path/to/scripts/weekly_report.py

# Monthly report - 1st of month 10:00 UTC
0 10 1 * *  python3 /path/to/scripts/monthly_report.py
```

## Security

**Never commit:**
- `config.json` (credentials)
- `state.json` (transaction IDs)
- Google tokens

All sensitive files listed in `.gitignore`.

## Requirements

- [Ponto](https://myponto.com) account with API access
- Google Cloud project with Drive & Sheets APIs enabled
- Python 3.8+ with `requests` library
