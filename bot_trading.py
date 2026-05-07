"""
╔══════════════════════════════════════════════════════════════╗
║                    BOT ULTIME V4.2                           ║
║     BTC + ETH | H1 | ADX/ATR/RSI pro via ta                 ║
║     Kelly après 30 trades | Score 18/30 | Trailing Stop      ║
║     Pause persistante | Logs fichier | Kill Switch           ║
╚══════════════════════════════════════════════════════════════╝
"""

import requests
import json
import time
import os
import logging
import pandas as pd
from ta.trend import ADXIndicator
from ta.volatility import AverageTrueRange
from ta.momentum import RSIIndicator
from datetime import datetime

# ══════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════

CAPITAL_INITIAL         = 50.0
LEVIER                  = 3
RISQUE_PAR_TRADE        = 0.01      # 1% du capital
ATR_MULTIPLIER          = 2.0       # Stop = ATR × 2
RATIO_RR                = 2.0       # Objectif = Stop × 2
ATR_PERIODE             = 14
KELLY_FRACTION          = 0.25
KELLY_CAP               = 0.05      # Max 5% du capital
MISE_FIXE_PCT           = 0.01      # 1% fixe avant 30 trades
MIN_TRADES_KELLY        = 30        # Trades minimum avant Kelly
PAUSE                   = 120       # 2 min entre analyses
ADX_SEUIL               = 20
VOLUME_MINI             = 0.50
SCORE_MIN               = 18        # 18/30 minimum (60%)
TIMEOUT_TRADE           = 6 * 3600  # 6h max par trade
CHECK_INTERVAL          = 10        # Vérification toutes les 10s
MAX_PERTES_CONSECUTIVES = 3
SEUIL_RUINE             = 0.50      # Arrêt si capital < 50%
PAUSE_DUREE             = 86400     # 24h en secondes

MARCHES = ["BTCUSDT", "ETHUSDT"]

KRAKEN_SYMBOLS = {
    "BTCUSDT": "XXBTZUSD",
    "ETHUSDT": "XETHZUSD"
}

log.info("=" * 55)
log.info("  BOT ULTIME V4.2")
log.info(f"  Capital     : {CAPITAL_INITIAL}EUR")
log.info(f"  Risque/trade: {RISQUE_PAR_TRADE*100}% du capital")
log.info(f"  Kelly apres : {MIN_TRADES_KELLY} trades")
log.info(f"  ATR x{ATR_MULTIPLIER} | Ratio 1:{int(RATIO_RR)}")
log.info(f"  Score min   : {SCORE_MIN}/30")
log.info(f"  Kill Switch : {MAX_PERTES_CONSECUTIVES} pertes → pause 24h")
log.info(f"  Seuil ruine : -{(1-SEUIL_RUINE)*100}% capital")
log.info(f"  Marches     : {', '.join(MARCHES)}")
log.info("=" * 55)

# ══════════════════════════════════════════════════════════════
# RÉCUPÉRATION DES DONNÉES
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
        log.error(f"Erreur prix {symbole} : {e}")
        return None

def get_klines(symbole, limite=100):
    kraken_symbol = KRAKEN_SYMBOLS.get(symbole, symbole)
    url = "https://api.kraken.com/0/public/OHLC"
    params = {"pair": kraken_symbol, "interval": 60}
    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        errors = data.get("error", [])
        if errors:
            return None
        result = data.get("result", {})
        keys = [k for k in result.keys() if k != "last"]
        if not keys:
            return None
        candles = result[keys[0]]
        df = pd.DataFrame(candles, columns=[
            'time', 'open', 'high', 'low', 'close', 'vwap', 'volume', 'count'
        ])
        df = df.astype({'high': float, 'low': float, 'close': float, 'volume': float})
        return df.tail(limite).reset_index(drop=True)
    except Exception as e:
        log.error(f"Erreur klines {symbole} : {e}")
        return None

# ══════════════════════════════════════════════════════════════
# INDICATEURS PROFESSIONNELS via ta
# ══════════════════════════════════════════════════════════════

def calculer_adx(df, periode=14):
    """ADX professionnel via ta (formule Wilder correcte)"""
    try:
        adx_ind = ADXIndicator(
            high=df['high'], low=df['low'], close=df['close'], window=periode
        )
        val = adx_ind.adx().iloc[-1]
        return round(float(val), 2) if not pd.isna(val) else 0
    except Exception as e:
        log.error(f"Erreur ADX : {e}")
        return 0

def calculer_atr(df, periode=14):
    """ATR professionnel via ta"""
    try:
        atr_ind = AverageTrueRange(
            high=df['high'], low=df['low'], close=df['close'], window=periode
        )
        val = atr_ind.average_true_range().iloc[-1]
        return round(float(val), 8) if not pd.isna(val) else 0
    except Exception as e:
        log.error(f"Erreur ATR : {e}")
        return 0

def calculer_rsi(df, periode=14):
    """RSI professionnel via ta"""
    try:
        rsi_ind = RSIIndicator(close=df['close'], window=periode)
        val = rsi_ind.rsi().iloc[-1]
        return round(float(val), 2) if not pd.isna(val) else 50
    except Exception as e:
        log.error(f"Erreur RSI : {e}")
        return 50

def verifier_volume(df):
    volumes = df['volume'].tolist()
    if len(volumes) < 10:
        return True, 0
    moyenne_24h   = sum(volumes[-24:]) / len(volumes[-24:])
    volume_recent = volumes[-1]
    ratio = volume_recent / moyenne_24h if moyenne_24h > 0 else 0
    return ratio >= VOLUME_MINI, round(ratio * 100, 1)

# ══════════════════════════════════════════════════════════════
# STOP DYNAMIQUE ATR + STRUCTURE
# ══════════════════════════════════════════════════════════════

def calculer_stop_dynamique(df, prix_entree, direction, atr):
    lookback  = 10
    highs     = df['high'].tolist()
    lows      = df['low'].tolist()

    if direction == "ACHAT":
        stop_atr       = prix_entree - (atr * ATR_MULTIPLIER)
        stop_structure = min(lows[-lookback:])
        stop_final     = min(stop_atr, stop_structure)
    else:
        stop_atr       = prix_entree + (atr * ATR_MULTIPLIER)
        stop_structure = max(highs[-lookback:])
        stop_final     = max(stop_atr, stop_structure)

    return round(stop_final, 8)

# ══════════════════════════════════════════════════════════════
# KELLY FRACTIONNÉ
# ══════════════════════════════════════════════════════════════

def calculer_mise(capital, nb_trades, win_rate, avg_win_pct, avg_loss_pct):
    """
    Mise fixe 1% les 30 premiers trades.
    Kelly fractionné 25% ensuite.
    """
    if nb_trades < MIN_TRADES_KELLY:
        log.info(f"  Mise fixe 1% (trade {nb_trades}/{MIN_TRADES_KELLY})")
        mise = capital * MISE_FIXE_PCT
    else:
        if avg_loss_pct <= 0:
            mise = capital * MISE_FIXE_PCT
        else:
            b          = avg_win_pct / avg_loss_pct
            p          = win_rate
            q          = 1 - p
            kelly_full = (p * b - q) / b
            kelly_frac = kelly_full * KELLY_FRACTION
            kelly_frac = max(0, min(kelly_frac, KELLY_CAP))
            mise       = capital * kelly_frac
            log.info(f"  Kelly {round(kelly_frac*100,2)}% → mise {round(mise,2)}EUR")

    mise = max(mise, 5.0)
    mise = min(mise, capital * 0.30)
    return round(mise, 2)

# ══════════════════════════════════════════════════════════════
# ANALYSE DU MARCHÉ
# ══════════════════════════════════════════════════════════════

def analyser_marche(symbole):
    df = get_klines(symbole)
    if df is None or len(df) < 30:
        log.warning(f"  {symbole} : données insuffisantes")
        return 0, "NEUTRE", {}

    # ADX
    adx = calculer_adx(df)
    if adx < ADX_SEUIL:
        log.info(f"  {symbole} : ADX {adx} < {ADX_SEUIL} → RANGE → pas de trade")
        return 0, "NEUTRE", {"adx": adx}

    # Volume
    volume_ok, volume_ratio = verifier_volume(df)
    if not volume_ok:
        log.info(f"  {symbole} : Volume {volume_ratio}% < 50% → pas de trade")
        return 0, "NEUTRE", {"adx": adx}

    # ATR et RSI
    atr     = calculer_atr(df)
    rsi     = calculer_rsi(df)
    closes  = df['close'].tolist()
    atr_pct = (atr / closes[-1]) * 100 if closes[-1] > 0 else 0

    # Score RSI
    if rsi < 30:   score_rsi, direction_rsi = 10, "ACHAT"
    elif rsi < 40: score_rsi, direction_rsi = 6,  "ACHAT"
    elif rsi > 70: score_rsi, direction_rsi = 10, "VENTE"
    elif rsi > 60: score_rsi, direction_rsi = 6,  "VENTE"
    else:          score_rsi, direction_rsi = 2,  "NEUTRE"

    # Moyenne Mobile
    ma_courte    = sum(closes[-10:]) / 10
    ma_longue    = sum(closes[-30:]) / 30
    direction_ma = "ACHAT" if ma_courte > ma_longue else "VENTE"
    ecart_ma     = abs(ma_courte - ma_longue) / ma_longue * 100
    if ecart_ma > 1:     score_ma = 10
    elif ecart_ma > 0.5: score_ma = 6
    else:                score_ma = 2

    # Score volatilité ATR
    if atr_pct > 2:     score_vol = 10
    elif atr_pct > 1:   score_vol = 6
    elif atr_pct > 0.5: score_vol = 3
    else:               score_vol = 1

    # Direction finale — RSI ET MA doivent être d'accord
    if direction_rsi == direction_ma and direction_rsi != "NEUTRE":
        direction_finale = direction_rsi
        score_total      = score_rsi + score_ma + score_vol
    elif direction_ma != "NEUTRE":
        direction_finale = direction_ma
        score_total      = score_ma + score_vol
    else:
        direction_finale = "NEUTRE"
        score_total      = 0

    # Bonus ADX fort
    if adx > 25:
        score_total = min(score_total + 3, 30)
    score_total = min(score_total, 30)

    log.info(f"  {symbole} : ADX {adx} | Vol {volume_ratio}% | "
             f"RSI {rsi} ({direction_rsi}) | MA ({direction_ma}) | "
             f"ATR {round(atr_pct,2)}% | Score {score_total}/30 | {direction_finale}")

    return score_total, direction_finale, {
        "adx": adx, "volume_ratio": volume_ratio,
        "rsi": rsi, "atr": atr, "atr_pct": atr_pct,
        "score_total": score_total, "direction": direction_finale,
        "df": df
    }

def choisir_meilleur_marche():
    log.info(f"[{datetime.now().strftime('%H:%M:%S')}] Analyse des marches...")
    resultats = {}

    for marche in MARCHES:
        score, direction, details = analyser_marche(marche)
        resultats[marche] = {"score": score, "direction": direction, "details": details}
        time.sleep(1)

    valides = {k: v for k, v in resultats.items()
               if v["direction"] != "NEUTRE" and v["score"] >= SCORE_MIN}

    if not valides:
        log.info("  => Aucun signal valide. On attend...")
        return None, "NEUTRE", {}

    meilleur  = max(valides, key=lambda x: (
        valides[x]["score"],
        valides[x]["details"].get("atr_pct", 0)
    ))
    direction = valides[meilleur]["direction"]
    score     = valides[meilleur]["score"]
    adx       = valides[meilleur]["details"].get("adx", 0)
    atr_pct   = valides[meilleur]["details"].get("atr_pct", 0)

    log.info(f"  => CHOIX : {meilleur} ({direction})")
    log.info(f"     Score {score}/30 | ADX {adx} | ATR {round(atr_pct,2)}%")
    return meilleur, direction, valides[meilleur]["details"]

# ══════════════════════════════════════════════════════════════
# SIMULATION DU TRADE
# ══════════════════════════════════════════════════════════════

def simuler_trade(symbole, direction, numero_trade, capital, details, etat):
    prix_entree = get_prix_actuel(symbole)
    if prix_entree is None:
        return "ERREUR", 0, 0

    df  = details.get("df")
    atr = details.get("atr", 0)

    # Stop dynamique ATR + Structure
    stop_loss         = calculer_stop_dynamique(df, prix_entree, direction, atr)
    distance_stop     = abs(prix_entree - stop_loss)
    distance_stop_pct = (distance_stop / prix_entree) * 100

    # Objectif ratio 1:2
    if direction == "ACHAT":
        prix_objectif = round(prix_entree + (distance_stop * RATIO_RR), 8)
    else:
        prix_objectif = round(prix_entree - (distance_stop * RATIO_RR), 8)

    # Taille de position
    win_rate = etat["nb_wins"] / etat["nb_trades"] if etat["nb_trades"] > 0 else 0.50
    avg_win  = etat["avg_win_pct"] if etat["avg_win_pct"] > 0 else distance_stop_pct * RATIO_RR
    avg_loss = etat["avg_loss_pct"] if etat["avg_loss_pct"] > 0 else distance_stop_pct

    mise              = calculer_mise(capital, etat["nb_trades"], win_rate, avg_win, avg_loss)
    gain_potentiel    = round(mise * LEVIER * (distance_stop_pct / 100) * RATIO_RR, 2)
    perte_potentielle = round(mise * LEVIER * (distance_stop_pct / 100), 2)

    log.info(f"\n  {'='*50}")
    log.info(f"  TRADE #{numero_trade} — {datetime.now().strftime('%H:%M:%S')}")
    log.info(f"  {'='*50}")
    log.info(f"  Symbole        : {symbole} ({direction})")
    log.info(f"  Prix entree    : {prix_entree}")
    log.info(f"  Stop initial   : {stop_loss} ({round(distance_stop_pct,2)}%)")
    log.info(f"  Objectif       : {prix_objectif} (ratio 1:{int(RATIO_RR)})")
    log.info(f"  Mise           : {mise}EUR | Levier x{LEVIER}")
    log.info(f"  Gain potentiel : +{gain_potentiel}EUR")
    log.info(f"  Perte max      : -{perte_potentielle}EUR\n")

    debut         = time.time()
    stop_actuel   = stop_loss
    meilleur_prix = prix_entree
    dernier_log   = 0

    while True:
        time.sleep(CHECK_INTERVAL)

        prix_actuel = get_prix_actuel(symbole)
        if prix_actuel is None:
            continue

        # Trailing Stop
        if direction == "ACHAT":
            if prix_actuel > meilleur_prix:
                meilleur_prix = prix_actuel
                nouveau_stop  = round(meilleur_prix - distance_stop, 8)
                if nouveau_stop > stop_actuel:
                    stop_actuel = nouveau_stop
            pnl              = round((prix_actuel - prix_entree) / prix_entree * mise * LEVIER, 2)
            atteint_objectif = prix_actuel >= prix_objectif
            atteint_stop     = prix_actuel <= stop_actuel
        else:
            if prix_actuel < meilleur_prix:
                meilleur_prix = prix_actuel
                nouveau_stop  = round(meilleur_prix + distance_stop, 8)
                if nouveau_stop < stop_actuel:
                    stop_actuel = nouveau_stop
            pnl              = round((prix_entree - prix_actuel) / prix_entree * mise * LEVIER, 2)
            atteint_objectif = prix_actuel <= prix_objectif
            atteint_stop     = prix_actuel >= stop_actuel

        duree = int((time.time() - debut) / 60)

        # Log toutes les minutes
        if time.time() - dernier_log >= 60:
            log.info(f"  [{datetime.now().strftime('%H:%M:%S')}] {symbole}: {prix_actuel} | "
                     f"PnL: {'+' if pnl >= 0 else ''}{pnl}EUR | "
                     f"Stop: {stop_actuel} | {duree}min")
            dernier_log = time.time()

        if atteint_objectif:
            log.info(f"\n  OBJECTIF ATTEINT ! +{pnl}EUR")
            return "GAGNE", pnl, mise

        if atteint_stop:
            log.info(f"\n  STOP-LOSS ATTEINT ! {pnl}EUR")
            return "PERDU", pnl, mise

        if time.time() - debut >= TIMEOUT_TRADE:
            log.info(f"\n  TIMEOUT {int(TIMEOUT_TRADE/3600)}H — Fermeture : "
                     f"{'+' if pnl >= 0 else ''}{pnl}EUR")
            return ("GAGNE" if pnl > 0 else "PERDU"), pnl, mise

# ══════════════════════════════════════════════════════════════
# KILL SWITCH avec pause persistante
# ══════════════════════════════════════════════════════════════

def verifier_kill_switch(etat, capital):
    # Seuil de ruine
    if capital < CAPITAL_INITIAL * SEUIL_RUINE:
        log.critical(f"SEUIL DE RUINE ATTEINT ! Capital {capital}EUR")
        return "RUINE"

    # Vérification pause active (persistante via timestamp)
    pause_until = etat.get("pause_until", 0)
    if time.time() < pause_until:
        restant = int((pause_until - time.time()) / 60)
        log.info(f"  En pause après pertes — {restant} minutes restantes")
        time.sleep(60)
        return "PAUSE"

    # 3 pertes consécutives → pause 24h persistante
    if etat["pertes_consecutives"] >= MAX_PERTES_CONSECUTIVES:
        log.warning(f"KILL SWITCH — {MAX_PERTES_CONSECUTIVES} pertes consecutives !")
        log.warning(f"Pause 24h enregistrée dans etat_bot.json")
        etat["pause_until"]          = time.time() + PAUSE_DUREE
        etat["pertes_consecutives"]  = 0
        sauvegarder_etat(etat)
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
        "total_gagne": 0.0, "total_perdu": 0.0,
        "cumul_net": 0.0, "nb_trades": 0,
        "nb_wins": 0, "nb_losses": 0,
        "nb_skips": 0, "pertes_consecutives": 0,
        "avg_win_pct": 0.0, "avg_loss_pct": 0.0,
        "pause_until": 0,
        "historique": []
    }

def sauvegarder_etat(etat):
    etat_a_sauver = {k: v for k, v in etat.items() if k != "df"}
    with open("etat_bot.json", "w") as f:
        json.dump(etat_a_sauver, f, indent=2, ensure_ascii=False)

def afficher_tableau_de_bord(etat):
    win_rate = (etat["nb_wins"] / etat["nb_trades"] * 100) if etat["nb_trades"] > 0 else 0
    perf     = ((etat["capital"] - CAPITAL_INITIAL) / CAPITAL_INITIAL * 100)
    log.info(f"\n  {'='*55}")
    log.info(f"  BOT ULTIME V4.2 — TABLEAU DE BORD")
    log.info(f"  {'='*55}")
    log.info(f"  Capital actuel : {round(etat['capital'], 2)}EUR "
             f"({'+' if perf >= 0 else ''}{round(perf, 2)}%)")
    log.info(f"  Trades total   : {etat['nb_trades']}")
    log.info(f"  Victoires      : {etat['nb_wins']} ({win_rate:.1f}%)")
    log.info(f"  Defaites       : {etat['nb_losses']}")
    log.info(f"  Pertes consec. : {etat['pertes_consecutives']}/{MAX_PERTES_CONSECUTIVES}")
    log.info(f"  Kelly actif    : {'Non (< 30 trades)' if etat['nb_trades'] < MIN_TRADES_KELLY else 'Oui'}")
    log.info(f"  Total gagne    : +{round(etat['total_gagne'], 2)}EUR")
    log.info(f"  Total perdu    : -{round(etat['total_perdu'], 2)}EUR")
    log.info(f"  BENEFICE NET   : {'+' if etat['cumul_net'] >= 0 else ''}{round(etat['cumul_net'], 2)}EUR")
    if etat["historique"]:
        log.info(f"\n  Derniers trades :")
        for h in etat["historique"][-5:]:
            icone = "OK" if h["resultat"] == "GAGNE" else "XX"
            log.info(f"    [{icone}] {h['heure']} | {h['marche']} | "
                     f"{h['direction']} | "
                     f"{'+' if h['gain'] >= 0 else ''}{h['gain']}EUR | "
                     f"Capital: {h['capital']}EUR")
    log.info(f"  {'='*55}")

# ══════════════════════════════════════════════════════════════
# BOUCLE PRINCIPALE
# ══════════════════════════════════════════════════════════════

def demarrer_bot():
    log.info(f"DEMARRAGE — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    etat = charger_etat()
    afficher_tableau_de_bord(etat)

    while True:
        try:
            statut = verifier_kill_switch(etat, etat["capital"])
            if statut == "RUINE":
                break
            if statut == "PAUSE":
                continue

            symbole, direction, details = choisir_meilleur_marche()

            if direction == "NEUTRE" or symbole is None:
                etat["nb_skips"] += 1
                sauvegarder_etat(etat)
                log.info(f"  Nouvelle analyse dans 2 minutes...")
                time.sleep(PAUSE)
                continue

            etat["nb_trades"] += 1
            resultat, gain, mise = simuler_trade(
                symbole, direction, etat["nb_trades"],
                etat["capital"], details, etat
            )

            if resultat == "ERREUR":
                etat["nb_trades"] -= 1
                time.sleep(PAUSE)
                continue

            etat["capital"]   = round(etat["capital"] + gain, 2)
            etat["cumul_net"] = round(etat["capital"] - CAPITAL_INITIAL, 2)

            if resultat == "GAGNE":
                etat["nb_wins"]            += 1
                etat["total_gagne"]         = round(etat["total_gagne"] + gain, 2)
                etat["pertes_consecutives"] = 0
                gain_pct = (gain / max(mise * LEVIER, 1)) * 100
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
                perte_pct = (abs(gain) / max(mise * LEVIER, 1)) * 100
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

            log.info(f"  Pause 2 minutes avant prochain trade...")
            time.sleep(PAUSE)

        except KeyboardInterrupt:
            log.info("Bot arrete.")
            break
        except Exception as e:
            log.error(f"Erreur : {e}")
            time.sleep(60)

if __name__ == "__main__":
    demarrer_bot()
