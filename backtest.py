"""
BACKTESTING — 30 DERNIERS JOURS
Stratégie Martingale · ETH & SOL · Levier x3
"""

import requests
import json
from datetime import datetime

MISE_DEPART = 5.0
LEVIER      = 3
BASE_URL    = "https://fapi.binance.com"

def get_donnees(symbole, jours=30):
    try:
        r = requests.get(f"{BASE_URL}/fapi/v1/klines",
                         params={"symbol": symbole, "interval": "1d", "limit": jours}, timeout=10)
        data = r.json()
        journees = []
        for k in data:
            open_p  = float(str(k[1]))
            close_p = float(str(k[4]))
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
        r = requests.get(f"{BASE_URL}/fapi/v1/klines",
                         params={"symbol": symbole, "interval": "1h", "limit": limite}, timeout=10)
        return [float(str(k[4])) for k in r.json()]
    except:
        return []

def rsi(closes, p=14):
    if len(closes) < p+1: return 50
    g = [max(0, closes[i]-closes[i-1]) for i in range(1,len(closes))]
    l = [max(0, closes[i-1]-closes[i]) for i in range(1,len(closes))]
    mg, ml = sum(g[-p:])/p, sum(l[-p:])/p
    return round(100-(100/(1+mg/ml)),2) if ml else 100

def ma(closes, p):
    return sum(closes[-p:])/p if len(closes)>=p else None

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
        print("ERREUR : Impossible de recuperer les donnees")
        return

    print(f"{len(eth)} jours recuperes\n")

    mise = MISE_DEPART
    cumul = 0.0
    gagnes, perdus = 0, 0

    print(f"{'Date':<12} {'Marche':<8} {'Dir':<7} {'Mise':>6} {'Res':<10} {'Gain':>8} {'Cumul':>8}")
    print("-"*65)

    for i, (je, js) in enumerate(zip(eth, sol)):
        # Scores
        re = rsi(c_eth[-100:])
        rs = rsi(c_sol[-100:])

        se = 8 if re < 30 else 8 if re > 70 else 3
        ss = 8 if rs < 30 else 8 if rs > 70 else 3
        de = "ACHAT" if re < 50 else "VENTE"
        ds = "ACHAT" if rs < 50 else "VENTE"

        if se >= ss:
            marche, direction, var = "ETH", de, je["variation"]
        else:
            marche, direction, var = "SOL", ds, js["variation"]

        # Résultat
        if direction == "ACHAT":
            resultat = "GAGNE" if var > 0 else "PERDU"
        else:
            resultat = "GAGNE" if var < 0 else "PERDU"

        if resultat == "GAGNE":
            gain = mise * 2
            cumul += gain
            gagnes += 1
            prochaine = MISE_DEPART
            icone = "✅"
        else:
            gain = -mise
            cumul += gain
            perdus += 1
            prochaine = mise * 2
            icone = "❌"

        print(f"{je['date']:<12} {marche:<8} {direction:<7} {mise:>6.1f} {icone+' '+resultat:<10} {'+' if gain>=0 else ''}{gain:>7.2f} {'+' if cumul>=0 else ''}{cumul:>7.2f}")
        mise = prochaine

    print("\n" + "="*60)
    print("RAPPORT FINAL")
    print("="*60)
    print(f"Trades gagnes  : {gagnes}")
    print(f"Trades perdus  : {perdus}")
    taux = round(gagnes/max(gagnes+perdus,1)*100,1)
    print(f"Taux reussite  : {taux}%")
    print(f"Benefice net   : {'+' if cumul>=0 else ''}{round(cumul,2)} USDT")
    print(f"Mise finale    : {mise} USDT")
    print("="*60)

    if cumul > 0:
        print(f"RESULTAT POSITIF : +{round(cumul,2)} USDT sur 30 jours !")
    else:
        print(f"RESULTAT NEGATIF : {round(cumul,2)} USDT sur 30 jours")

if __name__ == "__main__":
    lancer_backtesting()
