"""
╔══════════════════════════════════════════════════════════════╗
║              BACKTESTER ADAPTATIF V6                         ║
║   TENDANCE → Donchian 55/20                                  ║
║   RANGE    → Mean Reversion RSI                              ║
║   BTC + ETH + SOL | H1 | ATR Stop | Frais réels             ║
╚══════════════════════════════════════════════════════════════╝
"""

import requests
import pandas as pd
import time
from ta.trend import ADXIndicator
from ta.volatility import AverageTrueRange
from ta.momentum import RSIIndicator
from datetime import datetime

# ══════════════════════════════════════════════════════════════
# PARAMÈTRES — IDENTIQUES AU BOT V6
# ══════════════════════════════════════════════════════════════

CAPITAL_INITIAL  = 50.0
LEVIER           = 3
MISE_PCT         = 0.01
ATR_MULTIPLIER   = 1.5
RATIO_RR         = 2.0
ADX_TENDANCE     = 25
VOLUME_MINI      = 0.40
DONCHIAN_ENTREE  = 55
DONCHIAN_SORTIE  = 20
RSI_ACHAT        = 30
RSI_VENTE        = 70
FRAIS_PCT        = 0.0004
SLIPPAGE_PCT     = 0.0002
TIMEOUT_BOUGIES  = 12   # 12 bougies H1 = 12h max

MARCHES = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
KRAKEN_SYMBOLS = {
    "BTCUSDT": "XXBTZUSD",
    "ETHUSDT": "XETHZUSD",
    "SOLUSDT": "SOLUSD"
}

# ══════════════════════════════════════════════════════════════
# DONNÉES
# ══════════════════════════════════════════════════════════════

def get_historical_data(symbole):
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

    # ADX, ATR, RSI
    adx_ind   = ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=14)
    atr_ind   = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14)
    rsi_ind   = RSIIndicator(close=df['close'], window=14)

    df['adx'] = adx_ind.adx()
    df['atr'] = atr_ind.average_true_range()
    df['rsi'] = rsi_ind.rsi()

    # Volume ratio
    df['vol_moy_24h'] = df['volume'].rolling(24).mean()
    df['vol_ratio']   = df['volume'] / df['vol_moy_24h']

    # Donchian (shift pour éviter le look-ahead)
    df['don_haut_55'] = df['high'].shift(1).rolling(DONCHIAN_ENTREE).max()
    df['don_bas_55']  = df['low'].shift(1).rolling(DONCHIAN_ENTREE).min()
    df['don_haut_20'] = df['high'].shift(1).rolling(DONCHIAN_SORTIE).max()
    df['don_bas_20']  = df['low'].shift(1).rolling(DONCHIAN_SORTIE).min()

    return df.dropna()

# ══════════════════════════════════════════════════════════════
# BACKTEST ADAPTATIF
# ══════════════════════════════════════════════════════════════

def backtest_adaptatif(df, symbole):
    print(f"\n  {'='*50}")
    print(f"  BACKTEST ADAPTATIF V6 — {symbole}")
    print(f"  Période : {df.index[0].strftime('%Y-%m-%d')} → {df.index[-1].strftime('%Y-%m-%d')}")
    print(f"  Bougies : {len(df)} H1")
    print(f"  {'='*50}")

    trades   = []
    capital  = CAPITAL_INITIAL
    i        = DONCHIAN_ENTREE + 5
    frais    = (FRAIS_PCT + SLIPPAGE_PCT) * 2

    nb_tendance    = 0
    nb_range       = 0
    nb_skip_volume = 0

    while i < len(df) - TIMEOUT_BOUGIES - 2:
        row = df.iloc[i]

        # Filtre volume
        if row['vol_ratio'] < VOLUME_MINI:
            nb_skip_volume += 1
            i += 1
            continue

        prix    = row['close']
        atr     = row['atr']
        adx     = row['adx']
        rsi     = row['rsi']
        signal  = None
        strat   = None

        # Détection régime
        if adx >= ADX_TENDANCE:
            # TENDANCE → Donchian
            if prix > row['don_haut_55']:
                signal = "ACHAT"
                strat  = "DONCHIAN"
                nb_tendance += 1
            elif prix < row['don_bas_55']:
                signal = "VENTE"
                strat  = "DONCHIAN"
                nb_tendance += 1
        else:
            # RANGE → Mean Reversion
            if rsi < RSI_ACHAT:
                signal = "ACHAT"
                strat  = "MEAN_REV"
                nb_range += 1
            elif rsi > RSI_VENTE:
                signal = "VENTE"
                strat  = "MEAN_REV"
                nb_range += 1

        if signal is None:
            i += 1
            continue

        # Calcul stop et objectif
        mise = CAPITAL_INITIAL * MISE_PCT
        if signal == "ACHAT":
            stop_loss = prix - (atr * ATR_MULTIPLIER)
        else:
            stop_loss = prix + (atr * ATR_MULTIPLIER)

        distance_stop = abs(prix - stop_loss)

        if strat == "DONCHIAN":
            if signal == "ACHAT":
                objectif = row['don_bas_20']
            else:
                objectif = row['don_haut_20']
        else:
            if signal == "ACHAT":
                objectif = prix + (distance_stop * RATIO_RR)
            else:
                objectif = prix - (distance_stop * RATIO_RR)

        # Simulation bougie par bougie
        resultat  = "NEUTRE"
        gain_brut = 0
        duree     = 0

        for j in range(i + 1, min(i + TIMEOUT_BOUGIES + 1, len(df))):
            row_j = df.iloc[j]
            duree = j - i

            if signal == "ACHAT":
                if row_j['low'] <= stop_loss:
                    gain_brut = (stop_loss - prix) / prix * mise * LEVIER
                    resultat  = "PERDU"
                    break
                if row_j['high'] >= objectif:
                    gain_brut = (objectif - prix) / prix * mise * LEVIER
                    resultat  = "GAGNE"
                    break
                # Sortie Donchian inverse
                if strat == "DONCHIAN" and row_j['close'] < row_j['don_bas_20']:
                    gain_brut = (row_j['close'] - prix) / prix * mise * LEVIER
                    resultat  = "GAGNE" if gain_brut > 0 else "PERDU"
                    break
            else:
                if row_j['high'] >= stop_loss:
                    gain_brut = (prix - stop_loss) / prix * mise * LEVIER
                    resultat  = "PERDU"
                    break
                if row_j['low'] <= objectif:
                    gain_brut = (prix - objectif) / prix * mise * LEVIER
                    resultat  = "GAGNE"
                    break
                if strat == "DONCHIAN" and row_j['close'] > row_j['don_haut_20']:
                    gain_brut = (prix - row_j['close']) / prix * mise * LEVIER
                    resultat  = "GAGNE" if gain_brut > 0 else "PERDU"
                    break

        # Timeout
        if resultat == "NEUTRE":
            prix_fin  = df.iloc[min(i + TIMEOUT_BOUGIES, len(df)-1)]['close']
            if signal == "ACHAT":
                gain_brut = (prix_fin - prix) / prix * mise * LEVIER
            else:
                gain_brut = (prix - prix_fin) / prix * mise * LEVIER
            resultat = "GAGNE" if gain_brut > 0 else "PERDU"
            duree    = TIMEOUT_BOUGIES

        gain_net = round(gain_brut - frais * mise * LEVIER, 2)
        capital  = round(capital + gain_net, 2)

        trades.append({
            'date':     df.index[i].strftime('%Y-%m-%d %H:%M'),
            'signal':   signal,
            'strat':    strat,
            'resultat': resultat,
            'gain':     gain_net,
            'duree_h':  duree,
            'capital':  capital,
            'adx':      round(adx, 1),
            'rsi':      round(rsi, 1),
            'atr_pct':  round((atr / prix) * 100, 2)
        })

        i = i + duree + 2

    print(f"  Signaux TENDANCE (Donchian)  : {nb_tendance}")
    print(f"  Signaux RANGE (Mean Rev)     : {nb_range}")
    print(f"  Skips volume                 : {nb_skip_volume}")

    return trades, capital

# ══════════════════════════════════════════════════════════════
# AFFICHAGE
# ══════════════════════════════════════════════════════════════

def afficher_resultats(trades, capital_final, symbole):
    if not trades:
        print(f"\n  Aucun trade trouvé sur {symbole}")
        return None

    df_t     = pd.DataFrame(trades)
    nb       = len(trades)
    wins     = len(df_t[df_t['resultat'] == 'GAGNE'])
    losses   = len(df_t[df_t['resultat'] == 'PERDU'])
    win_rate = wins / nb * 100
    gain_tot = df_t['gain'].sum()
    perf     = (capital_final - CAPITAL_INITIAL) / CAPITAL_INITIAL * 100
    avg_win  = df_t[df_t['resultat']=='GAGNE']['gain'].mean() if wins > 0 else 0
    avg_loss = df_t[df_t['resultat']=='PERDU']['gain'].mean() if losses > 0 else 0

    # Par stratégie
    don_trades = df_t[df_t['strat'] == 'DONCHIAN']
    rev_trades = df_t[df_t['strat'] == 'MEAN_REV']

    don_wr = len(don_trades[don_trades['resultat']=='GAGNE']) / len(don_trades) * 100 if len(don_trades) > 0 else 0
    rev_wr = len(rev_trades[rev_trades['resultat']=='GAGNE']) / len(rev_trades) * 100 if len(rev_trades) > 0 else 0

    # Drawdown
    capitals = [CAPITAL_INITIAL] + [t['capital'] for t in trades]
    peak     = CAPITAL_INITIAL
    max_dd   = 0
    for c in capitals:
        if c > peak: peak = c
        dd = (c - peak) / peak * 100
        if dd < max_dd: max_dd = dd

    jours = (pd.to_datetime(trades[-1]['date']) - pd.to_datetime(trades[0]['date'])).days
    sem   = nb / max(jours / 7, 1)

    print(f"\n  {'='*55}")
    print(f"  RÉSULTATS ADAPTATIF V6 — {symbole}")
    print(f"  {'='*55}")
    print(f"  Période          : {jours} jours")
    print(f"  Trades total     : {nb} ({round(sem,1)}/semaine)")
    print(f"  Victoires        : {wins} ({round(win_rate,1)}%)")
    print(f"  Défaites         : {losses}")
    print(f"  Gain moyen win   : +{round(avg_win,2)}EUR")
    print(f"  Perte moyenne    : {round(avg_loss,2)}EUR")
    print(f"  Capital final    : {round(capital_final,2)}EUR")
    print(f"  Performance      : {'+' if perf>=0 else ''}{round(perf,1)}%")
    print(f"  Gain total net   : {'+' if gain_tot>=0 else ''}{round(gain_tot,2)}EUR")
    print(f"  Drawdown max     : {round(max_dd,1)}%")
    print(f"  {'─'*55}")
    print(f"  DONCHIAN  : {len(don_trades)} trades | WR {round(don_wr,1)}%")
    print(f"  MEAN_REV  : {len(rev_trades)} trades | WR {round(rev_wr,1)}%")
    print(f"  {'='*55}")

    print(f"\n  Tous les trades :")
    for t in trades:
        icone = "✅" if t['resultat'] == "GAGNE" else "❌"
        print(f"    {icone} {t['date']} | [{t['strat']:9}] {t['signal']:5} | "
              f"{'+' if t['gain']>=0 else ''}{t['gain']}EUR | "
              f"ADX {t['adx']} | RSI {t['rsi']} | "
              f"{t['duree_h']}h | {t['capital']}EUR")

    return {
        'symbole': symbole, 'nb_trades': nb,
        'trades_semaine': round(sem,1),
        'win_rate': round(win_rate,1),
        'performance': round(perf,1),
        'gain_total': round(gain_tot,2),
        'drawdown_max': round(max_dd,1),
        'don_wr': round(don_wr,1),
        'rev_wr': round(rev_wr,1)
    }

# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

def main():
    print("=" * 55)
    print("  BACKTESTER ADAPTATIF V6")
    print(f"  ADX > {ADX_TENDANCE} → DONCHIAN | ADX < {ADX_TENDANCE} → MEAN REVERSION")
    print(f"  Stop ATR × {ATR_MULTIPLIER} | Ratio 1:{int(RATIO_RR)}")
    print(f"  Frais {FRAIS_PCT*100}% + Slippage {SLIPPAGE_PCT*100}%")
    print(f"  Marches : {', '.join(MARCHES)}")
    print("=" * 55)

    resultats = []

    for symbole in MARCHES:
        df = get_historical_data(symbole)
        if df is None or len(df) < 100:
            print(f"  Impossible de récupérer {symbole}")
            continue

        df = ajouter_indicateurs(df)
        print(f"  {len(df)} bougies valides")

        trades, capital = backtest_adaptatif(df, symbole)
        result = afficher_resultats(trades, capital, symbole)
        if result:
            resultats.append(result)

        time.sleep(2)

    if resultats:
        print(f"\n  {'='*55}")
        print(f"  SYNTHÈSE GLOBALE")
        print(f"  {'='*55}")
        for r in resultats:
            print(f"  {r['symbole']:8} : {r['nb_trades']:3} trades | "
                  f"{r['trades_semaine']}/sem | "
                  f"WR {r['win_rate']}% | "
                  f"Perf {'+' if r['performance']>=0 else ''}{r['performance']}% | "
                  f"DD {r['drawdown_max']}% | "
                  f"DON {r['don_wr']}% | REV {r['rev_wr']}%")
        print(f"  {'='*55}")

if __name__ == "__main__":
    main()
