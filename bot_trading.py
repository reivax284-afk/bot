"""
╔══════════════════════════════════════════════════════════════╗
║       BOT SCALPING — SIMULATION COMPLETE                    ║
║       Source prix : Kraken (sans restriction)               ║
║       Mise fixe 50EUR | +0.10EUR = ferme | -25EUR = ferme   ║
╚══════════════════════════════════════════════════════════════╝
"""

import requests
import json
import time
import os
from datetime import datetime

# ══════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════

MISE              = 50.0
LEVIER            = 3
GAIN_CIBLE        = 0.10   # +0.10EUR
STOP_LOSS         = -25.0  # -25EUR
PAUSE             = 600    # 10 minutes entre trades
MARCHES           = ["SOLUSDT"]
FICHIER_ETAT      = "etat_bot.json"

KRAKEN_SYMBOLS = {
    "ETHUSDT": "XETHZUSD",
    "SOLUSDT": "SOLUSDT"
}

print("=" * 55)
print("  BOT SCALPING — SIMULATION COMPLETE")
print(f"  Mise fixe  : {MISE}EUR | Levier : x{LEVIER}")
print(f"  Objectif   : +{GAIN_CIBLE}EUR | Stop : {STOP_LOSS}EUR")
print(f"  Pause      : {PAUSE//60} minutes entre chaque trade")
print(f"  Source     : Kraken API (sans restriction)")
print("=" * 55)

# ══════════════════════════════════════════════════════════════
# RÉCUPÉRATION DES PRIX VIA KRAKEN
# ══════════════════════════════════════════════════════════════

def get_prix_actuel(symbole):
    kraken_symbol = KRAKEN_SYMBOLS.get(symbole, symbole)
    url = "https://api.kraken.com/0/public/Ticker"
    try:
        r = requests.get(url, params={"pair": kraken_symbol}, timeout=10)
        data = r.json()
        if data.get("error"):
            print(f"  Erreur Kraken : {data['error']}")
            return None
        result = data.get("result", {})
        key = list(result.keys())[0]
        prix = float(result[key]["c"][0])  # "c" = dernier prix
        return prix
    except Exception as e:
        print(f"  Erreur prix {symbole} : {e}")
        return None

def get_klines(symbole, limite=50):
    kraken_symbol = KRAKEN_SYMBOLS.get(symbole, symbole)
    url = "https://api.kraken.com/0/public/OHLC"
    params = {"pair": kraken_symbol, "interval": 60}  # bougies 1h
    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        if data.get("error"):
            return None, None, None
        result = data.get("result", {})
        key = [k for k in result.keys() if k != "last"][0]
        candles = result[key]
        closes = [float(k[4]) for k in candles]
        highs  = [float(k[2]) for k in candles]
        lows   = [float(k[3]) for k in candles]
        return closes[-limite:], highs[-limite:], lows[-limite:]
    except Exception as e:
        print(f"  Erreur klines {symbole} : {e}")
        return None, None, None

# ══════════════════════════════════════════════════════════════
# INDICATEURS TECHNIQUES
# ══════════════════════════════════════════════════════════════

def calculer_rsi(closes, periode=14):
    if len(closes) < periode + 1:
        return 50
    gains, pertes = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(max(diff, 0))
        pertes.append(abs(min(diff, 0)))
    moy_gain  = sum(gains[-periode:]) / periode
    moy_perte = sum(pertes[-periode:]) / periode
    if moy_perte == 0:
        return 100
    return round(100 - (100 / (1 + moy_gain / moy_perte)), 2)

def calculer_moyenne_mobile(closes, periode):
    if len(closes) < periode:
        return None
    return sum(closes[-periode:]) / periode

def calculer_volatilite(closes, highs, lows, periode=14):
    if len(closes) < periode:
        return 0
    amplitudes = [(highs[i] - lows[i]) / closes[i] * 100 for i in range(-periode, 0)]
    return round(sum(amplitudes) / len(amplitudes), 2)

# ══════════════════════════════════════════════════════════════
# SCORING ET CHOIX DU MARCHÉ
# ══════════════════════════════════════════════════════════════

def scorer_marche(symbole):
    closes, highs, lows = get_klines(symbole)
    if closes is None:
        return 0, "NEUTRE", {}

    rsi        = calculer_rsi(closes)
    ma_courte  = calculer_moyenne_mobile(closes, 10)
    ma_longue  = calculer_moyenne_mobile(closes, 30)
    volatilite = calculer_volatilite(closes, highs, lows)

    if rsi < 25:   score_rsi, direction = 10, "ACHAT"
    elif rsi < 30: score_rsi, direction = 8,  "ACHAT"
    elif rsi < 40: score_rsi, direction = 5,  "ACHAT"
    elif rsi > 75: score_rsi, direction = 10, "VENTE"
    elif rsi > 70: score_rsi, direction = 8,  "VENTE"
    elif rsi > 60: score_rsi, direction = 5,  "VENTE"
    else:          score_rsi, direction = 2,  "NEUTRE"

    if ma_courte and ma_longue:
        ecart        = abs(ma_courte - ma_longue) / ma_longue * 100
        direction_ma = "ACHAT" if ma_courte > ma_longue else "VENTE"
        if ecart > 2:     score_ma = 10
        elif ecart > 1:   score_ma = 7
        elif ecart > 0.5: score_ma = 4
        else:             score_ma = 1
    else:
        score_ma, direction_ma = 0, "NEUTRE"

    if volatilite > 3:     score_vol = 10
    elif volatilite > 2:   score_vol = 8
    elif volatilite > 1:   score_vol = 5
    elif volatilite > 0.5: score_vol = 3
    else:                  score_vol = 1

    score_total = score_rsi + score_ma + score_vol
    if direction == "NEUTRE":
        direction = direction_ma

    return score_total, direction, {
        "rsi": rsi, "score_total": score_total, "direction": direction
    }

def choisir_meilleur_marche():
    print("\n  Analyse des marches...")
    resultats = {}
    for marche in MARCHES:
        score, direction, details = scorer_marche(marche)
        resultats[marche] = {"score": score, "direction": direction, "details": details}
        print(f"    {marche} : score {score}/30 ({direction})")
        time.sleep(1)
    meilleur  = max(resultats, key=lambda x: resultats[x]["score"])
    direction = resultats[meilleur]["direction"]
    print(f"  => CHOIX : {meilleur} ({direction})")
    return meilleur, direction, resultats[meilleur]["details"]

# ══════════════════════════════════════════════════════════════
# SIMULATION DU TRADE
# ══════════════════════════════════════════════════════════════

def simuler_trade(symbole, direction, numero_trade):
    prix_entree = get_prix_actuel(symbole)
    if prix_entree is None:
        return "ERREUR", 0

    pct_gain_cible = GAIN_CIBLE / (MISE * LEVIER)
    pct_stop       = abs(STOP_LOSS) / (MISE * LEVIER)

    if direction == "ACHAT":
        prix_objectif  = round(prix_entree * (1 + pct_gain_cible), 4)
        prix_stop_loss = round(prix_entree * (1 - pct_stop), 4)
    else:
        prix_objectif  = round(prix_entree * (1 - pct_gain_cible), 4)
        prix_stop_loss = round(prix_entree * (1 + pct_stop), 4)

    print(f"\n  {'='*50}")
    print(f"  TRADE #{numero_trade} — {datetime.now().strftime('%H:%M:%S')}")
    print(f"  {'='*50}")
    print(f"  Symbole    : {symbole} ({direction})")
    print(f"  Prix entree: {prix_entree}")
    print(f"  Objectif   : {prix_objectif} -> +{GAIN_CIBLE}EUR")
    print(f"  Stop-Loss  : {prix_stop_loss} -> {STOP_LOSS}EUR")
    print(f"  Surveillance toutes les 60 secondes...\n")

    debut = time.time()

    while True:
        time.sleep(60)

        prix_actuel = get_prix_actuel(symbole)
        if prix_actuel is None:
            continue

        if direction == "ACHAT":
            pnl = round((prix_actuel - prix_entree) / prix_entree * MISE * LEVIER, 2)
        else:
            pnl = round((prix_entree - prix_actuel) / prix_entree * MISE * LEVIER, 2)

        heure = datetime.now().strftime("%H:%M:%S")
        duree = int((time.time() - debut) / 60)
        print(f"  [{heure}] {symbole}: {prix_actuel} | "
              f"PnL: {'+' if pnl >= 0 else ''}{pnl}EUR | {duree}min")

        if pnl >= GAIN_CIBLE:
            print(f"\n  OBJECTIF ATTEINT ! +{pnl}EUR")
            return "GAGNE", pnl

        if pnl <= STOP_LOSS:
            print(f"\n  STOP-LOSS ATTEINT ! {pnl}EUR")
            return "PERDU", pnl

        # Timeout 24h
        if time.time() - debut > 86400:
            print(f"\n  TIMEOUT 24H — Fermeture : {'+' if pnl >= 0 else ''}{pnl}EUR")
            return ("GAGNE" if pnl > 0 else "PERDU"), pnl

# ══════════════════════════════════════════════════════════════
# GESTION DE L'ÉTAT
# ══════════════════════════════════════════════════════════════

def charger_etat():
    if os.path.exists(FICHIER_ETAT):
        with open(FICHIER_ETAT, "r") as f:
            return json.load(f)
    return {
        "total_gagne": 0.0,
        "total_perdu": 0.0,
        "cumul_net": 0.0,
        "nb_trades": 0,
        "nb_wins": 0,
        "nb_losses": 0,
        "historique": []
    }

def sauvegarder_etat(etat):
    with open(FICHIER_ETAT, "w") as f:
        json.dump(etat, f, indent=2, ensure_ascii=False)

def afficher_tableau_de_bord(etat):
    win_rate = (etat["nb_wins"] / etat["nb_trades"] * 100) if etat["nb_trades"] > 0 else 0
    print(f"\n  {'='*55}")
    print(f"  TABLEAU DE BORD")
    print(f"  {'='*55}")
    print(f"  Trades total  : {etat['nb_trades']}")
    print(f"  Victoires     : {etat['nb_wins']} ({win_rate:.1f}%)")
    print(f"  Defaites      : {etat['nb_losses']}")
    print(f"  Total gagne   : +{round(etat['total_gagne'], 2)}EUR")
    print(f"  Total perdu   : -{round(etat['total_perdu'], 2)}EUR")
    print(f"  BENEFICE NET  : {'+' if etat['cumul_net'] >= 0 else ''}{round(etat['cumul_net'], 2)}EUR")
    if etat["historique"]:
        print(f"\n  Derniers trades :")
        for h in etat["historique"][-5:]:
            icone = "OK" if h["resultat"] == "GAGNE" else "XX"
            print(f"    [{icone}] {h['heure']} | {h['marche']} | "
                  f"{h['resultat']} | {'+' if h['gain'] >= 0 else ''}{h['gain']}EUR | "
                  f"Cumul: {'+' if h['cumul'] >= 0 else ''}{h['cumul']}EUR")
    print(f"  {'='*55}")

# ══════════════════════════════════════════════════════════════
# BOUCLE PRINCIPALE
# ══════════════════════════════════════════════════════════════

def demarrer_bot():
    print(f"\n  DEMARRAGE — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    etat = charger_etat()
    afficher_tableau_de_bord(etat)

    while True:
        try:
            etat["nb_trades"] += 1
            symbole, direction, details = choisir_meilleur_marche()

            if direction == "NEUTRE":
                print("  Aucun signal. Nouvelle analyse dans 10 minutes...")
                time.sleep(PAUSE)
                continue

            resultat, gain = simuler_trade(symbole, direction, etat["nb_trades"])

            if resultat == "ERREUR":
                print("  Erreur trade. Nouvelle tentative dans 10 minutes...")
                etat["nb_trades"] -= 1
                time.sleep(PAUSE)
                continue

            if resultat == "GAGNE":
                etat["nb_wins"]     += 1
                etat["total_gagne"]  = round(etat["total_gagne"] + gain, 2)
            else:
                etat["nb_losses"]   += 1
                etat["total_perdu"]  = round(etat["total_perdu"] + abs(gain), 2)

            etat["cumul_net"] = round(etat["total_gagne"] - etat["total_perdu"], 2)
            etat["historique"].append({
                "heure":     datetime.now().strftime("%Y-%m-%d %H:%M"),
                "marche":    symbole,
                "direction": direction,
                "resultat":  resultat,
                "gain":      round(gain, 2),
                "cumul":     etat["cumul_net"]
            })
            sauvegarder_etat(etat)
            afficher_tableau_de_bord(etat)

            print(f"\n  Pause de 10 minutes avant le prochain trade...")
            time.sleep(PAUSE)

        except KeyboardInterrupt:
            print("\n  Bot arrete.")
            break
        except Exception as e:
            print(f"\n  Erreur : {e}")
            time.sleep(300)

if __name__ == "__main__":
    demarrer_bot()
