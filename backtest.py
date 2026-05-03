"""
BACKTESTING — 30 DERNIERS JOURS
Strategie Martingale · ETH & SOL · Levier x3
Utilise l'API publique Binance Spot (pas de cle API necessaire)
"""

import requests
import json
from datetime import datetime

MISE_DEPART = 5.0
LEVIER      = 3
# API publique Binance Spot - pas besoin de cle API
BASE_URL    = "https://api.binance.com"

def get_donnees(symbole, jours=30):
    try:
        r = requests.get(f"{BASE_URL}/api/v3/klines",
                         params={"symbol": symbole, "interval": "1d", "limit": jours}, timeout=10)
        data = r.json()
        if not isinstance(data, list):
            print(f"Erreur API {symbole} : {data}")
            return []
        journees = []
        for k in data:
            open_p  = float(k[1])
            close_p = float(k[4])
            variation = round((close_p - open_p) / open_p * 100, 2)
            journees.append({
                "date": datetime.fromtimestamp(int(k[0])/1000).strftime("%Y-%m-%d"),
                "open": open_p, "close": close_p, "variation": variation
            })
        return journees
    except Exception as e:
        print(f"Erreur {symbole} : {e}")
        return []

def get_closes(symbole, limite=100):
    try:
        r = requests.get(f"{BASE_URL}/api/v3/klines",
                         params={"symbol": symbole, "interval": "1h", "limit": limite}, timeout=10)
        data = r.json()
        if not isinstance(data, list):
            return []
        return [float(k[4]) for k in data]
    except Exception as e:
        print(f"Erreur closes {symbole} : {e}")
        return []

def rsi(closes, p=14):
    if len(closes) < p+1:
        return 50
    g = [max(0.0, closes[i]-closes[i-1]) for i in range(1,len(closes))]
    l = [max(0.0, closes[i-1]-closes[i]) for i in range(1,len(closes))]
    mg, ml = sum(g[-p:])/p, sum(l[-p:])/p
    return round(100-(100/(1+mg/ml)),2) if ml > 0 else 100

def lancer_backtesting():
    print("\n" + "="*60)
    print("BACKTESTING — 30 DERNIERS JOURS")
    print("Strategie : Martingale Journaliere · Levier x3")
    print("="*60)

    print("Recuperation des donnees...")
    eth = get_donnees("ETHUSDT", 30)
    sol = get_donnees("SOLUSDT", 30)
    c_eth = get_closes("ETHUSDT", 200)
    c_sol = get_closes("SOLUSDT", 200)

    if not eth or not sol:
        print("ERREUR : Donnees non disponibles")
        return

    print(f"{len(eth)} jours de donnees ETH recuperes")
    print(f"{len(sol)} jours de donnees SOL recuperes\n")

    mise = MISE_DEPART
    cumul = 0.0
    gagnes, perdus = 0, 0

    print(f"{'Date':<12} {'Marche':<6} {'Dir':<7} {'Mise':>6} {'Res':<12} {'Gain':>8} {'Cumul':>8}")
    print("-"*65)

    for i, (je, js) in enumerate(zip(eth, sol)):
        re = rsi(c_eth[-100:]) if c_eth else 50
        rs = rsi(c_sol[-100:]) if c_sol else 50

        se = 8 if re < 30 or re > 70 else 3
        ss = 8 if rs < 30 or rs > 70 else 3
        de = "ACHAT" if re < 50 else "VENTE"
        ds = "ACHAT" if rs < 50 else "VENTE"

        if se >= ss:
            marche, direction, var = "ETH", de, je["variation"]
        else:
            marche, direction, var = "SOL", ds, js["variation"]

        if direction == "ACHAT":
            resultat = "GAGNE" if var > 0 else "PERDU"
        else:
            resultat = "GAGNE" if var < 0 else "PERDU"

        if resultat == "GAGNE":
            gain = mise * 2
            cumul += gain
            gagnes += 1
            prochaine = MISE_DEPART
            icone = "OUI"
        else:
            gain = -mise
            cumul += gain
            perdus += 1
            prochaine = mise * 2
            icone = "NON"

        signe_gain = "+" if gain >= 0 else ""
        signe_cumul = "+" if cumul >= 0 else ""
        print(f"{je['date']:<12} {marche:<6} {direction:<7} {mise:>6.1f} {icone+' '+resultat:<12} {signe_gain}{gain:>7.2f} {signe_cumul}{cumul:>7.2f}")
        mise = prochaine

    print("\n" + "="*60)
    print("RAPPORT FINAL")
    print("="*60)
    print(f"Trades gagnes  : {gagnes}")
    print(f"Trades perdus  : {perdus}")
    taux = round(gagnes/max(gagnes+perdus,1)*100,1)
    print(f"Taux reussite  : {taux}%")
    signe = "+" if cumul >= 0 else ""
    print(f"Benefice net   : {signe}{round(cumul,2)} USDT")
    print(f"Mise finale    : {mise} USDT")
    print("="*60)
    if cumul > 0:
        print(f"RESULTAT POSITIF : {signe}{round(cumul,2)} USDT sur 30 jours !")
    else:
        print(f"RESULTAT NEGATIF : {round(cumul,2)} USDT sur 30 jours")

if __name__ == "__main__":
    lancer_backtesting()
