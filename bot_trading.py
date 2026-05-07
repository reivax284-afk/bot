"""
╔══════════════════════════════════════════════════════════════╗
║                    BOT ULTIME V4                             ║
║         BTC + ETH | H1 | ATR Dynamique | Kelly 25%          ║
║      Stop ATR+Structure | Ratio 1:2 | Kill Switch            ║
║         Risque 1% capital | Seuil ruine -50%                 ║
╚══════════════════════════════════════════════════════════════╝
"""

import requests
import json
import time
import os
import numpy as np
from datetime import datetime

# ══════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════

CAPITAL_INITIAL  = 50.0      # Capital de départ en EUR
LEVIER           = 3         # Levier x3
RISQUE_PAR_TRADE = 0.01      # 1% du capital par trade
ATR_MULTIPLIER   = 2.0       # Stop = ATR × 2
RATIO_RR         = 2.0       # Objectif = Stop × 2 (ratio 1:2)
ATR_PERIODE      = 14        # Période ATR
KELLY_FRACTION   = 0.25      # Kelly fractionné à 25%
KELLY_CAP        = 0.05      # Cap Kelly à 5% max du capital
PAUSE            = 120       # 2 minutes entre analyses
ADX_SEUIL        = 20        # ADX < 20 = range = pas de trade
VOLUME_MINI      = 0.50      # Volume > 50% moyenne 24h
SCORE_MIN        = 10        # Score minimum 10/30

# Kill Switch
MAX_PERTES_CONSECUTIVES = 3   # Arrêt 24h après 3 pertes d'affilée
SEUIL_RUINE             = 0.50 # Arrêt total si capital < 50% initial

# Marchés - BTC et ETH uniquement
MARCHES = ["BTCUSDT", "ETHUSDT"]

KRAKEN_SYMBOLS = {
    "BTCUSDT": "XXBTZUSD",
    "ETHUSDT": "XETHZUSD"
}

print("=" * 55)
print("  BOT ULTIME V4")
print(f"  Capital    : {CAPITAL_INITIAL}EUR")
print(f"  Risque/trade: {RISQUE_PAR_TRADE*100}% du capital")
print(f"  ATR x{ATR_MULTIPLIER} | Ratio 1:{int(RATIO_RR)}")
print(f"  Kelly {KELLY_FRACTION*100}% | Cap {KELLY_CAP*100}%")
print(f"  Kill Switch: {MAX_PERTES_CONSECUTIVES} pertes → arrêt 24h")
print(f"  Seuil ruine: -{(1-SEUIL_RUINE)*100}% capital")
print(f"  Marches    : {', '.join(MARCHES)}")
print("=" * 55)

# ══════════════════════════════════════════════════════════════
# RÉCUPÉRATION DES DONNÉES VIA KRAKEN
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

def get_klines(symbole, limite=100):
    """Bougies H1 via Kraken"""
    kraken_symbol = KRAKEN_SYMBOLS.get(symbole, symbole)
    url = "https://api.kraken.com/0/public/OHLC"
    params = {"pair": kraken_symbol, "interval": 60}  # H1
    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        errors = data.get("error", [])
        if errors:
            return None, None, None, None
        result = data.get("result", {})
        keys = [k for k in result.keys() if k != "last"]
        if not keys:
            return None, None, None, None
        candles = result[keys[0]]
        closes  = [float(k[4]) for k in candles]
        highs   = [float(k[2]) for k in candles]
        lows    = [float(k[3]) for k in candles]
        volumes = [float(k[6]) for k in candles]
        return closes[-limite:], highs[-limite:], lows[-limite:], volumes[-limite:]
    except Exception as e:
        print(f"  Erreur klines {symbole} : {e}")
        return None, None, None, None

# ══════════════════════════════════════════════════════════════
# INDICATEUR 1 — ATR (méthode Wilder)
# ══════════════════════════════════════════════════════════════

def calculer_atr(highs, lows, closes, periode=14):
    """
    ATR avec méthode Wilder (EMA exponentielle).
    Plus précis que la moyenne simple.
    """
    if len(closes) < periode + 1:
        return 0

    tr_list = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        tr_list.append(tr)

    # EMA avec alpha = 1/periode (méthode Wilder)
    atr = tr_list[0]
    alpha = 1 / periode
    for tr in tr_list[1:]:
        atr = alpha * tr + (1 - alpha) * atr

    return round(atr, 8)

# ══════════════════════════════════════════════════════════════
# INDICATEUR 2 — ADX
# ══════════════════════════════════════════════════════════════

def calculer_adx(highs, lows, closes, periode=14):
    if len(closes) < periode * 2:
        return 0
    tr_list, plus_dm, minus_dm = [], [], []
    for i in range(1, len(closes)):
        high_diff = highs[i] - highs[i-1]
        low_diff  = lows[i-1] - lows[i]
        tr = max(highs[i] - lows[i],
                 abs(highs[i] - closes[i-1]),
                 abs(lows[i] - closes[i-1]))
        tr_list.append(tr)
        plus_dm.append(high_diff if high_diff > low_diff and high_diff > 0 else 0)
        minus_dm.append(low_diff if low_diff > high_diff and low_diff > 0 else 0)

    def smooth(data, p):
        result = [sum(data[:p])]
        for i in range(p, len(data)):
            result.append(result[-1] - result[-1]/p + data[i])
        return result

    atr  = smooth(tr_list, periode)
    pdi  = smooth(plus_dm, periode)
    mdi  = smooth(minus_dm, periode)

    dx_list = []
    for i in range(len(atr)):
        if atr[i] == 0:
            continue
        pdi_val = 100 * pdi[i] / atr[i]
        mdi_val = 100 * mdi[i] / atr[i]
        if pdi_val + mdi_val == 0:
            continue
        dx = 100 * abs(pdi_val - mdi_val) / (pdi_val + mdi_val)
        dx_list.append(dx)

    if not dx_list:
        return 0
    return round(sum(dx_list[-periode:]) / periode, 2)

# ══════════════════════════════════════════════════════════════
# INDICATEUR 3 — RSI
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

# ══════════════════════════════════════════════════════════════
# INDICATEUR 4 — VOLUME
# ══════════════════════════════════════════════════════════════

def verifier_volume(volumes):
    if len(volumes) < 10:
        return True, 0
    moyenne_24h   = sum(volumes[-24:]) / len(volumes[-24:])  # 24 bougies H1 = 24h
    volume_recent = volumes[-1]
    ratio = volume_recent / moyenne_24h if moyenne_24h > 0 else 0
    suffisant = ratio >= VOLUME_MINI
    return suffisant, round(ratio * 100, 1)

# ══════════════════════════════════════════════════════════════
# STOP DYNAMIQUE ATR + STRUCTURE
# ══════════════════════════════════════════════════════════════

def calculer_stop_dynamique(closes, highs, lows, prix_entree, direction, atr):
    """
    Stop dynamique basé sur ATR + structure du marché.
    Stop ATR = prix_entree ± (ATR × multiplicateur)
    Stop Structure = swing low/high récent
    Stop final = le plus conservateur des deux
    """
    lookback = 10

    if direction == "ACHAT":
        # Stop ATR
        stop_atr = prix_entree - (atr * ATR_MULTIPLIER)
        # Stop structure = swing low récent
        stop_structure = min(lows[-lookback:])
        # On prend le plus bas des deux (protection maximale)
        stop_final = min(stop_atr, stop_structure)
    else:
        # Stop ATR
        stop_atr = prix_entree + (atr * ATR_MULTIPLIER)
        # Stop structure = swing high récent
        stop_structure = max(highs[-lookback:])
        # On prend le plus haut des deux (protection maximale)
        stop_final = max(stop_atr, stop_structure)

    return round(stop_final, 8)

# ══════════════════════════════════════════════════════════════
# KELLY FRACTIONNÉ — Taille de position optimale
# ══════════════════════════════════════════════════════════════

def calculer_kelly(capital, win_rate, avg_win_pct, avg_loss_pct):
    """
    Kelly fractionné à 25% pour calculer la taille optimale.
    Cap à 5% du capital maximum.
    """
    if avg_loss_pct <= 0:
        return capital * 0.01

    b = avg_win_pct / avg_loss_pct
    p = win_rate
    q = 1 - p

    kelly_full = (p * b - q) / b
    kelly_frac = kelly_full * KELLY_FRACTION
    kelly_frac = max(0, min(kelly_frac, KELLY_CAP))

    mise = capital * kelly_frac
    return round(mise, 2)

# ══════════════════════════════════════════════════════════════
# ANALYSE DU MARCHÉ
# ══════════════════════════════════════════════════════════════

def analyser_marche(symbole):
    closes, highs, lows, volumes = get_klines(symbole)
    if closes is None:
        print(f"  {symbole} : Erreur données")
        return 0, "NEUTRE", {}

    # ── ADX ──
    adx = calculer_adx(highs, lows, closes)
    if adx < ADX_SEUIL:
        print(f"  {symbole} : ADX {adx} < {ADX_SEUIL} → RANGE → pas de trade")
        return 0, "NEUTRE", {"adx": adx}

    # ── VOLUME ──
    volume_ok, volume_ratio = verifier_volume(volumes)
    if not volume_ok:
        print(f"  {symbole} : Volume {volume_ratio}% < 50% → pas de trade")
        return 0, "NEUTRE", {"adx": adx}

    # ── ATR ──
    atr = calculer_atr(highs, lows, closes, ATR_PERIODE)

    # ── RSI ──
    rsi = calculer_rsi(closes)
    if rsi < 30:
        score_rsi, direction_rsi = 10, "ACHAT"
    elif rsi < 40:
        score_rsi, direction_rsi = 6,  "ACHAT"
    elif rsi > 70:
        score_rsi, direction_rsi = 10, "VENTE"
    elif rsi > 60:
        score_rsi, direction_rsi = 6,  "VENTE"
    else:
        score_rsi, direction_rsi = 2,  "NEUTRE"

    # ── MA (direction) ──
    ma_courte = sum(closes[-10:]) / 10
    ma_longue = sum(closes[-30:]) / 30
    direction_ma = "ACHAT" if ma_courte > ma_longue else "VENTE"
    ecart_ma = abs(ma_courte - ma_longue) / ma_longue * 100
    if ecart_ma > 1:   score_ma = 10
    elif ecart_ma > 0.5: score_ma = 6
    else:              score_ma = 2

    # ── VOLATILITÉ ATR ──
    atr_pct = (atr / closes[-1]) * 100
    if atr_pct > 2:    score_vol = 10
    elif atr_pct > 1:  score_vol = 6
    elif atr_pct > 0.5: score_vol = 3
    else:              score_vol = 1

    # ── DIRECTION FINALE ──
    # RSI et MA doivent être cohérents
    if direction_rsi == direction_ma and direction_rsi != "NEUTRE":
        direction_finale = direction_rsi
        score_total = score_rsi + score_ma + score_vol
    elif direction_ma != "NEUTRE":
        direction_finale = direction_ma
        score_total = score_ma + score_vol
    else:
        direction_finale = "NEUTRE"
        score_total = 0

    # Bonus ADX fort
    if adx > 25:
        score_total = min(score_total + 3, 30)

    score_total = min(score_total, 30)

    print(f"  {symbole} : ADX {adx} | Vol {volume_ratio}% | "
          f"RSI {rsi} ({direction_rsi}) | MA ({direction_ma}) | "
          f"ATR {round(atr_pct,2)}% | Score {score_total}/30 | {direction_finale}")

    return score_total, direction_finale, {
        "adx": adx,
        "volume_ratio": volume_ratio,
        "rsi": rsi,
        "atr": atr,
        "atr_pct": atr_pct,
        "direction_ma": direction_ma,
        "score_total": score_total,
        "direction": direction_finale,
        "closes": closes,
        "highs": highs,
        "lows": lows
    }

def choisir_meilleur_marche():
    print(f"\n  [{datetime.now().strftime('%H:%M:%S')}] Analyse des marches...")
    resultats = {}

    for marche in MARCHES:
        score, direction, details = analyser_marche(marche)
        resultats[marche] = {"score": score, "direction": direction, "details": details}
        time.sleep(1)

    valides = {k: v for k, v in resultats.items()
               if v["direction"] != "NEUTRE" and v["score"] >= SCORE_MIN}

    if not valides:
        print("  => Aucun signal valide. On attend...")
        return None, "NEUTRE", {}

    # Priorité : meilleur score puis ATR le plus élevé
    meilleur = max(valides, key=lambda x: (
        valides[x]["score"],
        valides[x]["details"].get("atr_pct", 0)
    ))

    direction = valides[meilleur]["direction"]
    score     = valides[meilleur]["score"]
    adx       = valides[meilleur]["details"].get("adx", 0)
    atr_pct   = valides[meilleur]["details"].get("atr_pct", 0)

    print(f"\n  => CHOIX : {meilleur} ({direction})")
    print(f"     Score {score}/30 | ADX {adx} | ATR {round(atr_pct,2)}%")
    return meilleur, direction, valides[meilleur]["details"]

# ══════════════════════════════════════════════════════════════
# SIMULATION DU TRADE
# ══════════════════════════════════════════════════════════════

def simuler_trade(symbole, direction, numero_trade, capital, details, etat):
    prix_entree = get_prix_actuel(symbole)
    if prix_entree is None:
        return "ERREUR", 0, 0

    # ATR et stop dynamique
    atr    = details.get("atr", 0)
    closes = details.get("closes", [])
    highs  = details.get("highs", [])
    lows   = details.get("lows", [])

    stop_loss = calculer_stop_dynamique(closes, highs, lows, prix_entree, direction, atr)

    # Distance au stop
    distance_stop = abs(prix_entree - stop_loss)
    distance_stop_pct = (distance_stop / prix_entree) * 100

    # Objectif = distance stop × ratio R:R
    if direction == "ACHAT":
        prix_objectif = round(prix_entree + (distance_stop * RATIO_RR), 8)
    else:
        prix_objectif = round(prix_entree - (distance_stop * RATIO_RR), 8)

    # Taille de position avec Kelly
    win_rate = etat["nb_wins"] / etat["nb_trades"] if etat["nb_trades"] > 0 else 0.55
    avg_win  = etat["avg_win_pct"] if etat["avg_win_pct"] > 0 else distance_stop_pct * RATIO_RR
    avg_loss = etat["avg_loss_pct"] if etat["avg_loss_pct"] > 0 else distance_stop_pct

    mise = calculer_kelly(capital, win_rate, avg_win, avg_loss)
    mise = max(mise, 5.0)   # minimum 5€ de mise
    mise = min(mise, capital * 0.3)  # maximum 30% du capital

    # Gain et perte potentiels
    gain_potentiel = round(mise * LEVIER * (distance_stop_pct / 100) * RATIO_RR, 2)
    perte_potentielle = round(mise * LEVIER * (distance_stop_pct / 100), 2)

    print(f"\n  {'='*50}")
    print(f"  TRADE #{numero_trade} — {datetime.now().strftime('%H:%M:%S')}")
    print(f"  {'='*50}")
    print(f"  Symbole       : {symbole} ({direction})")
    print(f"  Prix entree   : {prix_entree}")
    print(f"  Stop dynamique: {stop_loss} ({round(distance_stop_pct,2)}%)")
    print(f"  Objectif      : {prix_objectif} (ratio 1:{int(RATIO_RR)})")
    print(f"  Mise Kelly    : {mise}EUR | Levier x{LEVIER}")
    print(f"  Gain potentiel: +{gain_potentiel}EUR")
    print(f"  Perte max     : -{perte_potentielle}EUR\n")

    debut = time.time()

    while True:
        time.sleep(30)

        prix_actuel = get_prix_actuel(symbole)
        if prix_actuel is None:
            continue

        if direction == "ACHAT":
            pnl = round((prix_actuel - prix_entree) / prix_entree * mise * LEVIER, 2)
            atteint_objectif = prix_actuel >= prix_objectif
            atteint_stop     = prix_actuel <= stop_loss
        else:
            pnl = round((prix_entree - prix_actuel) / prix_entree * mise * LEVIER, 2)
            atteint_objectif = prix_actuel <= prix_objectif
            atteint_stop     = prix_actuel >= stop_loss

        heure = datetime.now().strftime("%H:%M:%S")
        duree = int((time.time() - debut) / 60)
        print(f"  [{heure}] {symbole}: {prix_actuel} | "
              f"PnL: {'+' if pnl >= 0 else ''}{pnl}EUR | {duree}min")

        if atteint_objectif:
            print(f"\n  OBJECTIF ATTEINT ! +{pnl}EUR")
            return "GAGNE", pnl, mise

        if atteint_stop:
            print(f"\n  STOP-LOSS ATTEINT ! {pnl}EUR")
            return "PERDU", pnl, mise

        if time.time() - debut > 86400:
            print(f"\n  TIMEOUT 24H — Fermeture : {'+' if pnl >= 0 else ''}{pnl}EUR")
            return ("GAGNE" if pnl > 0 else "PERDU"), pnl, mise

# ══════════════════════════════════════════════════════════════
# KILL SWITCH
# ══════════════════════════════════════════════════════════════

def verifier_kill_switch(etat, capital):
    """
    Kill switch à deux niveaux :
    1. 3 pertes consécutives → arrêt 24h
    2. Capital < 50% initial → arrêt total
    """
    # Seuil de ruine
    if capital < CAPITAL_INITIAL * SEUIL_RUINE:
        print(f"\n  🚨 SEUIL DE RUINE ATTEINT !")
        print(f"  Capital {capital}EUR < {CAPITAL_INITIAL * SEUIL_RUINE}EUR")
        print(f"  BOT ARRÊTÉ DÉFINITIVEMENT")
        return "RUINE"

    # 3 pertes consécutives
    if etat["pertes_consecutives"] >= MAX_PERTES_CONSECUTIVES:
        print(f"\n  ⚠️  KILL SWITCH — {MAX_PERTES_CONSECUTIVES} pertes consécutives !")
        print(f"  Pause de 24h...")
        time.sleep(86400)
        etat["pertes_consecutives"] = 0
        print(f"  Reprise du bot après 24h de pause.")
        return "PAUSE"

    return "OK"

# ══════════════════════════════════════════════════════════════
# GESTION DE L'ÉTAT
# ══════════════════════════════════════════════════════════════

def charger_etat():
    if os.path.exists("etat_bot.json"):
        with open("etat_bot.json", "r") as f:
            return json.load(f)
    return {
        "capital": CAPITAL_INITIAL,
        "total_gagne": 0.0,
        "total_perdu": 0.0,
        "cumul_net": 0.0,
        "nb_trades": 0,
        "nb_wins": 0,
        "nb_losses": 0,
        "nb_skips": 0,
        "pertes_consecutives": 0,
        "avg_win_pct": 0.0,
        "avg_loss_pct": 0.0,
        "historique": []
    }

def sauvegarder_etat(etat):
    with open("etat_bot.json", "w") as f:
        json.dump(etat, f, indent=2, ensure_ascii=False)

def afficher_tableau_de_bord(etat):
    win_rate = (etat["nb_wins"] / etat["nb_trades"] * 100) if etat["nb_trades"] > 0 else 0
    perf = ((etat["capital"] - CAPITAL_INITIAL) / CAPITAL_INITIAL * 100)
    print(f"\n  {'='*55}")
    print(f"  BOT ULTIME V4 — TABLEAU DE BORD")
    print(f"  {'='*55}")
    print(f"  Capital actuel : {round(etat['capital'], 2)}EUR "
          f"({'+' if perf >= 0 else ''}{round(perf, 2)}%)")
    print(f"  Trades total   : {etat['nb_trades']}")
    print(f"  Victoires      : {etat['nb_wins']} ({win_rate:.1f}%)")
    print(f"  Defaites       : {etat['nb_losses']}")
    print(f"  Pertes consec. : {etat['pertes_consecutives']}/{MAX_PERTES_CONSECUTIVES}")
    print(f"  Signaux sautes : {etat['nb_skips']}")
    print(f"  Total gagne    : +{round(etat['total_gagne'], 2)}EUR")
    print(f"  Total perdu    : -{round(etat['total_perdu'], 2)}EUR")
    print(f"  BENEFICE NET   : {'+' if etat['cumul_net'] >= 0 else ''}{round(etat['cumul_net'], 2)}EUR")
    if etat["historique"]:
        print(f"\n  Derniers trades :")
        for h in etat["historique"][-5:]:
            icone = "✅" if h["resultat"] == "GAGNE" else "❌"
            print(f"    {icone} {h['heure']} | {h['marche']} | "
                  f"{h['direction']} | "
                  f"{'+' if h['gain'] >= 0 else ''}{h['gain']}EUR | "
                  f"Capital: {h['capital']}EUR")
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
            # Vérification kill switch
            statut = verifier_kill_switch(etat, etat["capital"])
            if statut == "RUINE":
                break

            # Analyse des marchés
            symbole, direction, details = choisir_meilleur_marche()

            if direction == "NEUTRE" or symbole is None:
                etat["nb_skips"] += 1
                sauvegarder_etat(etat)
                print(f"  Nouvelle analyse dans 2 minutes...")
                time.sleep(PAUSE)
                continue

            # Lancement du trade
            etat["nb_trades"] += 1
            resultat, gain, mise = simuler_trade(
                symbole, direction, etat["nb_trades"],
                etat["capital"], details, etat
            )

            if resultat == "ERREUR":
                etat["nb_trades"] -= 1
                print("  Erreur. Nouvelle tentative dans 2 minutes...")
                time.sleep(PAUSE)
                continue

            # Mise à jour du capital
            etat["capital"] = round(etat["capital"] + gain, 2)
            etat["cumul_net"] = round(etat["capital"] - CAPITAL_INITIAL, 2)

            if resultat == "GAGNE":
                etat["nb_wins"]           += 1
                etat["total_gagne"]        = round(etat["total_gagne"] + gain, 2)
                etat["pertes_consecutives"] = 0
                # Mise à jour moyenne gains
                gain_pct = (gain / (mise * LEVIER)) * 100
                if etat["avg_win_pct"] == 0:
                    etat["avg_win_pct"] = gain_pct
                else:
                    etat["avg_win_pct"] = round(
                        (etat["avg_win_pct"] * (etat["nb_wins"]-1) + gain_pct) / etat["nb_wins"], 4
                    )
            else:
                etat["nb_losses"]          += 1
                etat["total_perdu"]         = round(etat["total_perdu"] + abs(gain), 2)
                etat["pertes_consecutives"] += 1
                # Mise à jour moyenne pertes
                perte_pct = (abs(gain) / (mise * LEVIER)) * 100
                if etat["avg_loss_pct"] == 0:
                    etat["avg_loss_pct"] = perte_pct
                else:
                    etat["avg_loss_pct"] = round(
                        (etat["avg_loss_pct"] * (etat["nb_losses"]-1) + perte_pct) / etat["nb_losses"], 4
                    )

            etat["historique"].append({
                "heure":     datetime.now().strftime("%Y-%m-%d %H:%M"),
                "marche":    symbole,
                "direction": direction,
                "resultat":  resultat,
                "gain":      round(gain, 2),
                "mise":      round(mise, 2),
                "capital":   etat["capital"]
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
