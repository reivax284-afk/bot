"""
╔══════════════════════════════════════════════════════════════╗
║       BOT SCALPING — SUIVI DE TENDANCE                      ║
║       Seuil tendance 1% | Mise 50EUR | +0.10EUR / -25EUR    ║
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
GAIN_CIBLE        = 0.10    # +0.10EUR
STOP_LOSS         = -25.0   # -25EUR
PAUSE             = 120     # 2 minutes entre trades
SEUIL_TENDANCE    = 0.5     # 1% de mouvement pour confirmer tendance
MARCHES           = ["ETHUSDT", "SOLUSDT", "XRPUSDT", "AVAXUSDT"]
FICHIER_ETAT      = "etat_bot.json"

KRAKEN_SYMBOLS = {
    "ETHUSDT":  "XETHZUSD",
    "SOLUSDT":  "SOLUSDT",
    "XRPUSDT":  "XRPUSD",
    "AVAXUSDT": "AVAXUSD"
}

print("=" * 55)
print("  BOT SCALPING — SUIVI DE TENDANCE")
print(f"  Mise      : {MISE}EUR | Levier : x{LEVIER}")
print(f"  Objectif  : +{GAIN_CIBLE}EUR | Stop : {STOP_LOSS}EUR")
print(f"  Tendance  : seuil {SEUIL_TENDANCE}%")
print(f"  Marches   : {', '.join(MARCHES)}")
print(f"  Source    : Kraken API (sans restriction)")
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
        if data.get("error") and data["error"]:
            print(f"  Erreur prix {symbole} : {data['error']}")
            return None
        result = data.get("result", {})
        key = list(result.keys())[0]
        return float(result[key]["c"][0])
    except Exception as e:
        print(f"  Erreur prix {symbole} : {e}")
        return None

def get_klines(symbole, limite=50):
    kraken_symbol = KRAKEN_SYMBOLS.get(symbole, symbole)
    url = "https://api.kraken.com/0/public/OHLC"
    params = {"pair": kraken_symbol, "interval": 5}
    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        errors = data.get("error", [])
        if errors:
            print(f"  Erreur klines {symbole} : {errors}")
            return None, None, None
        result = data.get("result", {})
        keys = [k for k in result.keys() if k != "last"]
        if not keys:
            return None, None, None
        candles = result[keys[0]]
        closes = [float(k[4]) for k in candles]
        highs  = [float(k[2]) for k in candles]
        lows   = [float(k[3]) for k in candles]
        return closes[-limite:], highs[-limite:], lows[-limite:]
    except Exception as e:
        print(f"  Erreur klines {symbole} : {e}")
        return None, None, None

# ══════════════════════════════════════════════════════════════
# DÉTECTION DE TENDANCE (basée sur le mouvement réel du prix)
# ══════════════════════════════════════════════════════════════

def detecter_tendance(closes, highs, lows):
    """
    Détecte la tendance en regardant le mouvement réel du prix
    sur les dernières bougies.
    
    - Si le prix a monté de +1% sur les 3 dernières bougies → HAUSSIERE → ACHAT
    - Si le prix a baissé de -1% sur les 3 dernières bougies → BAISSIERE → VENTE
    - Sinon → NEUTRE → on attend
    """
    if len(closes) < 6:
        return "NEUTRE", 0

    # Mouvement sur les 3 dernières bougies
    prix_actuel = closes[-1]
    prix_3h_avant = closes[-4]
    mouvement_3h = (prix_actuel - prix_3h_avant) / prix_3h_avant * 100

    # Mouvement sur la dernière bougie
    prix_1h_avant = closes[-2]
    mouvement_1h = (prix_actuel - prix_1h_avant) / prix_1h_avant * 100

    # Amplitude (volatilité) de la dernière bougie
    amplitude = (highs[-1] - lows[-1]) / closes[-1] * 100

    print(f"    Mouvement 3h: {round(mouvement_3h, 2)}% | "
          f"Mouvement 1h: {round(mouvement_1h, 2)}% | "
          f"Amplitude: {round(amplitude, 2)}%")

    # Tendance haussière : mouvement 3h > +1% ET dernière bougie positive
    if mouvement_3h >= SEUIL_TENDANCE and mouvement_1h >= 0:
        return "HAUSSIERE", mouvement_3h

    # Tendance baissière : mouvement 3h < -1% ET dernière bougie négative
    elif mouvement_3h <= -SEUIL_TENDANCE and mouvement_1h <= 0:
        return "BAISSIERE", mouvement_3h

    # Marché flat
    else:
        return "NEUTRE", mouvement_3h

def analyser_marche(symbole):
    """
    Analyse complète du marché.
    Retourne : (score, direction, details)
    """
    closes, highs, lows = get_klines(symbole)
    if closes is None:
        print(f"  {symbole} : Erreur données")
        return 0, "NEUTRE", {}

    tendance, mouvement = detecter_tendance(closes, highs, lows)

    if tendance == "HAUSSIERE":
        direction = "ACHAT"
        score = min(int(abs(mouvement) * 10), 30)  # Plus ça monte, plus le score est élevé
    elif tendance == "BAISSIERE":
        direction = "VENTE"
        score = min(int(abs(mouvement) * 10), 30)
    else:
        direction = "NEUTRE"
        score = 0

    print(f"  {symbole} : score {score}/30 | "
          f"Tendance {tendance} | {direction}")

    return score, direction, {
        "tendance": tendance,
        "mouvement": mouvement,
        "score": score,
        "direction": direction
    }

def choisir_meilleur_marche():
    print(f"\n  [{datetime.now().strftime('%H:%M:%S')}] Analyse des marches...")
    resultats = {}

    for marche in MARCHES:
        score, direction, details = analyser_marche(marche)
        resultats[marche] = {
            "score": score,
            "direction": direction,
            "details": details
        }
        time.sleep(1)

    # Filtre : on ne garde que les marchés avec une vraie tendance
    valides = {k: v for k, v in resultats.items() if v["direction"] != "NEUTRE" and v["score"] > 0}

    if not valides:
        print("  => Aucune tendance claire. On attend...")
        return None, "NEUTRE", {}

    # On choisit le marché avec le mouvement le plus fort
    meilleur = max(valides, key=lambda x: valides[x]["score"])
    direction = valides[meilleur]["direction"]
    score = valides[meilleur]["score"]

    print(f"\n  => CHOIX : {meilleur} ({direction}) — Score {score}/30 ✅")
    return meilleur, direction, valides[meilleur]["details"]

# ══════════════════════════════════════════════════════════════
# SIMULATION DU TRADE
# ══════════════════════════════════════════════════════════════

def simuler_trade(symbole, direction, numero_trade):
    prix_entree = get_prix_actuel(symbole)
    if prix_entree is None:
        return "ERREUR", 0

    pct_gain = GAIN_CIBLE / (MISE * LEVIER)
    pct_stop = abs(STOP_LOSS) / (MISE * LEVIER)

    if direction == "ACHAT":
        prix_objectif  = round(prix_entree * (1 + pct_gain), 4)
        prix_stop_loss = round(prix_entree * (1 - pct_stop), 4)
    else:
        prix_objectif  = round(prix_entree * (1 - pct_gain), 4)
        prix_stop_loss = round(prix_entree * (1 + pct_stop), 4)

    print(f"\n  {'='*50}")
    print(f"  TRADE #{numero_trade} — {datetime.now().strftime('%H:%M:%S')}")
    print(f"  {'='*50}")
    print(f"  Symbole    : {symbole} ({direction})")
    print(f"  Prix entree: {prix_entree}")
    print(f"  Objectif   : {prix_objectif} -> +{GAIN_CIBLE}EUR")
    print(f"  Stop-Loss  : {prix_stop_loss} -> {STOP_LOSS}EUR")
    print(f"  Mouvement  : {round(pct_gain*100, 3)}%\n")

    debut = time.time()

    while True:
        time.sleep(30)

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
        "nb_skips": 0,
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
    print(f"  Signaux sautes: {etat['nb_skips']}")
    print(f"  Total gagne   : +{round(etat['total_gagne'], 2)}EUR")
    print(f"  Total perdu   : -{round(etat['total_perdu'], 2)}EUR")
    print(f"  BENEFICE NET  : {'+' if etat['cumul_net'] >= 0 else ''}{round(etat['cumul_net'], 2)}EUR")
    if etat["historique"]:
        print(f"\n  Derniers trades :")
        for h in etat["historique"][-5:]:
            icone = "OK" if h["resultat"] == "GAGNE" else "XX"
            print(f"    [{icone}] {h['heure']} | {h['marche']} | "
                  f"{h['direction']} | {h['resultat']} | "
                  f"{'+' if h['gain'] >= 0 else ''}{h['gain']}EUR | "
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
            symbole, direction, details = choisir_meilleur_marche()

            if direction == "NEUTRE" or symbole is None:
                etat["nb_skips"] += 1
                sauvegarder_etat(etat)
                print(f"  Nouvelle analyse dans 2 minutes...")
                time.sleep(PAUSE)
                continue

            etat["nb_trades"] += 1
            resultat, gain = simuler_trade(symbole, direction, etat["nb_trades"])

            if resultat == "ERREUR":
                etat["nb_trades"] -= 1
                print("  Erreur. Nouvelle tentative dans 2 minutes...")
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

            print(f"\n  Pause de 2 minutes avant le prochain trade...")
            time.sleep(PAUSE)

        except KeyboardInterrupt:
            print("\n  Bot arrete.")
            break
        except Exception as e:
            print(f"\n  Erreur : {e}")
            time.sleep(60)

if __name__ == "__main__":
    demarrer_bot()
