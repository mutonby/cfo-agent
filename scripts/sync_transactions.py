#!/usr/bin/env python3
"""
Sincroniza transacciones de Ponto a Google Sheets.
"""
import json
import os
import sys
import requests
from datetime import datetime

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(SKILL_DIR, "config.json")
GOOGLE_TOKEN_PATH = os.path.expanduser("~/.claude/.google/token.json")
GOOGLE_CLIENT_PATH = os.path.expanduser("~/.claude/.google/client_secret.json")

def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=2)

def get_ponto_token(config):
    """Obtiene access token de Ponto."""
    resp = requests.post(
        "https://api.myponto.com/oauth2/token",
        auth=(config["ponto"]["client_id"], config["ponto"]["client_secret"]),
        data={"grant_type": "client_credentials"}
    )
    resp.raise_for_status()
    return resp.json()["access_token"]

def get_google_token():
    """Obtiene y refresca el token de Google si es necesario."""
    with open(GOOGLE_TOKEN_PATH) as f:
        token_data = json.load(f)
    
    # Por ahora devolvemos el access_token directamente
    # TODO: implementar refresh si expira
    return token_data["access_token"]

def get_transactions(ponto_token, account_id, after=None, limit=50):
    """Obtiene transacciones de Ponto."""
    url = f"https://api.myponto.com/accounts/{account_id}/transactions"
    params = {"limit": limit}
    if after:
        params["page[after]"] = after
    
    resp = requests.get(
        url,
        headers={"Authorization": f"Bearer {ponto_token}"},
        params=params
    )
    resp.raise_for_status()
    return resp.json()

def get_sheet_transaction_ids(google_token, spreadsheet_id):
    """Obtiene los Ponto IDs ya en el sheet (columna K)."""
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/Gastos!K:K"
    resp = requests.get(
        url,
        headers={"Authorization": f"Bearer {google_token}"}
    )
    if resp.status_code == 200:
        data = resp.json()
        values = data.get("values", [])
        return set(v[0] for v in values[1:] if v)  # Skip header
    return set()

def append_transactions(google_token, spreadsheet_id, transactions):
    """Añade transacciones al sheet."""
    if not transactions:
        return 0
    
    rows = []
    for tx in transactions:
        attr = tx["attributes"]
        amount = attr["amount"]
        
        # Extraer proveedor del remittanceInformation
        remittance = attr.get("remittanceInformation", "") or ""
        proveedor = extract_provider(remittance)
        categoria = categorize(remittance, proveedor)
        
        # Solo gastos (amount negativo)
        if amount >= 0:
            continue
        
        row = [
            attr.get("executionDate", "")[:10],  # Fecha
            extract_concept(remittance),          # Concepto
            categoria,                            # Categoría
            abs(amount),                          # Importe €
            "",                                   # Importe Original
            attr.get("currency", "EUR"),          # Moneda
            proveedor,                            # Proveedor
            "",                                   # Factura
            "Pendiente factura",                  # Estado
            "",                                   # Notas
            tx["id"]                              # Ponto ID
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
    resp.raise_for_status()
    return len(rows)

def extract_provider(remittance):
    """Extrae el proveedor del texto de remittance."""
    remittance = remittance.upper()
    
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
    }
    
    for key, value in providers.items():
        if key in remittance:
            return value
    
    # Extraer primer palabra después de COMPRA
    if "COMPRA " in remittance:
        parts = remittance.split("COMPRA ")[1].split(",")[0].split()[0]
        return parts.title()
    
    return "Desconocido"

def extract_concept(remittance):
    """Extrae un concepto limpio del remittance."""
    if not remittance:
        return "Sin concepto"
    
    # Limpiar y acortar
    concept = remittance.replace("COMPRA ", "").split(",")[0]
    if len(concept) > 50:
        concept = concept[:47] + "..."
    return concept

def categorize(remittance, provider):
    """Categoriza el gasto."""
    remittance = remittance.upper()
    provider = provider.upper()
    
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
    if any(x in remittance or x in provider for x in ["STRIPE", "CHARGEFLOW", "TRACKDESK", "SENJA", "POSTHOG", "X DEVELOPER", "TWITTER"]):
        return "SaaS Business"
    
    return "Otros"

def main():
    config = load_config()
    
    print("🔄 Sincronizando transacciones de Ponto...")
    
    # Obtener tokens
    ponto_token = get_ponto_token(config)
    google_token = get_google_token()
    
    # Obtener IDs ya en el sheet
    existing_ids = get_sheet_transaction_ids(google_token, config["google"]["spreadsheet_id"])
    print(f"📊 Transacciones existentes en sheet: {len(existing_ids)}")
    
    # Obtener transacciones de Ponto
    tx_data = get_transactions(ponto_token, config["ponto"]["account_id"], limit=50)
    transactions = tx_data.get("data", [])
    print(f"🏦 Transacciones obtenidas de Ponto: {len(transactions)}")
    
    # Filtrar nuevas
    new_transactions = [tx for tx in transactions if tx["id"] not in existing_ids]
    print(f"🆕 Transacciones nuevas: {len(new_transactions)}")
    
    if new_transactions:
        # Añadir al sheet
        added = append_transactions(google_token, config["google"]["spreadsheet_id"], new_transactions)
        print(f"✅ Añadidas {added} transacciones al sheet")
    else:
        print("✅ No hay transacciones nuevas")
    
    return len(new_transactions)

if __name__ == "__main__":
    try:
        count = main()
        sys.exit(0 if count >= 0 else 1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
