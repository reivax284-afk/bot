"""
╔══════════════════════════════════════════════════════════════╗
║       BOT SCALPING V2 — RSI + RETOURNEMENT DE TENDANCE      ║
║       Mise 50EUR | +0.75EUR = ferme | -1.50EUR = ferme      ║
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
GAIN_CIBLE        = 0.75    # +0.75EUR
STOP_LOSS         = -1.50   # -1.50EUR
PAUSE             = 120     # 2 minutes entre trades
SCORE_MIN         = 10      # Score minimum 10/30
MARCHES           = ["DOGEUSDT", "SOLUSDT", "XRPUSDT", "AVAXUSDT",
                     "BNBUSDT", "LINKUSDT", "ADAUSDT"]

KRAKEN_SYMBOLS = {
    "DOGEUSDT": "XDGUSD",
    "SOLUSDT":  "SOLUSD",
    "XRPUSDT":  "XRPUSD",
    "AVAXUSDT": "AVAXUSD",
    "BNBUSDT":  "BNBUSD",
    "LINKUSDT": "LINKUSD",
    "ADAUSDT":  "ADAUSD"
}

print("=" * 55)
print("  BOT SCALPING V2 — RSI + RETOURNEMENT")
print(f"  Mise      : {MISE}EUR | Levier : x{LEVIER}")
print(f"  Objectif  : +{GAIN_CIBLE}EUR | Stop : {STOP_LOSS}EUR")
print(f"  Marches   : {len(MARCHES)} cryptos")
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
    params = {"pair": kraken_symbol, "interval": 60}
    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        errors = data.get("error", [])
        if errors:
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
# INDICATEUR 1 — RSI
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

def scorer_rsi(rsi):
    """Retourne (score, direction) selon le RSI"""
    if rsi < 25:   return 10, "ACHAT"
    elif rsi < 30: return 8,  "ACHAT"
    elif rsi < 40: return 5,  "ACHAT"
    elif rsi > 75: return 10, "VENTE"
    elif rsi > 70: return 8,  "VENTE"
    elif rsi > 60: return 5,  "VENTE"
    else:          return 2,  "NEUTRE"

# ══════════════════════════════════════════════════════════════
# INDICATEUR 2 — DÉTECTION DE RETOURNEMENT
# ══════════════════════════════════════════════════════════════

def detecter_retournement(closes, highs, lows):
    """
    Détecte si le prix commence à changer de direction.
    
    RETOURNEMENT BAISSIER (signal VENTE) :
    - Les 3 dernières bougies montaient
    - La dernière bougie commence à baisser
    → Le prix était en montée et commence à redescendre
    
    RETOURNEMENT HAUSSIER (signal ACHAT) :
    - Les 3 dernières bougies descendaient  
    - La dernière bougie commence à monter
    → Le prix était en baisse et commence à remonter
    """
    if len(closes) < 6:
        return "NEUTRE", 0

    # Mouvement des 3 bougies précédentes (avant la dernière)
    mouvement_precedent = (closes[-2] - closes[-5]) / closes[-5] * 100

    # Mouvement de la dernière bougie
    mouvement_recent = (closes[-1] - closes[-2]) / closes[-2] * 100

    # Amplitude de la dernière bougie (volatilité)
    amplitude = (highs[-1] - lows[-1]) / closes[-1] * 100

    print(f"    Mouvement precedent: {round(mouvement_precedent, 3)}% | "
          f"Recent: {round(mouvement_recent, 3)}% | "
          f"Amplitude: {round(amplitude, 3)}%")

    # RETOURNEMENT BAISSIER
    # Les prix montaient (+0.3% sur 3 bougies) et maintenant ça commence à baisser
    if mouvement_precedent > 0.3 and mouvement_recent < -0.1:
        force = abs(mouvement_precedent) + abs(mouvement_recent)
        return "VENTE", round(force, 3)

    # RETOURNEMENT HAUSSIER
    # Les prix baissaient (-0.3% sur 3 bougies) et maintenant ça commence à monter
    elif mouvement_precedent < -0.3 and mouvement_recent > 0.1:
        force = abs(mouvement_precedent) + abs(mouvement_recent)
        return "ACHAT", round(force, 3)

    else:
        return "NEUTRE", 0

# ══════════════════════════════════════════════════════════════
# ANALYSE COMBINÉE — RSI + RETOURNEMENT
# ══════════════════════════════════════════════════════════════

def analyser_marche(symbole):
    """
    Analyse combinée RSI + Retournement.
    
    Les deux indicateurs travaillent ensemble :
    - RSI dit si le marché est suracheté/survendu
    - Retournement dit si ça commence à changer de direction
    
    Signal fort = quand les DEUX sont d'accord
    """
    closes, highs, lows = get_klines(symbole)
    if closes is None:
        print(f"  {symbole} : Erreur données")
        return 0, "NEUTRE", {}

    # Calcul RSI
    rsi = calculer_rsi(closes)
    score_rsi, direction_rsi = scorer_rsi(rsi)

    # Détection retournement
    retournement, force = detecter_retournement(closes, highs, lows)

    # Volatilité
    if len(highs) >= 14:
        amplitudes = [(highs[i] - lows[i]) / closes[i] * 100 for i in range(-14, 0)]
        volatilite = round(sum(amplitudes) / len(amplitudes), 2)
    else:
        volatilite = 0

    # ══ LOGIQUE DE COMBINAISON RSI + RETOURNEMENT ══

    # CAS 1 : Les deux sont d'accord → signal très fort
    if direction_rsi == retournement and retournement != "NEUTRE":
        score_final = score_rsi + int(force * 5)
        score_final = min(score_final, 30)
        direction_finale = retournement
        signal = "RSI + RETOURNEMENT ACCORD"

    # CAS 2 : RSI fort mais pas encore de retournement → on attend
    elif direction_rsi != "NEUTRE" and retournement == "NEUTRE":
        score_final = score_rsi  # Score réduit, on attend confirmation
        direction_finale = direction_rsi
        signal = "RSI seul (attente retournement)"

    # CAS 3 : Retournement détecté mais RSI neutre → signal modéré
    elif retournement != "NEUTRE" and direction_rsi == "NEUTRE":
        score_final = int(force * 8)
        score_final = min(score_final, 15)
        direction_finale = retournement
        signal = "RETOURNEMENT seul"

    # CAS 4 : Les deux se contredisent → on ne trade pas
    elif direction_rsi != "NEUTRE" and retournement != "NEUTRE" and direction_rsi != retournement:
        score_final = 0
        direction_finale = "NEUTRE"
        signal = "CONTRADICTION RSI vs RETOURNEMENT"

    # CAS 5 : Aucun signal
    else:
        score_final = 0
        direction_finale = "NEUTRE"
        signal = "Aucun signal"

    print(f"  {symbole} : RSI {rsi} ({direction_rsi}) | "
          f"Retournement {retournement} | "
          f"Vol {volatilite}% | Score {score_final}/30")
    print(f"    Signal : {signal}")

    return score_final, direction_finale, {
        "rsi": rsi,
        "direction_rsi": direction_rsi,
        "retournement": retournement,
        "force_retournement": force,
        "volatilite": volatilite,
        "score_total": score_final,
        "direction": direction_finale,
        "signal": signal
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

    # Filtrer les marchés avec signal valide
    valides = {k: v for k, v in resultats.items()
               if v["direction"] != "NEUTRE" and v["score"] >= SCORE_MIN}

    if not valides:
        print("  => Aucun signal valide. On attend...")
        return None, "NEUTRE", {}

    # Choisir le marché avec le meilleur score
    # En cas d'égalité, on prend celui avec la meilleure volatilité
    meilleur = max(valides, key=lambda x: (
        valides[x]["score"],
        valides[x]["details"].get("volatilite", 0)
    ))
    direction = valides[meilleur]["direction"]
    score     = valides[meilleur]["score"]
    signal    = valides[meilleur]["details"].get("signal", "")
    vol       = valides[meilleur]["details"].get("volatilite", 0)

    print(f"\n  => CHOIX : {meilleur} ({direction})")
    print(f"     Score : {score}/30 | Vol : {vol}% | {signal}")
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
        prix_objectif  = round(prix_entree * (1 + pct_gain), 6)
        prix_stop_loss = round(prix_entree * (1 - pct_stop), 6)
    else:
        prix_objectif  = round(prix_entree * (1 - pct_gain), 6)
        prix_stop_loss = round(prix_entree * (1 + pct_stop), 6)

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
    if os.path.exists("etat_bot.json"):
        with open("etat_bot.json", "r") as f:
            return json.load(f)
    return {
        "total_gagne": 0.0, "total_perdu": 0.0,
        "cumul_net": 0.0, "nb_trades": 0,
        "nb_wins": 0, "nb_losses": 0,
        "nb_skips": 0, "historique": []
    }

def sauvegarder_etat(etat):
    with open("etat_bot.json", "w") as f:
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
