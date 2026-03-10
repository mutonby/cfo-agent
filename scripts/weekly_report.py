#!/usr/bin/env python3
"""
Genera informe semanal CFO para el CEO.
"""
import json
import os
import sys
import requests
from datetime import datetime, timedelta
from collections import defaultdict

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(SKILL_DIR, "config.json")
GOOGLE_TOKEN_PATH = os.path.expanduser("~/.claude/.google/token.json")

def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)

def get_ponto_token(config):
    resp = requests.post(
        "https://api.myponto.com/oauth2/token",
        auth=(config["ponto"]["client_id"], config["ponto"]["client_secret"]),
        data={"grant_type": "client_credentials"}
    )
    resp.raise_for_status()
    return resp.json()["access_token"]

def get_account_balance(ponto_token, account_id):
    resp = requests.get(
        f"https://api.myponto.com/accounts/{account_id}",
        headers={"Authorization": f"Bearer {ponto_token}"}
    )
    resp.raise_for_status()
    data = resp.json()["data"]
    return data["attributes"]["currentBalance"]

def get_google_token():
    with open(GOOGLE_TOKEN_PATH) as f:
        return json.load(f)["access_token"]

def get_all_transactions(google_token, spreadsheet_id):
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/Gastos!A:K"
    resp = requests.get(url, headers={"Authorization": f"Bearer {google_token}"})
    if resp.status_code != 200:
        return []
    
    data = resp.json()
    rows = data.get("values", [])
    if len(rows) < 2:
        return []
    
    headers = rows[0]
    transactions = []
    for row in rows[1:]:
        tx = {}
        for i, h in enumerate(headers):
            tx[h] = row[i] if i < len(row) else ""
        try:
            tx["_amount"] = float(tx.get("Importe €", "0").replace(",", "."))
        except:
            tx["_amount"] = 0
        transactions.append(tx)
    
    return transactions

def generate_report(config):
    google_token = get_google_token()
    ponto_token = get_ponto_token(config)
    
    # Obtener balance actual
    balance = get_account_balance(ponto_token, config["ponto"]["account_id"])
    
    # Obtener transacciones
    transactions = get_all_transactions(google_token, config["google"]["spreadsheet_id"])
    
    today = datetime.now()
    
    # Calcular fechas
    week_start = today - timedelta(days=today.weekday() + 7)  # Lunes pasado
    week_end = week_start + timedelta(days=6)  # Domingo pasado
    month_start = today.replace(day=1)
    last_month_same_day = (month_start - timedelta(days=1)).replace(day=min(today.day, 28))
    last_month_start = last_month_same_day.replace(day=1)
    
    # Filtrar transacciones
    this_week = []
    last_week = []
    this_month = []
    last_month_to_same_day = []
    
    for tx in transactions:
        try:
            tx_date = datetime.strptime(tx.get("Fecha", ""), "%Y-%m-%d")
        except:
            continue
        
        if week_start.date() <= tx_date.date() <= week_end.date():
            this_week.append(tx)
        
        prev_week_start = week_start - timedelta(days=7)
        prev_week_end = prev_week_start + timedelta(days=6)
        if prev_week_start.date() <= tx_date.date() <= prev_week_end.date():
            last_week.append(tx)
        
        if tx_date.date() >= month_start.date():
            this_month.append(tx)
        
        if last_month_start.date() <= tx_date.date() <= last_month_same_day.date():
            last_month_to_same_day.append(tx)
    
    # Calcular totales
    week_total = sum(tx["_amount"] for tx in this_week)
    last_week_total = sum(tx["_amount"] for tx in last_week)
    month_total = sum(tx["_amount"] for tx in this_month)
    last_month_total = sum(tx["_amount"] for tx in last_month_to_same_day)
    
    # Top 5 gastos de la semana
    top_5 = sorted(this_week, key=lambda x: x["_amount"], reverse=True)[:5]
    
    # Por categoría
    by_category = defaultdict(float)
    for tx in this_week:
        by_category[tx.get("Categoría", "Otros")] += tx["_amount"]
    
    # Generar report
    report = f"""📊 **INFORME SEMANAL CFO — {week_start.strftime('%d %b')} al {week_end.strftime('%d %b %Y')}**

💰 **Balance actual:** €{balance:,.2f}

---

📈 **RESUMEN SEMANAL**

| Métrica | Esta semana | Semana anterior | Δ |
|---------|-------------|-----------------|---|
| Gastos | €{week_total:,.2f} | €{last_week_total:,.2f} | {'+' if week_total > last_week_total else ''}{((week_total/last_week_total - 1) * 100) if last_week_total else 0:+.0f}% |

---

📅 **RITMO DEL MES** (día {today.day})

| Métrica | Este mes | Mismo día mes ant. | Δ |
|---------|----------|-------------------|---|
| Gastos | €{month_total:,.2f} | €{last_month_total:,.2f} | {'+' if month_total > last_month_total else ''}{((month_total/last_month_total - 1) * 100) if last_month_total else 0:+.0f}% |

{"⚠️ **ALERTA:** Vamos por ENCIMA del ritmo del mes anterior" if month_total > last_month_total * 1.2 else "✅ Ritmo de gasto controlado"}

---

🏆 **TOP 5 GASTOS DE LA SEMANA**
"""
    
    for i, tx in enumerate(top_5, 1):
        report += f"\n{i}. **{tx.get('Proveedor', 'N/A')}** — €{tx['_amount']:,.2f} ({tx.get('Categoría', 'N/A')})"
    
    report += "\n\n---\n\n🏷️ **POR CATEGORÍA**\n"
    
    for cat, total in sorted(by_category.items(), key=lambda x: x[1], reverse=True)[:5]:
        report += f"\n• {cat}: €{total:,.2f}"
    
    # Proyección
    days_in_month = (month_start.replace(month=month_start.month % 12 + 1, day=1) - timedelta(days=1)).day
    daily_avg = month_total / today.day if today.day > 0 else 0
    projected = daily_avg * days_in_month
    
    report += f"""

---

📉 **PROYECCIÓN FIN DE MES**

• Gasto diario promedio: €{daily_avg:,.2f}
• Proyección cierre: €{projected:,.2f}
• Días restantes: {days_in_month - today.day}

---

💡 **OBSERVACIONES**

"""
    
    # Observaciones automáticas
    if week_total > last_week_total * 1.3:
        report += "• 🔴 Semana con gasto elevado (+30% vs anterior)\n"
    elif week_total < last_week_total * 0.7:
        report += "• 🟢 Semana con gasto bajo (-30% vs anterior)\n"
    else:
        report += "• 🟡 Gasto semanal estable\n"
    
    if month_total > last_month_total * 1.2:
        report += "• ⚠️ Ritmo de gasto mensual por encima del mes anterior\n"
    
    # Facturas pendientes
    pending = len([tx for tx in transactions if tx.get("Estado") == "Pendiente factura"])
    if pending > 10:
        report += f"• 📄 {pending} facturas pendientes de subir\n"
    
    return report

def main():
    config = load_config()
    
    try:
        report = generate_report(config)
        print(report)
        return report
    except Exception as e:
        print(f"❌ Error generando informe: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    main()
