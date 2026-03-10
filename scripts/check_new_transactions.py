#!/usr/bin/env python3
"""
Comprueba transacciones nuevas, las añade al Sheet, detecta anomalías y pide facturas.
Diseñado para ejecutarse en heartbeat cada ~4 horas.
"""
import json
import os
import sys
import requests
from datetime import datetime, timedelta
from collections import defaultdict

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(SKILL_DIR, "config.json")
STATE_PATH = os.path.join(SKILL_DIR, "state.json")
GOOGLE_TOKEN_PATH = os.path.expanduser("~/.claude/.google/token.json")
GOOGLE_CLIENT_PATH = os.path.expanduser("~/.claude/.google/client_secret.json")

HIGH_PAYMENT_THRESHOLD = 500

def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)

def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {"last_check": None, "known_transaction_ids": []}

def save_state(state):
    with open(STATE_PATH, 'w') as f:
        json.dump(state, f, indent=2)

def refresh_google_token():
    """Refresca el token de Google si es necesario."""
    with open(GOOGLE_CLIENT_PATH) as f:
        client = json.load(f)["installed"]
    
    with open(GOOGLE_TOKEN_PATH) as f:
        token_data = json.load(f)
    
    # Intentar refrescar
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "refresh_token": token_data["refresh_token"],
            "grant_type": "refresh_token"
        }
    )
    
    if resp.status_code == 200:
        new_token = resp.json()
        token_data["access_token"] = new_token["access_token"]
        with open(GOOGLE_TOKEN_PATH, 'w') as f:
            json.dump(token_data, f, indent=2)
        return token_data["access_token"]
    
    return token_data["access_token"]

def get_ponto_token(config):
    resp = requests.post(
        "https://api.myponto.com/oauth2/token",
        auth=(config["ponto"]["client_id"], config["ponto"]["client_secret"]),
        data={"grant_type": "client_credentials"}
    )
    resp.raise_for_status()
    return resp.json()["access_token"]

def get_ponto_transactions(ponto_token, account_id, limit=20):
    """Obtiene las últimas transacciones de Ponto."""
    resp = requests.get(
        f"https://api.myponto.com/accounts/{account_id}/transactions",
        headers={"Authorization": f"Bearer {ponto_token}"},
        params={"limit": limit}
    )
    resp.raise_for_status()
    return resp.json().get("data", [])

def get_sheet_data(google_token, spreadsheet_id):
    """Obtiene todos los datos del sheet para análisis."""
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/Gastos!A:K"
    resp = requests.get(url, headers={"Authorization": f"Bearer {google_token}"})
    
    if resp.status_code == 401:
        # Token expirado, refrescar
        google_token = refresh_google_token()
        resp = requests.get(url, headers={"Authorization": f"Bearer {google_token}"})
    
    if resp.status_code != 200:
        return [], set(), google_token
    
    data = resp.json()
    rows = data.get("values", [])
    
    if len(rows) < 2:
        return [], set(), google_token
    
    headers = rows[0]
    transactions = []
    known_ids = set()
    
    for row in rows[1:]:
        tx = {}
        for i, h in enumerate(headers):
            tx[h] = row[i] if i < len(row) else ""
        try:
            tx["_amount"] = float(tx.get("Importe €", "0").replace(",", "."))
        except:
            tx["_amount"] = 0
        transactions.append(tx)
        if tx.get("Ponto ID"):
            known_ids.add(tx["Ponto ID"])
    
    return transactions, known_ids, google_token

def extract_provider(remittance):
    """Extrae el proveedor del texto."""
    remittance = (remittance or "").upper()
    
    providers = {
        "OPENAI": "OpenAI",
        "GOOGLE CLOUD": "Google Cloud",
        "GOOGLE*CLOUD": "Google Cloud",
        "GOOGLE*ADS": "Google Ads",
        "YOUTUBE": "YouTube",
        "CHARGEFLOW": "Chargeflow",
        "OPENROUTER": "OpenRouter",
        "GENIUSLINK": "Geniuslink",
        "NAMECHEAP": "Namecheap",
        "X DEVELOPER": "X/Twitter",
        "TWITTER": "X/Twitter",
        "AWS": "AWS",
        "CONTABO": "Contabo",
        "HETZNER": "Hetzner",
        "STRIPE": "Stripe",
        "PAYPAL": "PayPal",
        "ANTHROPIC": "Anthropic",
        "CLAUDE": "Anthropic",
        "ELEVENLABS": "ElevenLabs",
        "MISTRAL": "Mistral",
        "TRACKDESK": "Trackdesk",
        "SENJA": "Senja",
        "POSTHOG": "PostHog",
        "RETELL": "Retell",
        "HERRERO": "Herrero & Asociados",
        "AMERICAN AIR": "American Airlines",
        "INVA REGULATORY": "INVA",
    }
    
    for key, value in providers.items():
        if key in remittance:
            return value
    
    if "COMPRA " in remittance:
        parts = remittance.split("COMPRA ")[1].split(",")[0].split()[0]
        return parts.title()[:20]
    
    return "Desconocido"

def categorize(remittance, provider):
    """Categoriza el gasto."""
    remittance = (remittance or "").upper()
    provider = (provider or "").upper()
    
    if any(x in remittance or x in provider for x in ["OPENAI", "ANTHROPIC", "CLAUDE", "MISTRAL", "OPENROUTER", "ELEVENLABS"]):
        return "IA Tools"
    if any(x in remittance or x in provider for x in ["GOOGLE CLOUD", "AWS", "CONTABO", "HETZNER"]):
        return "Infraestructura: Cloud"
    if any(x in remittance or x in provider for x in ["NAMECHEAP", "GENIUSLINK", "DONDOMINIO"]):
        return "Infraestructura: Dominios"
    if any(x in remittance or x in provider for x in ["GOOGLE*ADS", "PAYPAL"]):
        return "Marketing"
    if any(x in remittance or x in provider for x in ["YOUTUBE"]):
        return "Personal/Ocio"
    if any(x in remittance or x in provider for x in ["HERRERO", "INVA"]):
        return "Asesoría/Legal"
    if any(x in remittance or x in provider for x in ["STRIPE", "CHARGEFLOW", "TRACKDESK", "SENJA", "POSTHOG", "X DEVELOPER", "TWITTER"]):
        return "SaaS Business"
    
    return "Otros"

def analyze_transaction(tx, historical_txs):
    """Analiza si una transacción es anómala comparando con histórico."""
    alerts = []
    
    amount = abs(tx["attributes"]["amount"])
    provider = extract_provider(tx["attributes"].get("remittanceInformation", ""))
    
    # Buscar histórico de este proveedor
    provider_history = [t for t in historical_txs if t.get("Proveedor") == provider]
    
    # 1. Proveedor completamente nuevo
    if len(provider_history) == 0:
        if amount > HIGH_PAYMENT_THRESHOLD:
            alerts.append({
                "severity": "high",
                "message": f"🚨 **PROVEEDOR NUEVO con pago ALTO:** {provider} — €{amount:.2f}"
            })
        else:
            alerts.append({
                "severity": "low",
                "message": f"🆕 Proveedor nuevo: {provider} — €{amount:.2f}"
            })
    
    # 2. Pago inusualmente alto para este proveedor
    elif len(provider_history) > 0:
        historical_amounts = [t["_amount"] for t in provider_history if t["_amount"] > 0]
        if historical_amounts:
            avg = sum(historical_amounts) / len(historical_amounts)
            max_hist = max(historical_amounts)
            
            if amount > avg * 2 and amount > 100:
                alerts.append({
                    "severity": "medium",
                    "message": f"📊 Pago inusual de {provider}: €{amount:.2f} (media: €{avg:.2f}, máx anterior: €{max_hist:.2f})"
                })
    
    # 3. Pago muy alto en general
    if amount > 1000 and len([a for a in alerts if a["severity"] == "high"]) == 0:
        alerts.append({
            "severity": "medium",
            "message": f"💰 Pago alto: {provider} — €{amount:.2f}"
        })
    
    return alerts

def append_to_sheet(google_token, spreadsheet_id, transactions):
    """Añade transacciones al sheet."""
    if not transactions:
        return 0
    
    rows = []
    for tx in transactions:
        attr = tx["attributes"]
        amount = attr["amount"]
        
        if amount >= 0:  # Solo gastos
            continue
        
        remittance = attr.get("remittanceInformation", "") or ""
        provider = extract_provider(remittance)
        categoria = categorize(remittance, provider)
        
        # Limpiar concepto
        concept = remittance.replace("COMPRA ", "").split(",")[0][:50]
        
        row = [
            attr.get("executionDate", "")[:10],
            concept,
            categoria,
            abs(amount),
            "",
            attr.get("currency", "EUR"),
            provider,
            "",
            "Pendiente factura",
            "",
            tx["id"]
        ]
        rows.append(row)
    
    if not rows:
        return 0
    
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/Gastos!A:K:append"
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {google_token}",
            "Content-Type": "application/json"
        },
        params={"valueInputOption": "USER_ENTERED"},
        json={"values": rows}
    )
    
    if resp.status_code == 401:
        google_token = refresh_google_token()
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {google_token}",
                "Content-Type": "application/json"
            },
            params={"valueInputOption": "USER_ENTERED"},
            json={"values": rows}
        )
    
    resp.raise_for_status()
    return len(rows)

def main():
    config = load_config()
    state = load_state()
    
    result = {
        "new_transactions": [],
        "alerts": [],
        "added_count": 0,
        "request_invoices": []
    }
    
    try:
        # 1. Obtener token de Ponto
        ponto_token = get_ponto_token(config)
        
        # 2. Obtener token de Google (con refresh si es necesario)
        google_token = refresh_google_token()
        
        # 3. Obtener datos actuales del sheet
        historical_txs, known_ids, google_token = get_sheet_data(
            google_token, 
            config["google"]["spreadsheet_id"]
        )
        
        # 4. Obtener últimas transacciones de Ponto
        ponto_txs = get_ponto_transactions(
            ponto_token, 
            config["ponto"]["account_id"],
            limit=30
        )
        
        # 5. Filtrar nuevas (no están en el sheet)
        new_txs = [tx for tx in ponto_txs if tx["id"] not in known_ids]
        
        # 6. Filtrar solo gastos
        new_expenses = [tx for tx in new_txs if tx["attributes"]["amount"] < 0]
        
        if not new_expenses:
            print(json.dumps({"status": "ok", "message": "Sin transacciones nuevas", "new_count": 0}))
            return result
        
        # 7. Analizar cada transacción nueva
        for tx in new_expenses:
            alerts = analyze_transaction(tx, historical_txs)
            result["alerts"].extend(alerts)
            
            # Preparar info para pedir factura
            attr = tx["attributes"]
            provider = extract_provider(attr.get("remittanceInformation", ""))
            amount = abs(attr["amount"])
            date = attr.get("executionDate", "")[:10]
            
            result["new_transactions"].append({
                "provider": provider,
                "amount": amount,
                "date": date,
                "id": tx["id"]
            })
            
            result["request_invoices"].append(f"• {provider}: €{amount:.2f} ({date})")
        
        # 8. Añadir al sheet
        added = append_to_sheet(google_token, config["google"]["spreadsheet_id"], new_expenses)
        result["added_count"] = added
        
        # 9. Actualizar estado
        state["last_check"] = datetime.now().isoformat()
        state["known_transaction_ids"] = list(known_ids | {tx["id"] for tx in new_expenses})
        save_state(state)
        
        # 10. Generar output
        output = {
            "status": "new_transactions",
            "new_count": len(new_expenses),
            "added_to_sheet": added,
            "alerts": result["alerts"],
            "invoices_needed": result["request_invoices"]
        }
        
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return result
        
    except Exception as e:
        error_output = {
            "status": "error",
            "error": str(e)
        }
        print(json.dumps(error_output, ensure_ascii=False))
        return result

if __name__ == "__main__":
    main()
