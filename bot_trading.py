"""
╔══════════════════════════════════════════════════════════════╗
║       BOT MARTINGALE — MODE SIMULATION COMPLÈTE             ║
║       Pas besoin de Binance · Trades simulés en local       ║
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

MISE_DEPART  = float(os.environ.get("MISE_DEPART", "5.0"))
LEVIER       = int(os.environ.get("LEVIER", "3"))
MARCHES      = ["ETHUSDT", "SOLUSDT"]
FICHIER_ETAT = "etat_bot.json"

# Objectif : tripler la mise avec levier x3
# Mouvement nécessaire sur le prix : +33% (x3 avec levier x3)
OBJECTIF_PCT    = 0.333   # +33.3% de mouvement
STOP_LOSS_PCT   = 0.333   # -33.3% = perte totale de la mise

print("=" * 55)
print("  BOT MARTINGALE — SIMULATION COMPLETE")
print(f"  Mise depart : {MISE_DEPART}EUR | Levier : x{LEVIER}")
print(f"  Source prix : CoinGecko (sans restriction)")
print("=" * 55)

# ══════════════════════════════════════════════════════════════
# RÉCUPÉRATION DES PRIX VIA COINGECKO (sans restriction geo)
# ══════════════════════════════════════════════════════════════

COINGECKO_IDS = {
    "ETHUSDT": "ethereum",
    "SOLUSDT": "solana"
}

def get_klines_coingecko(symbole, limite=100):
    """Récupère les bougies horaires via CoinGecko"""
    coin_id = COINGECKO_IDS.get(symbole)
    if not coin_id:
        return None, None, None
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
    params = {"vs_currency": "usd", "days": "7"}  # 7 jours = bougies de 4h
    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        if not isinstance(data, list) or len(data) == 0:
            print(f"  Erreur CoinGecko {symbole} : {data}")
            return None, None, None
        closes = [float(k[4]) for k in data]
        highs  = [float(k[2]) for k in data]
        lows   = [float(k[3]) for k in data]
        return closes[-limite:], highs[-limite:], lows[-limite:]
    except Exception as e:
        print(f"  Erreur klines {symbole} : {e}")
        return None, None, None

def get_prix_actuel_coingecko(symbole):
    """Récupère le prix actuel via CoinGecko"""
    coin_id = COINGECKO_IDS.get(symbole)
    if not coin_id:
        return None
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": coin_id, "vs_currencies": "usd"}
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        prix = data[coin_id]["usd"]
        return float(prix)
    except Exception as e:
        print(f"  Erreur prix {symbole} : {e}")
        return None

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
    rs = moy_gain / moy_perte
    return round(100 - (100 / (1 + rs)), 2)

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
    print(f"\n  Analyse {symbole}...")
    closes, highs, lows = get_klines_coingecko(symbole)
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

    print(f"    RSI        : {rsi} -> {score_rsi}/10 ({direction})")
    print(f"    MA         : {score_ma}/10 ({direction_ma})")
    print(f"    Volatilite : {volatilite}% -> {score_vol}/10")
    print(f"    SCORE      : {score_total}/30")

    return score_total, direction, {
        "rsi": rsi, "score_rsi": score_rsi,
        "score_ma": score_ma, "volatilite": volatilite,
        "score_vol": score_vol, "score_total": score_total,
        "direction": direction
    }

def choisir_meilleur_marche():
    print("\n" + "-"*55)
    print("  SELECTION DU MARCHE DU JOUR")
    print("-"*55)
    resultats = {}
    for marche in MARCHES:
        score, direction, details = scorer_marche(marche)
        resultats[marche] = {"score": score, "direction": direction, "details": details}
        time.sleep(2)  # Respecter rate limit CoinGecko
    meilleur = max(resultats, key=lambda x: resultats[x]["score"])
    print(f"\n  MARCHE CHOISI : {meilleur} (score {resultats[meilleur]['score']}/30)")
    print(f"  Direction     : {resultats[meilleur]['direction']}")
    return meilleur, resultats[meilleur]["direction"], resultats[meilleur]["details"]

# ══════════════════════════════════════════════════════════════
# SIMULATION DU TRADE (sans Binance)
# ══════════════════════════════════════════════════════════════

def simuler_trade(symbole, direction, mise):
    """
    Surveille le prix en temps réel et simule le trade.
    Vérifie toutes les 5 minutes si objectif ou stop-loss atteint.
    Timeout : 24h max puis on ferme au prix du moment.
    """
    prix_entree = get_prix_actuel_coingecko(symbole)
    if prix_entree is None:
        print("  Erreur : impossible de recuperer le prix d'entree")
        return "PERDU", -mise

    if direction == "ACHAT":
        prix_objectif  = round(prix_entree * (1 + OBJECTIF_PCT), 4)
        prix_stop_loss = round(prix_entree * (1 - STOP_LOSS_PCT), 4)
    else:
        prix_objectif  = round(prix_entree * (1 - OBJECTIF_PCT), 4)
        prix_stop_loss = round(prix_entree * (1 + STOP_LOSS_PCT), 4)

    print(f"\n  TRADE SIMULE OUVERT")
    print(f"  Symbole    : {symbole}")
    print(f"  Direction  : {direction}")
    print(f"  Mise       : {mise}EUR (levier x{LEVIER} = {mise*LEVIER}EUR controles)")
    print(f"  Prix entree: {prix_entree}")
    print(f"  Objectif   : {prix_objectif} (+{mise*2}EUR si atteint)")
    print(f"  Stop-Loss  : {prix_stop_loss} (-{mise}EUR si atteint)")
    print(f"  Verification toutes les 5 minutes...\n")

    debut = time.time()
    timeout = 24 * 3600  # 24h max

    while True:
        time.sleep(300)  # Vérification toutes les 5 minutes

        prix_actuel = get_prix_actuel_coingecko(symbole)
        if prix_actuel is None:
            continue

        heure = datetime.now().strftime("%H:%M:%S")
        duree = int((time.time() - debut) / 60)

        print(f"  [{heure}] {symbole} : {prix_actuel} USD | "
              f"Objectif : {prix_objectif} | Stop : {prix_stop_loss} | "
              f"Depuis : {duree}min")

        if direction == "ACHAT":
            if prix_actuel >= prix_objectif:
                print(f"\n  OBJECTIF ATTEINT ! {prix_actuel} >= {prix_objectif}")
                print(f"  RESULTAT : GAGNE +{mise*2}EUR")
                return "GAGNE", mise * 2
            elif prix_actuel <= prix_stop_loss:
                print(f"\n  STOP-LOSS ATTEINT ! {prix_actuel} <= {prix_stop_loss}")
                print(f"  RESULTAT : PERDU -{mise}EUR")
                return "PERDU", -mise
        else:
            if prix_actuel <= prix_objectif:
                print(f"\n  OBJECTIF ATTEINT ! {prix_actuel} <= {prix_objectif}")
                print(f"  RESULTAT : GAGNE +{mise*2}EUR")
                return "GAGNE", mise * 2
            elif prix_actuel >= prix_stop_loss:
                print(f"\n  STOP-LOSS ATTEINT ! {prix_actuel} >= {prix_stop_loss}")
                print(f"  RESULTAT : PERDU -{mise}EUR")
                return "PERDU", -mise

        # Timeout 24h
        if time.time() - debut > timeout:
            pnl_pct = (prix_actuel - prix_entree) / prix_entree
            if direction == "VENTE":
                pnl_pct = -pnl_pct
            gain = round(mise * pnl_pct * LEVIER, 2)
            resultat = "GAGNE" if gain > 0 else "PERDU"
            print(f"\n  TIMEOUT 24H — Fermeture au prix actuel : {prix_actuel}")
            print(f"  RESULTAT : {resultat} {'+' if gain >= 0 else ''}{gain}EUR")
            return resultat, gain

# ══════════════════════════════════════════════════════════════
# GESTION DE L'ÉTAT
# ══════════════════════════════════════════════════════════════

def charger_etat():
    if os.path.exists(FICHIER_ETAT):
        with open(FICHIER_ETAT, "r") as f:
            return json.load(f)
    return {
        "mise_actuelle": MISE_DEPART,
        "pertes_consecutives": 0,
        "total_perdu": 0.0,
        "total_gagne": 0.0,
        "cumul_net": 0.0,
        "trade_du_jour_fait": False,
        "date_dernier_trade": "",
        "historique": []
    }

def sauvegarder_etat(etat):
    with open(FICHIER_ETAT, "w") as f:
        json.dump(etat, f, indent=2, ensure_ascii=False)

def afficher_tableau_de_bord(etat):
    print("\n" + "="*55)
    print("  TABLEAU DE BORD")
    print("="*55)
    print(f"  Mise actuelle      : {etat['mise_actuelle']}EUR")
    print(f"  Pertes consecutives: {etat['pertes_consecutives']}")
    print(f"  Total gagne        : +{etat['total_gagne']}EUR")
    print(f"  Total perdu        : -{etat['total_perdu']}EUR")
    print(f"  Benefice net       : {'+' if etat['cumul_net'] >= 0 else ''}{round(etat['cumul_net'], 2)}EUR")
    print(f"  Dernier trade      : {etat['date_dernier_trade'] or 'Aucun'}")
    if etat["historique"]:
        print(f"\n  Derniers trades :")
        for h in etat["historique"][-5:]:
            icone = "OK" if h["resultat"] == "GAGNE" else "XX"
            print(f"    [{icone}] {h['date']} | {h['marche']} | {h['mise']}EUR | "
                  f"{h['resultat']} | {'+' if h['gain'] >= 0 else ''}{h['gain']}EUR | "
                  f"Cumul: {'+' if h['cumul'] >= 0 else ''}{h['cumul']}EUR")
    print("="*55)

def calculer_prochaine_mise(etat, resultat):
    if resultat == "GAGNE":
        etat["mise_actuelle"]        = MISE_DEPART
        etat["pertes_consecutives"]  = 0
        print(f"\n  GAGNE ! Retour a la mise de depart : {MISE_DEPART}EUR demain")
    else:
        prochaine = etat["mise_actuelle"] * 2
        etat["pertes_consecutives"] += 1
        print(f"\n  PERDU. Mise doublee pour demain : {prochaine}EUR")
        print(f"  ({etat['pertes_consecutives']} perte(s) consecutive(s))")
        etat["mise_actuelle"] = prochaine
    return etat

# ══════════════════════════════════════════════════════════════
# TRADE DU JOUR
# ══════════════════════════════════════════════════════════════

def trade_du_jour():
    print("\n" + "█"*55)
    print("█  TRADE DU JOUR — SIMULATION")
    print(f"█  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("█"*55)

    etat = charger_etat()
    afficher_tableau_de_bord(etat)

    aujourd_hui = datetime.now().strftime("%Y-%m-%d")
    if etat["trade_du_jour_fait"] and etat["date_dernier_trade"] == aujourd_hui:
        print("\n  Trade du jour deja effectue. On attend demain.")
        return

    mise = etat["mise_actuelle"]
    print(f"\n  Mise du jour : {mise}EUR | Objectif : +{mise*2}EUR net")

    symbole, direction, details = choisir_meilleur_marche()

    if direction == "NEUTRE":
        print("  Aucun signal clair. On passe cette journee.")
        return

    etat["trade_du_jour_fait"] = True
    etat["date_dernier_trade"] = aujourd_hui
    sauvegarder_etat(etat)

    resultat, gain_perte = simuler_trade(symbole, direction, mise)

    if resultat == "GAGNE":
        etat["total_gagne"] += abs(gain_perte)
    else:
        etat["total_perdu"] += abs(gain_perte)

    etat["cumul_net"] = round(etat["total_gagne"] - etat["total_perdu"], 2)
    etat["historique"].append({
        "date":     aujourd_hui,
        "marche":   symbole,
        "mise":     mise,
        "resultat": resultat,
        "gain":     round(gain_perte, 2),
        "cumul":    etat["cumul_net"],
        "direction": direction
    })

    etat = calculer_prochaine_mise(etat, resultat)
    etat["trade_du_jour_fait"] = False
    sauvegarder_etat(etat)

    print("\n" + "="*55)
    print("  RESUME DU TRADE")
    print("="*55)
    print(f"  Marche    : {symbole}")
    print(f"  Direction : {direction}")
    print(f"  Mise      : {mise}EUR")
    print(f"  Resultat  : {'GAGNE' if resultat == 'GAGNE' else 'PERDU'}")
    print(f"  Gain/Perte: {'+' if gain_perte >= 0 else ''}{round(gain_perte, 2)}EUR")
    print(f"  Cumul net : {'+' if etat['cumul_net'] >= 0 else ''}{etat['cumul_net']}EUR")
    print(f"  Mise demain: {etat['mise_actuelle']}EUR")
    print("="*55)

# ══════════════════════════════════════════════════════════════
# BOUCLE PRINCIPALE
# ══════════════════════════════════════════════════════════════

def demarrer_bot():
    print(f"\n  DEMARRAGE — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    while True:
        try:
            trade_du_jour()
        except KeyboardInterrupt:
            print("\n  Bot arrete.")
            break
        except Exception as e:
            print(f"\n  Erreur : {e}")
            print("  Nouvelle tentative dans 5 minutes...")
            time.sleep(300)
            continue

        print(f"\n  Prochaine verification dans 1 heure...")
        time.sleep(3600)

if __name__ == "__main__":
    demarrer_bot()
