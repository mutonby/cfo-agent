#!/usr/bin/env python3
"""
Genera informe mensual CFO exhaustivo con comparativas, consejos y control de suscripciones.
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

# Suscripciones conocidas con descripción y si son esenciales
KNOWN_SUBSCRIPTIONS = {
    "OpenAI": {"essential": True, "desc": "API de GPT para productos", "alt": None},
    "Anthropic": {"essential": True, "desc": "Claude Pro/API", "alt": None},
    "Google Cloud": {"essential": True, "desc": "Infraestructura principal", "alt": "Revisar si hay recursos ociosos"},
    "AWS": {"essential": False, "desc": "Servicios secundarios", "alt": "¿Se puede migrar a GCP?"},
    "Contabo": {"essential": True, "desc": "Servidores dedicados", "alt": None},
    "Hetzner": {"essential": True, "desc": "Servidores EU", "alt": None},
    "OpenRouter": {"essential": False, "desc": "Acceso a múltiples LLMs", "alt": "¿Se usa lo suficiente?"},
    "ElevenLabs": {"essential": False, "desc": "Text-to-speech", "alt": "¿Hay alternativas más baratas?"},
    "Mistral": {"essential": False, "desc": "LLM alternativo", "alt": "¿Se puede consolidar con OpenRouter?"},
    "X/Twitter": {"essential": True, "desc": "API para Upload-Post", "alt": None},
    "Chargeflow": {"essential": True, "desc": "Gestión de chargebacks", "alt": None},
    "Trackdesk": {"essential": True, "desc": "Programa de afiliados", "alt": None},
    "Stripe": {"essential": True, "desc": "Procesador de pagos", "alt": None},
    "Senja": {"essential": False, "desc": "Testimonios", "alt": "¿Se usa activamente?"},
    "PostHog": {"essential": False, "desc": "Analytics de producto", "alt": "¿Plausible es suficiente?"},
    "YouTube": {"essential": False, "desc": "YouTube Premium personal", "alt": "Gasto personal, no empresa"},
    "Namecheap": {"essential": True, "desc": "Dominios", "alt": None},
    "Geniuslink": {"essential": False, "desc": "Links de afiliados", "alt": "¿ROI positivo?"},
    "Retell": {"essential": False, "desc": "Voice AI", "alt": "¿Se usa en producción?"},
    "Google Ads": {"essential": True, "desc": "Publicidad", "alt": "Revisar ROAS"},
}

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

def detect_subscriptions(transactions):
    """Detecta suscripciones basándose en pagos recurrentes."""
    by_provider = defaultdict(list)
    
    for tx in transactions:
        provider = tx.get("Proveedor", "Desconocido")
        try:
            month = tx.get("Fecha", "")[:7]
            amount = tx["_amount"]
            by_provider[provider].append({"month": month, "amount": amount, "date": tx.get("Fecha", "")})
        except:
            pass
    
    subscriptions = []
    for provider, payments in by_provider.items():
        months = set(p["month"] for p in payments)
        if len(months) >= 2:
            amounts = [p["amount"] for p in payments]
            avg_amount = sum(amounts) / len(amounts)
            min_amount = min(amounts)
            max_amount = max(amounts)
            last_payment = max(p["date"] for p in payments)
            
            # Info adicional si la conocemos
            info = KNOWN_SUBSCRIPTIONS.get(provider, {"essential": None, "desc": "Desconocido", "alt": "Revisar uso"})
            
            subscriptions.append({
                "provider": provider,
                "monthly_avg": avg_amount,
                "min": min_amount,
                "max": max_amount,
                "months_active": len(months),
                "last_payment": last_payment,
                "essential": info["essential"],
                "desc": info["desc"],
                "alt": info["alt"]
            })
    
    return sorted(subscriptions, key=lambda x: x["monthly_avg"], reverse=True)

def generate_insights(last_by_cat, prev_by_cat, subscriptions, balance, burn_rate):
    """Genera insights y consejos personalizados."""
    insights = []
    
    # 1. Categorías que crecieron mucho
    for cat in last_by_cat:
        last = last_by_cat.get(cat, 0)
        prev = prev_by_cat.get(cat, 0)
        if prev > 0 and last > prev * 1.5 and last > 100:
            insights.append({
                "type": "warning",
                "emoji": "⚠️",
                "text": f"**{cat}** subió {((last/prev)-1)*100:.0f}% (€{prev:.0f} → €{last:.0f}). Revisar si es puntual o tendencia."
            })
    
    # 2. Suscripciones no esenciales
    non_essential = [s for s in subscriptions if s["essential"] == False]
    total_non_essential = sum(s["monthly_avg"] for s in non_essential)
    if total_non_essential > 100:
        insights.append({
            "type": "savings",
            "emoji": "💡",
            "text": f"**€{total_non_essential:.0f}/mes** en suscripciones no esenciales. Revisar si todas se usan."
        })
    
    # 3. Suscripciones con alternativas
    for sub in subscriptions:
        if sub["alt"] and sub["monthly_avg"] > 50:
            insights.append({
                "type": "suggestion",
                "emoji": "🔍",
                "text": f"**{sub['provider']}** (€{sub['monthly_avg']:.0f}/mes): {sub['alt']}"
            })
    
    # 4. Runway
    if burn_rate > 0:
        runway = balance / burn_rate
        if runway < 6:
            insights.append({
                "type": "critical",
                "emoji": "🚨",
                "text": f"**Runway crítico:** Solo {runway:.1f} meses de vida. Reducir gastos o aumentar ingresos urgente."
            })
        elif runway < 12:
            insights.append({
                "type": "warning",
                "emoji": "⚠️",
                "text": f"**Runway ajustado:** {runway:.1f} meses. Vigilar burn rate."
            })
    
    # 5. Costes de IA
    ia_cost = last_by_cat.get("IA Tools", 0)
    total = sum(last_by_cat.values())
    if total > 0 and ia_cost / total > 0.25:
        insights.append({
            "type": "info",
            "emoji": "🤖",
            "text": f"**IA es {(ia_cost/total)*100:.0f}% del gasto.** Normal si es core del negocio, revisar si no."
        })
    
    # 6. Duplicados potenciales
    cloud_providers = [s for s in subscriptions if "cloud" in s["desc"].lower() or s["provider"] in ["AWS", "Google Cloud", "Contabo", "Hetzner"]]
    if len(cloud_providers) > 2:
        total_cloud = sum(s["monthly_avg"] for s in cloud_providers)
        insights.append({
            "type": "suggestion",
            "emoji": "☁️",
            "text": f"**{len(cloud_providers)} proveedores cloud** (€{total_cloud:.0f}/mes). ¿Se puede consolidar?"
        })
    
    return insights

def generate_report(config):
    google_token = get_google_token()
    ponto_token = get_ponto_token(config)
    
    balance = get_account_balance(ponto_token, config["ponto"]["account_id"])
    transactions = get_all_transactions(google_token, config["google"]["spreadsheet_id"])
    
    today = datetime.now()
    last_month_end = today.replace(day=1) - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    prev_month_end = last_month_start - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1)
    
    month_name = last_month_start.strftime("%B %Y")
    prev_month_name = prev_month_start.strftime("%B %Y")
    
    # Filtrar transacciones
    last_month_txs = []
    prev_month_txs = []
    
    for tx in transactions:
        try:
            tx_date = datetime.strptime(tx.get("Fecha", ""), "%Y-%m-%d")
        except:
            continue
        
        if last_month_start.date() <= tx_date.date() <= last_month_end.date():
            last_month_txs.append(tx)
        
        if prev_month_start.date() <= tx_date.date() <= prev_month_end.date():
            prev_month_txs.append(tx)
    
    # Totales
    last_month_total = sum(tx["_amount"] for tx in last_month_txs)
    prev_month_total = sum(tx["_amount"] for tx in prev_month_txs)
    
    # Por categoría
    last_by_cat = defaultdict(float)
    prev_by_cat = defaultdict(float)
    
    for tx in last_month_txs:
        last_by_cat[tx.get("Categoría", "Otros")] += tx["_amount"]
    
    for tx in prev_month_txs:
        prev_by_cat[tx.get("Categoría", "Otros")] += tx["_amount"]
    
    # Por proveedor
    last_by_provider = defaultdict(float)
    prev_by_provider = defaultdict(float)
    
    for tx in last_month_txs:
        last_by_provider[tx.get("Proveedor", "Otros")] += tx["_amount"]
    
    for tx in prev_month_txs:
        prev_by_provider[tx.get("Proveedor", "Otros")] += tx["_amount"]
    
    # Top 10 gastos
    top_10 = sorted(last_month_txs, key=lambda x: x["_amount"], reverse=True)[:10]
    
    # Suscripciones
    subscriptions = detect_subscriptions(transactions)
    total_subs = sum(s["monthly_avg"] for s in subscriptions)
    essential_subs = sum(s["monthly_avg"] for s in subscriptions if s["essential"] == True)
    non_essential_subs = sum(s["monthly_avg"] for s in subscriptions if s["essential"] == False)
    
    # Variaciones
    total_change = ((last_month_total / prev_month_total) - 1) * 100 if prev_month_total else 0
    total_change_emoji = "🔴" if total_change > 20 else ("🟢" if total_change < -10 else "🟡")
    
    burn_rate = last_month_total
    runway = balance / burn_rate if burn_rate > 0 else float('inf')
    
    # Generar insights
    insights = generate_insights(last_by_cat, prev_by_cat, subscriptions, balance, burn_rate)
    
    report = f"""📊 **INFORME MENSUAL CFO — {month_name.upper()}**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## 💰 RESUMEN EJECUTIVO

| Métrica | {month_name} | {prev_month_name} | Δ |
|---------|--------------|-------------------|---|
| **Gasto total** | €{last_month_total:,.2f} | €{prev_month_total:,.2f} | {total_change_emoji} {'+' if total_change > 0 else ''}{total_change:.1f}% |
| **Nº transacciones** | {len(last_month_txs)} | {len(prev_month_txs)} | {len(last_month_txs) - len(prev_month_txs):+d} |

💵 **Balance actual:** €{balance:,.2f}
🛤️ **Runway:** {runway:.1f} meses
🔥 **Burn rate:** €{burn_rate:,.2f}/mes

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## 🏷️ COMPARATIVA POR CATEGORÍAS

| Categoría | {month_name[:3]} | {prev_month_name[:3]} | Δ |
|-----------|------------------|----------------------|---|
"""
    
    # Ordenar categorías
    all_cats = set(last_by_cat.keys()) | set(prev_by_cat.keys())
    cat_data = []
    for cat in all_cats:
        last = last_by_cat.get(cat, 0)
        prev = prev_by_cat.get(cat, 0)
        change = ((last / prev) - 1) * 100 if prev else (100 if last else 0)
        cat_data.append((cat, last, prev, change))
    
    cat_data.sort(key=lambda x: x[1], reverse=True)
    
    for cat, last, prev, change in cat_data[:12]:
        if last > 0 or prev > 0:
            emoji = "🔴" if change > 30 else ("🟢" if change < -30 else "🟡")
            report += f"| {cat[:25]} | €{last:,.0f} | €{prev:,.0f} | {emoji} {'+' if change > 0 else ''}{change:.0f}% |\n"
    
    report += f"""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## 🔄 COMPARATIVA POR PROVEEDOR (Top 15)

| Proveedor | {month_name[:3]} | {prev_month_name[:3]} | Δ |
|-----------|------------------|----------------------|---|
"""
    
    # Top proveedores
    all_providers = set(last_by_provider.keys()) | set(prev_by_provider.keys())
    provider_data = []
    for prov in all_providers:
        last = last_by_provider.get(prov, 0)
        prev = prev_by_provider.get(prov, 0)
        change = ((last / prev) - 1) * 100 if prev else (100 if last else 0)
        provider_data.append((prov, last, prev, change))
    
    provider_data.sort(key=lambda x: x[1], reverse=True)
    
    for prov, last, prev, change in provider_data[:15]:
        if last > 10 or prev > 10:
            emoji = "🔴" if change > 50 else ("🟢" if change < -30 else "")
            report += f"| {prov[:20]} | €{last:,.0f} | €{prev:,.0f} | {emoji}{'+' if change > 0 else ''}{change:.0f}% |\n"
    
    report += f"""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## 💳 CONTROL DE SUSCRIPCIONES

**Resumen:**
• Total suscripciones: ~€{total_subs:,.0f}/mes
• Esenciales: ~€{essential_subs:,.0f}/mes
• No esenciales: ~€{non_essential_subs:,.0f}/mes ← **Potencial ahorro**

| Servicio | €/mes | Esencial | Descripción |
|----------|-------|----------|-------------|
"""
    
    for sub in subscriptions[:20]:
        essential_emoji = "✅" if sub["essential"] == True else ("❓" if sub["essential"] is None else "⚠️")
        report += f"| {sub['provider'][:18]} | €{sub['monthly_avg']:,.0f} | {essential_emoji} | {sub['desc'][:25]} |\n"
    
    report += f"""

### ⚠️ Suscripciones a revisar:
"""
    
    for sub in subscriptions:
        if sub["essential"] == False and sub["monthly_avg"] > 20:
            report += f"• **{sub['provider']}** (€{sub['monthly_avg']:.0f}/mes): {sub['alt'] or 'Revisar necesidad'}\n"
    
    report += f"""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## 🔍 TOP 10 GASTOS DEL MES

"""
    
    for i, tx in enumerate(top_10, 1):
        report += f"{i}. **{tx.get('Proveedor', 'N/A')}** — €{tx['_amount']:,.2f}\n"
        report += f"   _{tx.get('Concepto', '')[:50]}_ ({tx.get('Fecha', '')})\n\n"
    
    # KPIs
    ia_cost = last_by_cat.get("IA Tools", 0)
    infra_cost = last_by_cat.get("Infraestructura: Cloud", 0) + last_by_cat.get("Infraestructura: Dominios", 0)
    marketing_cost = last_by_cat.get("Marketing", 0) + last_by_cat.get("Marketing: Afiliados", 0)
    
    ia_pct = (ia_cost / last_month_total * 100) if last_month_total else 0
    infra_pct = (infra_cost / last_month_total * 100) if last_month_total else 0
    marketing_pct = (marketing_cost / last_month_total * 100) if last_month_total else 0
    
    report += f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## 📈 KPIs CLAVE

| KPI | Valor | vs Mes Ant |
|-----|-------|------------|
| 🔥 Burn rate | €{burn_rate:,.0f}/mes | {'+' if total_change > 0 else ''}{total_change:.0f}% |
| 🛤️ Runway | {runway:.1f} meses | - |
| 🤖 Coste IA | €{ia_cost:,.0f} ({ia_pct:.0f}%) | - |
| ☁️ Coste Infra | €{infra_cost:,.0f} ({infra_pct:.0f}%) | - |
| 📢 Marketing | €{marketing_cost:,.0f} ({marketing_pct:.0f}%) | - |
| 💳 Suscripciones | €{total_subs:,.0f}/mes | - |

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## 💡 INSIGHTS Y CONSEJOS

"""
    
    for insight in insights:
        report += f"{insight['emoji']} {insight['text']}\n\n"
    
    # Consejos generales
    report += """### 🎯 Acciones recomendadas:

"""
    
    if non_essential_subs > 100:
        report += f"1. **Revisar suscripciones no esenciales** — Potencial ahorro de €{non_essential_subs:.0f}/mes\n"
    
    if total_change > 20:
        report += f"2. **Analizar aumento de gasto** — Subió {total_change:.0f}% vs mes anterior\n"
    
    pending = len([tx for tx in last_month_txs if tx.get("Estado") == "Pendiente factura"])
    if pending > 5:
        report += f"3. **Subir {pending} facturas pendientes** — Importante para contabilidad\n"
    
    if runway < 18:
        report += f"4. **Monitorizar runway** — {runway:.1f} meses requiere atención\n"
    
    report += """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_Informe generado automáticamente por Secretaria_
_Skill: ponto-invoices | Datos: MyPonto API + Google Sheets_
"""
    
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
