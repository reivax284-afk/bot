"""
╔══════════════════════════════════════════════════════════════╗
║         BACKTESTER COMPARATIF — 3 OPTIONS                    ║
║   A: Levier x10 | Mise 5%                                   ║
║   B: Levier x3  | Mise 20%                                  ║
║   C: Levier x10 | Mise 20%                                  ║
║   10 marchés validés | Mean Reversion RSI                    ║
╚══════════════════════════════════════════════════════════════╝
"""

import requests
import pandas as pd
import time
from ta.trend import ADXIndicator
from ta.volatility import AverageTrueRange
from ta.momentum import RSIIndicator

CAPITAL_INITIAL = 50.0
ATR_MULTIPLIER  = 2.5
RATIO_RR        = 2.0
RATIO_PARTIEL   = 1.0
RSI_ACHAT       = 30
RSI_VENTE       = 70
ADX_MAX         = 40
ADX_MIN         = 10        # ADX minimum — évite les marchés morts
VOLUME_MINI     = 0.40
FRAIS_PCT       = 0.0004
SLIPPAGE_PCT    = 0.0002
TIMEOUT_BOUGIES = 6    # 6h

# 3 options à comparer
OPTIONS = [
    {"nom": "A — Levier x10 | Mise  5%", "levier": 10, "mise_pct": 0.05},
    {"nom": "B — Levier  x3 | Mise 20%", "levier":  3, "mise_pct": 0.20},
    {"nom": "C — Levier x10 | Mise 20%", "levier": 10, "mise_pct": 0.20},
]

MARCHES = [
    "BTCUSDT", "ETHUSDT", "XRPUSDT", "ATOMUSDT", "LINKUSDT",
    "ADAUSDT", "SOLUSDT", "AVAXUSDT", "NEARUSDT", "AAVEUSDT"
]
KRAKEN_SYMBOLS = {
    "BTCUSDT":  "XXBTZUSD", "ETHUSDT":  "XETHZUSD",
    "XRPUSDT":  "XXRPZUSD", "ATOMUSDT": "ATOMUSD",
    "LINKUSDT": "LINKUSD",  "ADAUSDT":  "ADAUSD",
    "SOLUSDT":  "SOLUSD",   "AVAXUSDT": "AVAXUSD",
    "NEARUSDT": "NEARUSD",  "AAVEUSDT": "AAVEUSD"
}

def get_data(symbole):
    kraken_symbol = KRAKEN_SYMBOLS.get(symbole, symbole)
    url    = "https://api.kraken.com/0/public/OHLC"
    params = {"pair": kraken_symbol, "interval": 60}
    try:
        r    = requests.get(url, params=params, timeout=30)
        data = r.json()
        if data.get("error") and data["error"]:
            return None
        result = data.get("result", {})
        keys   = [k for k in result.keys() if k != "last"]
        if not keys:
            return None
        candles = result[keys[0]]
        df = pd.DataFrame(candles, columns=[
            'time','open','high','low','close','vwap','volume','count'
        ])
        df = df.astype({'time': int, 'high': float, 'low': float,
                        'close': float, 'volume': float})
        df['datetime'] = pd.to_datetime(df['time'], unit='s')
        df = df.set_index('datetime').sort_index()
        return df
    except:
        return None

def ajouter_indicateurs(df):
    df = df.copy()
    df['adx'] = ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=14).adx()
    df['atr'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range()
    df['rsi'] = RSIIndicator(close=df['close'], window=14).rsi()
    df['vol_moy']   = df['volume'].rolling(24).mean()
    df['vol_ratio'] = df['volume'] / df['vol_moy']
    return df.dropna()

def backtest(df, levier, mise_pct):
    trades   = []
    capital  = CAPITAL_INITIAL
    i        = 20
    frais    = (FRAIS_PCT + SLIPPAGE_PCT) * 2
    ruine    = False

    while i < len(df) - TIMEOUT_BOUGIES - 2:
        # Vérification seuil de ruine
        if capital < CAPITAL_INITIAL * 0.30:
            ruine = True
            break

        row = df.iloc[i]
        if row['vol_ratio'] < VOLUME_MINI or row['adx'] > ADX_MAX or row['adx'] < ADX_MIN:
            i += 1
            continue

        prix   = row['close']
        atr    = row['atr']
        rsi    = row['rsi']
        signal = None

        if rsi < RSI_ACHAT:
            signal = "ACHAT"
        elif rsi > RSI_VENTE:
            signal = "VENTE"

        if signal is None:
            i += 1
            continue

        mise          = capital * mise_pct
        distance_stop = atr * ATR_MULTIPLIER

        if signal == "ACHAT":
            stop_loss   = prix - distance_stop
            obj_partiel = prix + (distance_stop * RATIO_PARTIEL)
            obj_final   = prix + (distance_stop * RATIO_RR)
        else:
            stop_loss   = prix + distance_stop
            obj_partiel = prix - (distance_stop * RATIO_PARTIEL)
            obj_final   = prix - (distance_stop * RATIO_RR)

        partiel_fait = False
        gain_partiel = 0
        gain_brut    = 0
        resultat     = "NEUTRE"
        duree        = 0

        for j in range(i + 1, min(i + TIMEOUT_BOUGIES + 1, len(df))):
            row_j = df.iloc[j]
            duree = j - i

            if signal == "ACHAT":
                if not partiel_fait and row_j['high'] >= obj_partiel:
                    gain_partiel = (obj_partiel - prix) / prix * mise * levier * 0.5
                    partiel_fait = True
                    stop_loss    = prix
                if row_j['low'] <= stop_loss:
                    gain_reste = (stop_loss - prix) / prix * mise * levier * (0.5 if partiel_fait else 1.0)
                    gain_brut  = gain_partiel + gain_reste
                    resultat   = "GAGNE" if gain_brut > 0 else "PERDU"
                    break
                if row_j['high'] >= obj_final:
                    gain_reste = (obj_final - prix) / prix * mise * levier * 0.5
                    gain_brut  = gain_partiel + gain_reste
                    resultat   = "GAGNE"
                    break
            else:
                if not partiel_fait and row_j['low'] <= obj_partiel:
                    gain_partiel = (prix - obj_partiel) / prix * mise * levier * 0.5
                    partiel_fait = True
                    stop_loss    = prix
                if row_j['high'] >= stop_loss:
                    gain_reste = (prix - stop_loss) / prix * mise * levier * (0.5 if partiel_fait else 1.0)
                    gain_brut  = gain_partiel + gain_reste
                    resultat   = "GAGNE" if gain_brut > 0 else "PERDU"
                    break
                if row_j['low'] <= obj_final:
                    gain_reste = (prix - obj_final) / prix * mise * levier * 0.5
                    gain_brut  = gain_partiel + gain_reste
                    resultat   = "GAGNE"
                    break

        if resultat == "NEUTRE":
            prix_fin  = df.iloc[min(i + TIMEOUT_BOUGIES, len(df)-1)]['close']
            if signal == "ACHAT":
                g = (prix_fin - prix) / prix * mise * levier
            else:
                g = (prix - prix_fin) / prix * mise * levier
            gain_brut = gain_partiel + g * (0.5 if partiel_fait else 1.0)
            resultat  = "GAGNE" if gain_brut > 0 else "PERDU"
            duree     = TIMEOUT_BOUGIES

        gain_net = round(gain_brut - frais * mise * levier, 2)
        capital  = round(capital + gain_net, 2)

        trades.append({
            'resultat': resultat,
            'gain':     gain_net,
            'capital':  capital,
            'duree_h':  duree
        })

        i = i + duree + 2

    return trades, capital, ruine

def analyser(trades, capital_final, ruine, levier, mise_pct):
    if not trades:
        return None

    df_t     = pd.DataFrame(trades)
    nb       = len(trades)
    wins     = len(df_t[df_t['resultat'] == 'GAGNE'])
    win_rate = wins / nb * 100
    gain_tot = df_t['gain'].sum()
    perf     = (capital_final - CAPITAL_INITIAL) / CAPITAL_INITIAL * 100
    avg_win  = df_t[df_t['resultat']=='GAGNE']['gain'].mean() if wins > 0 else 0
    avg_loss = df_t[df_t['resultat']=='PERDU']['gain'].mean() if (nb-wins) > 0 else 0

    # Drawdown
    capitals = [CAPITAL_INITIAL] + [t['capital'] for t in trades]
    peak = CAPITAL_INITIAL
    max_dd = 0
    for c in capitals:
        if c > peak: peak = c
        dd = (c - peak) / peak * 100
        if dd < max_dd: max_dd = dd

    # Projection journalière
    gains_par_jour = gain_tot / 24  # 24 jours de données
    gains_par_semaine = gain_tot / (24/7)

    return {
        'nb_trades': nb,
        'win_rate': round(win_rate, 1),
        'performance': round(perf, 1),
        'gain_total': round(gain_tot, 2),
        'gain_jour': round(gains_par_jour, 2),
        'gain_semaine': round(gains_par_semaine, 2),
        'avg_win': round(avg_win, 2),
        'avg_loss': round(avg_loss, 2),
        'drawdown_max': round(max_dd, 1),
        'capital_final': round(capital_final, 2),
        'ruine': ruine
    }

def main():
    print("=" * 60)
    print("  BACKTESTER COMPARATIF — 3 OPTIONS DE LEVIER/MISE")
    print("  Objectif : trouver la combinaison pour 10€/jour")
    print("=" * 60)

    # Télécharger les données une seule fois
    print("\n  Téléchargement des données...")
    donnees = {}
    for symbole in MARCHES:
        df = get_data(symbole)
        if df is not None and len(df) > 50:
            df = ajouter_indicateurs(df)
            donnees[symbole] = df
            print(f"  ✅ {symbole} — {len(df)} bougies")
        else:
            print(f"  ❌ {symbole} — ignoré")
        time.sleep(0.5)

    # Tester chaque option sur tous les marchés
    resultats_options = []

    for option in OPTIONS:
        print(f"\n  {'='*60}")
        print(f"  TEST : {option['nom']}")
        print(f"  {'='*60}")

        tous_trades    = []
        capital_global = CAPITAL_INITIAL
        ruine_globale  = False

        for symbole, df in donnees.items():
            trades, capital, ruine = backtest(df, option['levier'], option['mise_pct'])
            if trades:
                tous_trades.extend(trades)
                # Calcul gain/perte net sur ce marché
                gain_marche = sum(t['gain'] for t in trades)
                wins_m      = sum(1 for t in trades if t['resultat'] == 'GAGNE')
                wr_m        = wins_m / len(trades) * 100
                print(f"  {symbole:10} : {len(trades):3} trades | WR {round(wr_m,1):5}% | "
                      f"Gain {'+' if gain_marche>=0 else ''}{round(gain_marche,2):6}EUR"
                      f"{' ⚠️ RUINE' if ruine else ''}")
                if ruine:
                    ruine_globale = True

        # Analyse globale de l'option
        if tous_trades:
            df_all   = pd.DataFrame(tous_trades)
            nb       = len(tous_trades)
            wins     = len(df_all[df_all['resultat'] == 'GAGNE'])
            wr       = wins / nb * 100
            gain_tot = df_all['gain'].sum()
            avg_win  = df_all[df_all['resultat']=='GAGNE']['gain'].mean() if wins > 0 else 0
            avg_loss = df_all[df_all['resultat']=='PERDU']['gain'].mean() if (nb-wins) > 0 else 0

            # Drawdown sur capital simulé global
            cap_sim  = CAPITAL_INITIAL
            cap_list = [cap_sim]
            for t in tous_trades:
                cap_sim += t['gain']
                cap_list.append(cap_sim)
            peak   = CAPITAL_INITIAL
            max_dd = 0
            for c in cap_list:
                if c > peak: peak = c
                dd = (c - peak) / peak * 100
                if dd < max_dd: max_dd = dd

            gain_jour = gain_tot / 24
            gain_sem  = gain_tot / (24/7)

            print(f"\n  RÉSULTAT GLOBAL {option['nom']}")
            print(f"  {'─'*55}")
            print(f"  Trades total   : {nb}")
            print(f"  Win Rate global: {round(wr,1)}%")
            print(f"  Gain total     : {'+' if gain_tot>=0 else ''}{round(gain_tot,2)}EUR sur 24 jours")
            print(f"  Gain/jour      : {'+' if gain_jour>=0 else ''}{round(gain_jour,2)}EUR")
            print(f"  Gain/semaine   : {'+' if gain_sem>=0 else ''}{round(gain_sem,2)}EUR")
            print(f"  Avg win        : +{round(avg_win,2)}EUR")
            print(f"  Avg loss       : {round(avg_loss,2)}EUR")
            print(f"  Drawdown max   : {round(max_dd,1)}%")
            print(f"  Risque ruine   : {'⚠️ OUI — DANGEREUX' if ruine_globale else '✅ NON'}")

            resultats_options.append({
                'nom':        option['nom'],
                'levier':     option['levier'],
                'mise_pct':   option['mise_pct'],
                'nb_trades':  nb,
                'win_rate':   round(wr, 1),
                'gain_total': round(gain_tot, 2),
                'gain_jour':  round(gain_jour, 2),
                'gain_sem':   round(gain_sem, 2),
                'drawdown':   round(max_dd, 1),
                'ruine':      ruine_globale
            })

    # SYNTHÈSE FINALE
    print(f"\n  {'='*60}")
    print(f"  COMPARAISON FINALE DES 3 OPTIONS")
    print(f"  Objectif : 10€/jour")
    print(f"  {'='*60}")
    print(f"  {'Option':28} | {'WR':6} | {'Gain/j':7} | {'Gain/sem':9} | {'DD':6} | Risque")
    print(f"  {'-'*60}")

    for r in resultats_options:
        risque = "⚠️ RUINE" if r['ruine'] else "✅ OK"
        objectif = "🎯 OUI" if r['gain_jour'] >= 10 else "❌ NON"
        print(f"  {r['nom']:28} | {r['win_rate']:5}% | "
              f"{'+' if r['gain_jour']>=0 else ''}{r['gain_jour']:6}€ | "
              f"{'+' if r['gain_sem']>=0 else ''}{r['gain_sem']:8}€ | "
              f"{r['drawdown']:5}% | {risque} | {objectif}")

    print(f"\n  Pour atteindre 10€/jour avec 50€ de capital :")
    print(f"  Capital nécessaire avec option optimale :")
    if resultats_options:
        meilleur = max(resultats_options, key=lambda x: x['gain_jour'])
        if meilleur['gain_jour'] > 0:
            capital_necessaire = 10 / meilleur['gain_jour'] * CAPITAL_INITIAL
            print(f"  → Option {meilleur['nom']}")
            print(f"  → Capital nécessaire : {round(capital_necessaire, 0)}EUR")
        else:
            print(f"  → Aucune option n'est rentable sur cette période")
    print(f"  {'='*60}")

if __name__ == "__main__":
    main()
