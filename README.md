# 🏦 CFO Agent

> Your AI CFO — automated bank transaction tracking, expense categorization, invoice matching, anomaly detection, and weekly/monthly financial reports.

A [Clawdbot](https://clawd.bot) skill that connects to your bank via [Ponto](https://myponto.com) and manages your finances automatically.

## ✨ Features

- **📥 Auto-sync** — Bank transactions sync to Google Sheets every hour
- **🧾 Invoice matching** — Send a PDF/image, auto-matched to the expense
- **🚨 Anomaly detection** — Alerts for unusual payments, new vendors, high amounts
- **📊 Weekly reports** — Spending trends, projections, top expenses
- **📈 Monthly reports** — Full CFO analysis with subscription control & recommendations
- **🏷️ Auto-categorization** — AI tools, cloud, marketing, SaaS, etc.

## 🚀 Quick Start

1. **Install** — Copy to your Clawdbot skills folder
2. **Configure** — Copy `config.example.json` → `config.json` and add your credentials
3. **Connect Google** — Set up OAuth in `~/.claude/.google/`
4. **Add to heartbeat** — Check for new transactions hourly

See [SKILL.md](SKILL.md) for full documentation.

## 📋 Requirements

- [Ponto](https://myponto.com) account with API access (EU banks)
- Google Cloud project with Drive & Sheets APIs
- Python 3.8+

## 🔒 Security

⚠️ **Never commit credentials!**

- `config.json` — Your API keys (use `config.example.json` as template)
- `state.json` — Transaction state
- Google tokens

All sensitive files are in `.gitignore`.

## 📁 Structure

```
cfo-agent/
├── SKILL.md              # Full documentation
├── config.example.json   # Config template
├── .gitignore           # Protects secrets
└── scripts/
    ├── check_new_transactions.py  # Hourly check
    ├── sync_transactions.py       # Bulk sync
    ├── detect_anomalies.py        # Anomaly detection
    ├── weekly_report.py           # Monday reports
    └── monthly_report.py          # Monthly analysis
```

## 📊 Sample Reports

### Weekly (Mondays)
- Account balance & runway
- This week vs last week
- Top 5 expenses
- End-of-month projection

### Monthly (1st)
- Executive summary with YoY comparison
- Category & vendor breakdowns
- Subscription audit (essential vs non-essential)
- KPIs: burn rate, AI costs %, infra %
- Actionable recommendations

## 🤝 Contributing

Issues and PRs welcome!

## 📄 License

MIT
