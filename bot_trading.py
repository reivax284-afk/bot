"""
╔══════════════════════════════════════════════════════════════╗
║                    BOT ULTIME V5 — DONCHIAN                  ║
║         Stratégie Turtle Traders (55/20)                     ║
║         BTC + ETH | H1 | ATR Stop | Kelly 25%               ║
║         PostgreSQL Railway | Kill Switch                      ║
╚══════════════════════════════════════════════════════════════╝

STRATÉGIE DONCHIAN 55/20 :
- ACHAT  : prix dépasse le plus haut des 55 dernières bougies
- VENTE  : prix dépasse le plus bas des 55 dernières bougies
- SORTIE : prix dépasse le plus haut/bas des 20 dernières bougies
- STOP   : ATR × 2 (protection contre les faux breakouts)
- FILTRE : ADX > 20 (on ne trade qu'en tendance)
- FILTRE : Volume > 50% moyenne (liquidité confirmée)
"""

import requests
import json
import time
import os
import logging
import pandas as pd
from ta.trend import ADXIndicator
from ta.volatility import AverageTrueRange
from datetime import datetime
from database import init_database, charger_etat, sauvegarder_etat, enregistrer_trade

# ══════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════

CAPITAL_INITIAL         = 50.0
LEVIER                  = 3
MISE_FIXE_PCT           = 0.01      # 1% fixe avant 30 trades
KELLY_FRACTION          = 0.25      # Kelly 25% après 30 trades
KELLY_CAP               = 0.05      # Max 5% du capital
MIN_TRADES_KELLY        = 30
ATR_MULTIPLIER          = 2.0       # Stop = ATR × 2
PAUSE                   = 120       # 2 min entre analyses
CHECK_INTERVAL          = 10        # Vérification toutes les 10s
TIMEOUT_TRADE           = 24 * 3600 # 24h max (Donchian = swing)
ADX_SEUIL               = 20
VOLUME_MINI             = 0.50

# Paramètres Donchian
DONCHIAN_ENTREE         = 55        # Plus haut/bas sur 55 bougies
DONCHIAN_SORTIE         = 20        # Sortie sur 20 bougies

# Kill Switch
MAX_PERTES_CONSECUTIVES = 3
SEUIL_RUINE             = 0.50
PAUSE_DUREE             = 86400

MARCHES = ["BTCUSDT", "ETHUSDT"]
KRAKEN_SYMBOLS = {
    "BTCUSDT": "XXBTZUSD",
    "ETHUSDT": "XETHZUSD"
}

log.info("=" * 55)
log.info("  BOT ULTIME V5 — STRATÉGIE DONCHIAN (TURTLES)")
log.info(f"  Capital      : {CAPITAL_INITIAL}EUR")
log.info(f"  Donchian     : Entrée {DONCHIAN_ENTREE}j | Sortie {DONCHIAN_SORTIE}j")
log.info(f"  Stop         : ATR × {ATR_MULTIPLIER}")
log.info(f"  Kelly        : {KELLY_FRACTION*100}% après {MIN_TRADES_KELLY} trades")
log.info(f"  Kill Switch  : {MAX_PERTES_CONSECUTIVES} pertes → pause 24h")
log.info(f"  Seuil ruine  : -{(1-SEUIL_RUINE)*100}% capital")
log.info(f"  Marches      : {', '.join(MARCHES)}")
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
            'time','open','high','low','close','vwap','volume','count'
        ])
        df = df.astype({
            'high': float, 'low': float,
            'close': float, 'volume': float
        })
        return df.tail(limite).reset_index(drop=True)
    except Exception as e:
        log.error(f"Erreur klines {symbole} : {e}")
        return None

# ══════════════════════════════════════════════════════════════
# INDICATEURS
# ══════════════════════════════════════════════════════════════

def calculer_adx(df, periode=14):
    try:
        ind = ADXIndicator(
            high=df['high'], low=df['low'],
            close=df['close'], window=periode
        )
        val = ind.adx().iloc[-1]
        return round(float(val), 2) if not pd.isna(val) else 0
    except:
        return 0

def calculer_atr(df, periode=14):
    try:
        ind = AverageTrueRange(
            high=df['high'], low=df['low'],
            close=df['close'], window=periode
        )
        val = ind.average_true_range().iloc[-1]
        return round(float(val), 8) if not pd.isna(val) else 0
    except:
        return 0

def verifier_volume(df):
    volumes = df['volume'].tolist()
    if len(volumes) < 10:
        return True, 0
    moyenne_24h   = sum(volumes[-24:]) / len(volumes[-24:])
    volume_recent = volumes[-1]
    ratio = volume_recent / moyenne_24h if moyenne_24h > 0 else 0
    return ratio >= VOLUME_MINI, round(ratio * 100, 1)

# ══════════════════════════════════════════════════════════════
# STRATÉGIE DONCHIAN 55/20
# ══════════════════════════════════════════════════════════════

def analyser_donchian(symbole):
    """
    Stratégie Turtle Traders :
    - ACHAT  : clôture > plus haut des 55 dernières bougies
    - VENTE  : clôture < plus bas des 55 dernières bougies
    - Filtres : ADX > 20 + Volume > 50%
    """
    df = get_klines(symbole, limite=100)
    if df is None or len(df) < DONCHIAN_ENTREE + 5:
        log.warning(f"  {symbole} : données insuffisantes")
        return "NEUTRE", {}

    # Filtres
    adx = calculer_adx(df)
    if adx < ADX_SEUIL:
        log.info(f"  {symbole} : ADX {adx} < {ADX_SEUIL} → RANGE → pas de trade")
        return "NEUTRE", {"adx": adx}

    volume_ok, volume_ratio = verifier_volume(df)
    if not volume_ok:
        log.info(f"  {symbole} : Volume {volume_ratio}% < 50% → pas de trade")
        return "NEUTRE", {"adx": adx}

    # Calcul Donchian
    atr          = calculer_atr(df)
    prix_actuel  = df['close'].iloc[-1]

    # Plus haut et plus bas sur 55 bougies (sans la dernière)
    plus_haut_55 = df['high'].iloc[-DONCHIAN_ENTREE-1:-1].max()
    plus_bas_55  = df['low'].iloc[-DONCHIAN_ENTREE-1:-1].min()

    # Niveaux de sortie sur 20 bougies
    sortie_haut  = df['high'].iloc[-DONCHIAN_SORTIE-1:-1].max()
    sortie_bas   = df['low'].iloc[-DONCHIAN_SORTIE-1:-1].min()

    atr_pct = (atr / prix_actuel) * 100

    log.info(f"  {symbole} : ADX {adx} | Vol {volume_ratio}% | "
             f"Prix {round(prix_actuel,4)} | "
             f"H55 {round(plus_haut_55,4)} | B55 {round(plus_bas_55,4)} | "
             f"ATR {round(atr_pct,2)}%")

    details = {
        "adx": adx,
        "volume_ratio": volume_ratio,
        "atr": atr,
        "atr_pct": atr_pct,
        "plus_haut_55": plus_haut_55,
        "plus_bas_55": plus_bas_55,
        "sortie_haut": sortie_haut,
        "sortie_bas": sortie_bas,
        "prix_actuel": prix_actuel,
        "df": df
    }

    # Signal Donchian
    if prix_actuel > plus_haut_55:
        log.info(f"  {symbole} : BREAKOUT HAUSSIER ! "
                 f"{round(prix_actuel,4)} > H55 {round(plus_haut_55,4)} → ACHAT")
        return "ACHAT", details

    elif prix_actuel < plus_bas_55:
        log.info(f"  {symbole} : BREAKOUT BAISSIER ! "
                 f"{round(prix_actuel,4)} < B55 {round(plus_bas_55,4)} → VENTE")
        return "VENTE", details

    else:
        log.info(f"  {symbole} : Prix dans le canal Donchian → pas de signal")
        return "NEUTRE", details

def choisir_meilleur_marche():
    log.info(f"\n[{datetime.now().strftime('%H:%M:%S')}] Analyse Donchian des marches...")
    signaux = {}

    for marche in MARCHES:
        direction, details = analyser_donchian(marche)
        if direction != "NEUTRE":
            signaux[marche] = {"direction": direction, "details": details}
        time.sleep(1)

    if not signaux:
        log.info("  => Aucun breakout Donchian. On attend...")
        return None, "NEUTRE", {}

    # Priorité : ATR le plus élevé (mouvement le plus fort)
    meilleur  = max(signaux, key=lambda x: signaux[x]["details"].get("atr_pct", 0))
    direction = signaux[meilleur]["direction"]
    atr_pct   = signaux[meilleur]["details"].get("atr_pct", 0)
    adx       = signaux[meilleur]["details"].get("adx", 0)

    log.info(f"\n  => BREAKOUT : {meilleur} ({direction})")
    log.info(f"     ADX {adx} | ATR {round(atr_pct,2)}%")
    return meilleur, direction, signaux[meilleur]["details"]

# ══════════════════════════════════════════════════════════════
# KELLY FRACTIONNÉ
# ══════════════════════════════════════════════════════════════

def calculer_mise(capital, nb_trades, win_rate, avg_win_pct, avg_loss_pct):
    if nb_trades < MIN_TRADES_KELLY:
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
    mise = max(mise, 5.0)
    mise = min(mise, capital * 0.30)
    return round(mise, 2)

# ══════════════════════════════════════════════════════════════
# SIMULATION DU TRADE DONCHIAN
# ══════════════════════════════════════════════════════════════

def simuler_trade(symbole, direction, numero_trade, capital, details, etat):
    prix_entree = get_prix_actuel(symbole)
    if prix_entree is None:
        return "ERREUR", 0, 0, {}

    atr         = details.get("atr", 0)
    sortie_haut = details.get("sortie_haut", 0)
    sortie_bas  = details.get("sortie_bas", 0)

    # Stop ATR × 2
    if direction == "ACHAT":
        stop_loss     = round(prix_entree - (atr * ATR_MULTIPLIER), 8)
        prix_sortie_d = sortie_bas   # Sortie Donchian si prix < plus bas 20
    else:
        stop_loss     = round(prix_entree + (atr * ATR_MULTIPLIER), 8)
        prix_sortie_d = sortie_haut  # Sortie Donchian si prix > plus haut 20

    distance_stop     = abs(prix_entree - stop_loss)
    distance_stop_pct = (distance_stop / prix_entree) * 100

    win_rate = etat["nb_wins"] / etat["nb_trades"] if etat["nb_trades"] > 0 else 0.50
    avg_win  = etat["avg_win_pct"] if etat["avg_win_pct"] > 0 else distance_stop_pct * 2
    avg_loss = etat["avg_loss_pct"] if etat["avg_loss_pct"] > 0 else distance_stop_pct
    mise     = calculer_mise(capital, etat["nb_trades"], win_rate, avg_win, avg_loss)

    log.info(f"\n  {'='*50}")
    log.info(f"  TRADE #{numero_trade} — {datetime.now().strftime('%H:%M:%S')}")
    log.info(f"  {'='*50}")
    log.info(f"  Symbole        : {symbole} ({direction})")
    log.info(f"  Prix entree    : {prix_entree}")
    log.info(f"  Stop ATR×2     : {stop_loss} ({round(distance_stop_pct,2)}%)")
    log.info(f"  Sortie Donchian: {prix_sortie_d} (plus haut/bas 20j)")
    log.info(f"  Mise           : {mise}EUR | Levier x{LEVIER}")
    log.info(f"  Timeout        : 24h\n")

    debut         = time.time()
    stop_actuel   = stop_loss
    meilleur_prix = prix_entree
    dernier_log   = 0
    prix_cloture  = prix_entree

    while True:
        time.sleep(CHECK_INTERVAL)

        prix_actuel = get_prix_actuel(symbole)
        if prix_actuel is None:
            continue

        prix_cloture = prix_actuel

        # Trailing Stop Donchian
        if direction == "ACHAT":
            if prix_actuel > meilleur_prix:
                meilleur_prix = prix_actuel
                nouveau_stop  = round(meilleur_prix - distance_stop, 8)
                if nouveau_stop > stop_actuel:
                    stop_actuel = nouveau_stop
            pnl          = round((prix_actuel - prix_entree) / prix_entree * mise * LEVIER, 2)
            sortie_don   = prix_actuel < prix_sortie_d  # Sortie si prix < bas 20j
            atteint_stop = prix_actuel <= stop_actuel
        else:
            if prix_actuel < meilleur_prix:
                meilleur_prix = prix_actuel
                nouveau_stop  = round(meilleur_prix + distance_stop, 8)
                if nouveau_stop < stop_actuel:
                    stop_actuel = nouveau_stop
            pnl          = round((prix_entree - prix_actuel) / prix_entree * mise * LEVIER, 2)
            sortie_don   = prix_actuel > prix_sortie_d  # Sortie si prix > haut 20j
            atteint_stop = prix_actuel >= stop_actuel

        duree = int((time.time() - debut) / 60)

        if time.time() - dernier_log >= 60:
            log.info(f"  [{datetime.now().strftime('%H:%M:%S')}] {symbole}: {prix_actuel} | "
                     f"PnL: {'+' if pnl >= 0 else ''}{pnl}EUR | "
                     f"Stop: {stop_actuel} | {duree}min")
            dernier_log = time.time()

        trade_info = {
            "prix_entree":   prix_entree,
            "prix_sortie":   prix_cloture,
            "stop_loss":     stop_loss,
            "objectif":      prix_sortie_d,
            "duree_minutes": duree
        }

        # Sortie Donchian (signal de retournement)
        if sortie_don:
            log.info(f"\n  SORTIE DONCHIAN ! {'+' if pnl >= 0 else ''}{pnl}EUR")
            return ("GAGNE" if pnl > 0 else "PERDU"), pnl, mise, trade_info

        # Stop-loss ATR
        if atteint_stop:
            log.info(f"\n  STOP-LOSS ATR ! {pnl}EUR")
            return "PERDU", pnl, mise, trade_info

        # Timeout 24h
        if time.time() - debut >= TIMEOUT_TRADE:
            log.info(f"\n  TIMEOUT 24H — Fermeture : {'+' if pnl >= 0 else ''}{pnl}EUR")
            return ("GAGNE" if pnl > 0 else "PERDU"), pnl, mise, trade_info

# ══════════════════════════════════════════════════════════════
# KILL SWITCH
# ══════════════════════════════════════════════════════════════

def verifier_kill_switch(etat, capital):
    if capital < CAPITAL_INITIAL * SEUIL_RUINE:
        log.critical(f"SEUIL DE RUINE ! Capital {capital}EUR")
        return "RUINE"

    pause_until = etat.get("pause_until", 0)
    if time.time() < pause_until:
        restant = int((pause_until - time.time()) / 60)
        log.info(f"  En pause — {restant} minutes restantes")
        time.sleep(60)
        return "PAUSE"

    if etat["pertes_consecutives"] >= MAX_PERTES_CONSECUTIVES:
        log.warning(f"KILL SWITCH — {MAX_PERTES_CONSECUTIVES} pertes consecutives !")
        etat["pause_until"]         = int(time.time()) + PAUSE_DUREE
        etat["pertes_consecutives"] = 0
        sauvegarder_etat(etat)
        return "PAUSE"

    return "OK"

# ══════════════════════════════════════════════════════════════
# TABLEAU DE BORD
# ══════════════════════════════════════════════════════════════

def afficher_tableau_de_bord(etat):
    win_rate = (etat["nb_wins"] / etat["nb_trades"] * 100) if etat["nb_trades"] > 0 else 0
    perf     = ((etat["capital"] - CAPITAL_INITIAL) / CAPITAL_INITIAL * 100)
    log.info(f"\n  {'='*55}")
    log.info(f"  BOT V5 DONCHIAN — TABLEAU DE BORD")
    log.info(f"  {'='*55}")
    log.info(f"  Capital actuel : {round(etat['capital'],2)}EUR "
             f"({'+' if perf >= 0 else ''}{round(perf,2)}%)")
    log.info(f"  Trades total   : {etat['nb_trades']}")
    log.info(f"  Victoires      : {etat['nb_wins']} ({win_rate:.1f}%)")
    log.info(f"  Defaites       : {etat['nb_losses']}")
    log.info(f"  Pertes consec. : {etat['pertes_consecutives']}/{MAX_PERTES_CONSECUTIVES}")
    log.info(f"  Total gagne    : +{round(etat['total_gagne'],2)}EUR")
    log.info(f"  Total perdu    : -{round(etat['total_perdu'],2)}EUR")
    log.info(f"  BENEFICE NET   : {'+' if etat['cumul_net'] >= 0 else ''}{round(etat['cumul_net'],2)}EUR")
    if etat.get("historique"):
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
    log.info(f"DEMARRAGE BOT V5 DONCHIAN — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    init_database()
    etat = charger_etat()
    afficher_tableau_de_bord(etat)

    while True:
        try:
            statut = verifier_kill_switch(etat, etat["capital"])
            if statut == "RUINE":
                break
            if statut == "PAUSE":
                etat = charger_etat()
                continue

            symbole, direction, details = choisir_meilleur_marche()

            if direction == "NEUTRE" or symbole is None:
                etat["nb_skips"] += 1
                sauvegarder_etat(etat)
                log.info(f"  Nouvelle analyse dans 2 minutes...")
                time.sleep(PAUSE)
                continue

            etat["nb_trades"] += 1
            resultat, gain, mise, trade_info = simuler_trade(
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

            enregistrer_trade({
                'marche':        symbole,
                'direction':     direction,
                'resultat':      resultat,
                'prix_entree':   trade_info['prix_entree'],
                'prix_sortie':   trade_info['prix_sortie'],
                'stop_loss':     trade_info['stop_loss'],
                'objectif':      trade_info['objectif'],
                'mise':          mise,
                'gain':          round(gain, 2),
                'capital_apres': etat['capital'],
                'duree_minutes': trade_info['duree_minutes'],
                'score':         None,
                'adx':           details.get('adx'),
                'atr':           details.get('atr'),
                'rsi':           None,
            })

            sauvegarder_etat(etat)

            etat['historique'].append({
                'heure':     datetime.now().strftime('%Y-%m-%d %H:%M'),
                'marche':    symbole,
                'direction': direction,
                'resultat':  resultat,
                'gain':      round(gain, 2),
                'mise':      round(mise, 2),
                'capital':   etat['capital']
            })

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
