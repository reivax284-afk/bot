"""
╔══════════════════════════════════════════════════════════════╗
║              BACKTESTER DONCHIAN 55/20                       ║
║         Stratégie Turtle Traders sur BTC + ETH               ║
║         H1 | ATR Stop | Frais + Slippage réels               ║
╚══════════════════════════════════════════════════════════════╝
"""

import requests
import pandas as pd
import time
from ta.trend import ADXIndicator
from ta.volatility import AverageTrueRange
from datetime import datetime

# ══════════════════════════════════════════════════════════════
# PARAMÈTRES
# ══════════════════════════════════════════════════════════════

CAPITAL_INITIAL  = 50.0
LEVIER           = 3
MISE_PCT         = 0.01
ATR_MULTIPLIER   = 2.0
ADX_SEUIL        = 20
VOLUME_MINI      = 0.50
FRAIS_PCT        = 0.0004
SLIPPAGE_PCT     = 0.0002
DONCHIAN_ENTREE  = 55
DONCHIAN_SORTIE  = 20

MARCHES = ["BTCUSDT", "ETHUSDT"]
KRAKEN_SYMBOLS = {
    "BTCUSDT": "XXBTZUSD",
    "ETHUSDT": "XETHZUSD"
}

# ══════════════════════════════════════════════════════════════
# DONNÉES
# ══════════════════════════════════════════════════════════════

def get_historical_data(symbole, jours=30):
    kraken_symbol = KRAKEN_SYMBOLS.get(symbole, symbole)
    url    = "https://api.kraken.com/0/public/OHLC"
    params = {"pair": kraken_symbol, "interval": 60}
    print(f"  Téléchargement {symbole}...")
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
        df = df.astype({
            'time': int, 'high': float, 'low': float,
            'close': float, 'volume': float
        })
        df['datetime'] = pd.to_datetime(df['time'], unit='s')
        df = df.set_index('datetime').sort_index()
        print(f"  {len(df)} bougies H1 récupérées")
        return df
    except Exception as e:
        print(f"  Erreur : {e}")
        return None

def ajouter_indicateurs(df):
    df = df.copy()
    adx_ind   = ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=14)
    atr_ind   = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14)
    df['adx'] = adx_ind.adx()
    df['atr'] = atr_ind.average_true_range()
    df['vol_moy_24h'] = df['volume'].rolling(24).mean()
    df['vol_ratio']   = df['volume'] / df['vol_moy_24h']

    # Niveaux Donchian
    df['don_haut_55'] = df['high'].shift(1).rolling(DONCHIAN_ENTREE).max()
    df['don_bas_55']  = df['low'].shift(1).rolling(DONCHIAN_ENTREE).min()
    df['don_haut_20'] = df['high'].shift(1).rolling(DONCHIAN_SORTIE).max()
    df['don_bas_20']  = df['low'].shift(1).rolling(DONCHIAN_SORTIE).min()

    return df.dropna()

# ══════════════════════════════════════════════════════════════
# BACKTEST DONCHIAN
# ══════════════════════════════════════════════════════════════

def backtest_donchian(df, symbole):
    print(f"\n  {'='*50}")
    print(f"  BACKTEST DONCHIAN — {symbole}")
    print(f"  Période : {df.index[0].strftime('%Y-%m-%d')} → {df.index[-1].strftime('%Y-%m-%d')}")
    print(f"  Bougies : {len(df)} H1")
    print(f"  {'='*50}")

    trades  = []
    capital = CAPITAL_INITIAL
    i       = DONCHIAN_ENTREE + 5
    frais   = (FRAIS_PCT + SLIPPAGE_PCT) * 2

    while i < len(df) - 25:
        row = df.iloc[i]

        # Filtres
        if row['adx'] < ADX_SEUIL:
            i += 1
            continue
        if row['vol_ratio'] < VOLUME_MINI:
            i += 1
            continue

        prix    = row['close']
        atr     = row['atr']
        signal  = None

        # Signal Donchian entrée
        if prix > row['don_haut_55']:
            signal = "ACHAT"
        elif prix < row['don_bas_55']:
            signal = "VENTE"

        if signal is None:
            i += 1
            continue

        # Simulation du trade
        prix_entree = prix
        mise        = CAPITAL_INITIAL * MISE_PCT

        if signal == "ACHAT":
            stop_loss = prix_entree - (atr * ATR_MULTIPLIER)
        else:
            stop_loss = prix_entree + (atr * ATR_MULTIPLIER)

        distance_stop = abs(prix_entree - stop_loss)
        resultat      = "NEUTRE"
        gain_brut     = 0
        duree         = 0

        # Simulation bougie par bougie (max 24h)
        for j in range(i + 1, min(i + 25, len(df))):
            row_j = df.iloc[j]
            duree = j - i

            if signal == "ACHAT":
                if row_j['low'] <= stop_loss:
                    gain_brut = (stop_loss - prix_entree) / prix_entree * mise * LEVIER
                    resultat  = "PERDU"
                    break
                if row_j['close'] < row_j['don_bas_20']:
                    gain_brut = (row_j['close'] - prix_entree) / prix_entree * mise * LEVIER
                    resultat  = "GAGNE" if gain_brut > 0 else "PERDU"
                    break
            else:
                if row_j['high'] >= stop_loss:
                    gain_brut = (prix_entree - stop_loss) / prix_entree * mise * LEVIER
                    resultat  = "PERDU"
                    break
                if row_j['close'] > row_j['don_haut_20']:
                    gain_brut = (prix_entree - row_j['close']) / prix_entree * mise * LEVIER
                    resultat  = "GAGNE" if gain_brut > 0 else "PERDU"
                    break

        if resultat == "NEUTRE":
            row_fin   = df.iloc[min(i + 24, len(df)-1)]
            prix_fin  = row_fin['close']
            if signal == "ACHAT":
                gain_brut = (prix_fin - prix_entree) / prix_entree * mise * LEVIER
            else:
                gain_brut = (prix_entree - prix_fin) / prix_entree * mise * LEVIER
            resultat = "GAGNE" if gain_brut > 0 else "PERDU"
            duree    = 24

        gain_net = round(gain_brut - frais * mise * LEVIER, 2)
        capital  = round(capital + gain_net, 2)

        trades.append({
            'date':      df.index[i].strftime('%Y-%m-%d %H:%M'),
            'signal':    signal,
            'resultat':  resultat,
            'gain':      gain_net,
            'duree_h':   duree,
            'capital':   capital,
            'adx':       round(row['adx'], 1),
            'atr_pct':   round((atr / prix) * 100, 2),
            'don_h55':   round(row['don_haut_55'], 4),
            'don_b55':   round(row['don_bas_55'], 4),
        })

        # Skip le trade + 2h de pause
        i = i + duree + 2

    return trades, capital

# ══════════════════════════════════════════════════════════════
# AFFICHAGE DES RÉSULTATS
# ══════════════════════════════════════════════════════════════

def afficher_resultats(trades, capital_final, symbole):
    if not trades:
        print(f"\n  Aucun trade Donchian trouvé sur {symbole}")
        return None

    df_t      = pd.DataFrame(trades)
    nb        = len(trades)
    wins      = len(df_t[df_t['resultat'] == 'GAGNE'])
    losses    = len(df_t[df_t['resultat'] == 'PERDU'])
    win_rate  = wins / nb * 100
    gain_tot  = df_t['gain'].sum()
    perf      = (capital_final - CAPITAL_INITIAL) / CAPITAL_INITIAL * 100
    avg_win   = df_t[df_t['resultat']=='GAGNE']['gain'].mean() if wins > 0 else 0
    avg_loss  = df_t[df_t['resultat']=='PERDU']['gain'].mean() if losses > 0 else 0

    # Drawdown
    capitals  = [CAPITAL_INITIAL] + [t['capital'] for t in trades]
    peak      = CAPITAL_INITIAL
    max_dd    = 0
    for c in capitals:
        if c > peak: peak = c
        dd = (c - peak) / peak * 100
        if dd < max_dd: max_dd = dd

    jours    = (pd.to_datetime(trades[-1]['date']) - pd.to_datetime(trades[0]['date'])).days
    sem      = nb / max(jours / 7, 1)

    print(f"\n  {'='*55}")
    print(f"  RÉSULTATS DONCHIAN — {symbole}")
    print(f"  {'='*55}")
    print(f"  Période          : {jours} jours")
    print(f"  Trades total     : {nb}")
    print(f"  Trades/semaine   : {round(sem, 1)}")
    print(f"  Victoires        : {wins} ({round(win_rate, 1)}%)")
    print(f"  Défaites         : {losses}")
    print(f"  Gain moyen win   : +{round(avg_win, 2)}EUR")
    print(f"  Perte moyenne    : {round(avg_loss, 2)}EUR")
    print(f"  Capital initial  : {CAPITAL_INITIAL}EUR")
    print(f"  Capital final    : {round(capital_final, 2)}EUR")
    print(f"  Performance      : {'+' if perf >= 0 else ''}{round(perf, 1)}%")
    print(f"  Gain total net   : {'+' if gain_tot >= 0 else ''}{round(gain_tot, 2)}EUR")
    print(f"  Drawdown max     : {round(max_dd, 1)}%")
    print(f"  {'='*55}")

    print(f"\n  Tous les trades :")
    for t in trades:
        icone = "✅" if t['resultat'] == "GAGNE" else "❌"
        print(f"    {icone} {t['date']} | {t['signal']} | "
              f"{'+' if t['gain'] >= 0 else ''}{t['gain']}EUR | "
              f"ADX {t['adx']} | ATR {t['atr_pct']}% | "
              f"{t['duree_h']}h | Capital: {t['capital']}EUR")

    return {
        'symbole': symbole, 'nb_trades': nb,
        'trades_semaine': round(sem, 1),
        'win_rate': round(win_rate, 1),
        'performance': round(perf, 1),
        'gain_total': round(gain_tot, 2),
        'drawdown_max': round(max_dd, 1)
    }

# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

def main():
    print("=" * 55)
    print("  BACKTESTER DONCHIAN 55/20 — TURTLES")
    print(f"  Entrée : breakout {DONCHIAN_ENTREE} bougies")
    print(f"  Sortie : breakout inverse {DONCHIAN_SORTIE} bougies")
    print(f"  Stop   : ATR × {ATR_MULTIPLIER}")
    print(f"  Frais  : {FRAIS_PCT*100}% | Slippage : {SLIPPAGE_PCT*100}%")
    print("=" * 55)

    resultats = []

    for symbole in MARCHES:
        df = get_historical_data(symbole)
        if df is None or len(df) < 100:
            print(f"  Impossible de récupérer {symbole}")
            continue

        df = ajouter_indicateurs(df)
        print(f"  {len(df)} bougies valides")

        trades, capital = backtest_donchian(df, symbole)
        result = afficher_resultats(trades, capital, symbole)
        if result:
            resultats.append(result)

        time.sleep(2)

    if resultats:
        print(f"\n  {'='*55}")
        print(f"  SYNTHÈSE GLOBALE DONCHIAN")
        print(f"  {'='*55}")
        for r in resultats:
            print(f"  {r['symbole']} : {r['nb_trades']} trades | "
                  f"T/sem {r['trades_semaine']} | "
                  f"WR {r['win_rate']}% | "
                  f"Perf {'+' if r['performance']>=0 else ''}{r['performance']}% | "
                  f"MaxDD {r['drawdown_max']}%")
        print(f"  {'='*55}")

if __name__ == "__main__":
    main()
