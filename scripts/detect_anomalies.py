#!/usr/bin/env python3
"""
Detecta anomalías en las transacciones: pagos altos, proveedores nuevos, duplicados.
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

HIGH_PAYMENT_THRESHOLD = 500  # EUR

def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)

def get_google_token():
    with open(GOOGLE_TOKEN_PATH) as f:
        return json.load(f)["access_token"]

def get_all_transactions(google_token, spreadsheet_id):
    """Obtiene todas las transacciones del sheet."""
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
        transactions.append(tx)
    
    return transactions

def analyze_transactions(transactions):
    """Analiza transacciones y detecta anomalías."""
    alerts = []
    
    if not transactions:
        return alerts
    
    # Agrupar por proveedor
    by_provider = defaultdict(list)
    for tx in transactions:
        provider = tx.get("Proveedor", "Desconocido")
        by_provider[provider].append(tx)
    
    # Detectar transacciones de hoy/ayer
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    recent_txs = [tx for tx in transactions if tx.get("Fecha", "") in [today, yesterday]]
    
    for tx in recent_txs:
        provider = tx.get("Proveedor", "Desconocido")
        try:
            amount = float(tx.get("Importe €", "0").replace(",", "."))
        except:
            amount = 0
        
        # 1. Pago alto de proveedor nuevo
        provider_history = by_provider.get(provider, [])
        if amount > HIGH_PAYMENT_THRESHOLD and len(provider_history) == 1:
            alerts.append({
                "type": "high_new_provider",
                "severity": "high",
                "message": f"⚠️ Pago alto de proveedor NUEVO: {provider} - €{amount:.2f}",
                "tx": tx
            })
        
        # 2. Pago inusualmente alto para este proveedor
        elif len(provider_history) > 1:
            other_amounts = []
            for ptx in provider_history:
                if ptx.get("Ponto ID") != tx.get("Ponto ID"):
                    try:
                        other_amounts.append(float(ptx.get("Importe €", "0").replace(",", ".")))
                    except:
                        pass
            
            if other_amounts:
                avg = sum(other_amounts) / len(other_amounts)
                if amount > avg * 2 and amount > 100:
                    alerts.append({
                        "type": "unusual_high",
                        "severity": "medium",
                        "message": f"📊 Pago inusual de {provider}: €{amount:.2f} (media histórica: €{avg:.2f})",
                        "tx": tx
                    })
        
        # 3. Proveedor completamente nuevo (primera vez)
        if len(provider_history) == 1 and amount <= HIGH_PAYMENT_THRESHOLD:
            alerts.append({
                "type": "new_provider",
                "severity": "low",
                "message": f"🆕 Proveedor nuevo detectado: {provider} - €{amount:.2f}",
                "tx": tx
            })
    
    # 4. Duplicados (mismo proveedor, mismo importe, mismo día)
    by_date = defaultdict(list)
    for tx in recent_txs:
        key = (tx.get("Fecha"), tx.get("Proveedor"), tx.get("Importe €"))
        by_date[key].append(tx)
    
    for key, txs in by_date.items():
        if len(txs) > 1:
            alerts.append({
                "type": "duplicate",
                "severity": "medium",
                "message": f"🔄 Posible duplicado: {key[1]} - €{key[2]} ({len(txs)} veces el {key[0]})",
                "tx": txs[0]
            })
    
    return alerts

def main():
    config = load_config()
    
    try:
        google_token = get_google_token()
    except Exception as e:
        print(f"❌ Error obteniendo token de Google: {e}")
        return []
    
    transactions = get_all_transactions(google_token, config["google"]["spreadsheet_id"])
    alerts = analyze_transactions(transactions)
    
    if alerts:
        print(f"🚨 {len(alerts)} alertas detectadas:")
        for alert in alerts:
            print(f"  {alert['message']}")
    else:
        print("✅ Sin anomalías detectadas")
    
    return alerts

if __name__ == "__main__":
    alerts = main()
    # Devuelve las alertas como JSON para que el heartbeat las use
    print(json.dumps(alerts, ensure_ascii=False, indent=2))
