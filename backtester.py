"""
╔══════════════════════════════════════════════════════════════╗
║           BACKTESTER ADAPTATIF V6.1                          ║
║   Stop ATR×2.5 | Ratio 1:1.5 | Sortie partielle 50%        ║
║   BTC + ETH + SOL | H1 | Frais réels                        ║
╚══════════════════════════════════════════════════════════════╝
"""

import requests
import pandas as pd
import time
from ta.trend import ADXIndicator
from ta.volatility import AverageTrueRange
from ta.momentum import RSIIndicator

CAPITAL_INITIAL  = 50.0
LEVIER           = 3
MISE_PCT         = 0.01
ATR_MULTIPLIER   = 2.5
RATIO_RR         = 1.5
RATIO_PARTIEL    = 1.0
ADX_TENDANCE     = 25
VOLUME_MINI      = 0.40
DONCHIAN_ENTREE  = 55
DONCHIAN_SORTIE  = 20
RSI_ACHAT        = 30
RSI_VENTE        = 70
FRAIS_PCT        = 0.0004
SLIPPAGE_PCT     = 0.0002
TIMEOUT_BOUGIES  = 12

MARCHES = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
KRAKEN_SYMBOLS = {
    "BTCUSDT": "XXBTZUSD",
    "ETHUSDT": "XETHZUSD",
    "SOLUSDT": "SOLUSD"
}

def get_data(symbole):
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
        df = df.astype({'time': int, 'high': float, 'low': float,
                        'close': float, 'volume': float})
        df['datetime'] = pd.to_datetime(df['time'], unit='s')
        df = df.set_index('datetime').sort_index()
        print(f"  {len(df)} bougies H1")
        return df
    except Exception as e:
        print(f"  Erreur : {e}")
        return None

def ajouter_indicateurs(df):
    df = df.copy()
    df['adx'] = ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=14).adx()
    df['atr'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range()
    df['rsi'] = RSIIndicator(close=df['close'], window=14).rsi()
    df['vol_moy'] = df['volume'].rolling(24).mean()
    df['vol_ratio'] = df['volume'] / df['vol_moy']
    df['don_haut_55'] = df['high'].shift(1).rolling(DONCHIAN_ENTREE).max()
    df['don_bas_55']  = df['low'].shift(1).rolling(DONCHIAN_ENTREE).min()
    df['don_haut_20'] = df['high'].shift(1).rolling(DONCHIAN_SORTIE).max()
    df['don_bas_20']  = df['low'].shift(1).rolling(DONCHIAN_SORTIE).min()
    return df.dropna()

def backtest(df, symbole):
    print(f"\n  {'='*50}")
    print(f"  BACKTEST V6.1 — {symbole}")
    print(f"  Période : {df.index[0].strftime('%Y-%m-%d')} → {df.index[-1].strftime('%Y-%m-%d')}")
    print(f"  {'='*50}")

    trades   = []
    capital  = CAPITAL_INITIAL
    i        = DONCHIAN_ENTREE + 5
    frais    = (FRAIS_PCT + SLIPPAGE_PCT) * 2

    while i < len(df) - TIMEOUT_BOUGIES - 2:
        row = df.iloc[i]

        if row['vol_ratio'] < VOLUME_MINI:
            i += 1
            continue

        prix   = row['close']
        atr    = row['atr']
        adx    = row['adx']
        rsi    = row['rsi']
        signal = None
        strat  = None

        if adx >= ADX_TENDANCE:
            if prix > row['don_haut_55']:
                signal, strat = "ACHAT", "DONCHIAN"
            elif prix < row['don_bas_55']:
                signal, strat = "VENTE", "DONCHIAN"
        else:
            if rsi < RSI_ACHAT:
                signal, strat = "ACHAT", "MEAN_REV"
            elif rsi > RSI_VENTE:
                signal, strat = "VENTE", "MEAN_REV"

        if signal is None:
            i += 1
            continue

        mise          = CAPITAL_INITIAL * MISE_PCT
        distance_stop = atr * ATR_MULTIPLIER

        if signal == "ACHAT":
            stop_loss       = prix - distance_stop
            obj_partiel     = prix + (distance_stop * RATIO_PARTIEL)
            obj_final       = prix + (distance_stop * RATIO_RR)
        else:
            stop_loss       = prix + distance_stop
            obj_partiel     = prix - (distance_stop * RATIO_PARTIEL)
            obj_final       = prix - (distance_stop * RATIO_RR)

        partiel_fait = False
        gain_partiel = 0
        gain_brut    = 0
        resultat     = "NEUTRE"
        duree        = 0

        for j in range(i + 1, min(i + TIMEOUT_BOUGIES + 1, len(df))):
            row_j = df.iloc[j]
            duree = j - i

            if signal == "ACHAT":
                # Sortie partielle
                if not partiel_fait and row_j['high'] >= obj_partiel:
                    gain_partiel = (obj_partiel - prix) / prix * mise * LEVIER * 0.5
                    partiel_fait = True
                    stop_loss    = prix  # Stop → prix entrée
                # Stop
                if row_j['low'] <= stop_loss:
                    if partiel_fait:
                        gain_reste = (stop_loss - prix) / prix * mise * LEVIER * 0.5
                        gain_brut  = gain_partiel + gain_reste
                    else:
                        gain_brut = (stop_loss - prix) / prix * mise * LEVIER
                    resultat = "GAGNE" if gain_brut > 0 else "PERDU"
                    break
                # Objectif final
                if row_j['high'] >= obj_final:
                    gain_reste = (obj_final - prix) / prix * mise * LEVIER * 0.5
                    gain_brut  = gain_partiel + gain_reste
                    resultat   = "GAGNE"
                    break
            else:
                if not partiel_fait and row_j['low'] <= obj_partiel:
                    gain_partiel = (prix - obj_partiel) / prix * mise * LEVIER * 0.5
                    partiel_fait = True
                    stop_loss    = prix
                if row_j['high'] >= stop_loss:
                    if partiel_fait:
                        gain_reste = (prix - stop_loss) / prix * mise * LEVIER * 0.5
                        gain_brut  = gain_partiel + gain_reste
                    else:
                        gain_brut = (prix - stop_loss) / prix * mise * LEVIER
                    resultat = "GAGNE" if gain_brut > 0 else "PERDU"
                    break
                if row_j['low'] <= obj_final:
                    gain_reste = (prix - obj_final) / prix * mise * LEVIER * 0.5
                    gain_brut  = gain_partiel + gain_reste
                    resultat   = "GAGNE"
                    break

        if resultat == "NEUTRE":
            prix_fin = df.iloc[min(i + TIMEOUT_BOUGIES, len(df)-1)]['close']
            if signal == "ACHAT":
                gain_brut = (prix_fin - prix) / prix * mise * LEVIER
            else:
                gain_brut = (prix - prix_fin) / prix * mise * LEVIER
            if partiel_fait:
                gain_brut = gain_partiel + gain_brut * 0.5
            resultat = "GAGNE" if gain_brut > 0 else "PERDU"
            duree    = TIMEOUT_BOUGIES

        gain_net = round(gain_brut - frais * mise * LEVIER, 2)
        capital  = round(capital + gain_net, 2)

        trades.append({
            'date': df.index[i].strftime('%Y-%m-%d %H:%M'),
            'signal': signal, 'strat': strat,
            'resultat': resultat, 'gain': gain_net,
            'partiel': partiel_fait,
            'duree_h': duree, 'capital': capital,
            'adx': round(adx, 1), 'rsi': round(rsi, 1),
            'atr_pct': round((atr / prix) * 100, 2)
        })

        i = i + duree + 2

    return trades, capital

def afficher(trades, capital_final, symbole):
    if not trades:
        print(f"\n  Aucun trade sur {symbole}")
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

    don = df_t[df_t['strat'] == 'DONCHIAN']
    rev = df_t[df_t['strat'] == 'MEAN_REV']
    don_wr = len(don[don['resultat']=='GAGNE']) / len(don) * 100 if len(don) > 0 else 0
    rev_wr = len(rev[rev['resultat']=='GAGNE']) / len(rev) * 100 if len(rev) > 0 else 0

    capitals = [CAPITAL_INITIAL] + [t['capital'] for t in trades]
    peak = CAPITAL_INITIAL
    max_dd = 0
    for c in capitals:
        if c > peak: peak = c
        dd = (c - peak) / peak * 100
        if dd < max_dd: max_dd = dd

    jours = (pd.to_datetime(trades[-1]['date']) - pd.to_datetime(trades[0]['date'])).days
    sem   = nb / max(jours / 7, 1)

    print(f"\n  {'='*55}")
    print(f"  RÉSULTATS V6.1 — {symbole}")
    print(f"  {'='*55}")
    print(f"  Période        : {jours} jours")
    print(f"  Trades         : {nb} ({round(sem,1)}/semaine)")
    print(f"  Victoires      : {wins} ({round(win_rate,1)}%)")
    print(f"  Défaites       : {losses}")
    print(f"  Gain moyen win : +{round(avg_win,2)}EUR")
    print(f"  Perte moyenne  : {round(avg_loss,2)}EUR")
    print(f"  Capital final  : {round(capital_final,2)}EUR")
    print(f"  Performance    : {'+' if perf>=0 else ''}{round(perf,1)}%")
    print(f"  Gain total net : {'+' if gain_tot>=0 else ''}{round(gain_tot,2)}EUR")
    print(f"  Drawdown max   : {round(max_dd,1)}%")
    print(f"  {'─'*55}")
    print(f"  DONCHIAN : {len(don)} trades | WR {round(don_wr,1)}%")
    print(f"  MEAN_REV : {len(rev)} trades | WR {round(rev_wr,1)}%")
    print(f"  {'='*55}")

    print(f"\n  Tous les trades :")
    for t in trades:
        icone = "✅" if t['resultat'] == "GAGNE" else "❌"
        partiel = "P" if t['partiel'] else " "
        print(f"    {icone}{partiel} {t['date']} | [{t['strat']:9}] {t['signal']:5} | "
              f"{'+' if t['gain']>=0 else ''}{t['gain']}EUR | "
              f"ADX {t['adx']} | RSI {t['rsi']} | {t['duree_h']}h | {t['capital']}EUR")

    return {
        'symbole': symbole, 'nb_trades': nb,
        'trades_semaine': round(sem, 1),
        'win_rate': round(win_rate, 1),
        'performance': round(perf, 1),
        'gain_total': round(gain_tot, 2),
        'drawdown_max': round(max_dd, 1),
        'don_wr': round(don_wr, 1),
        'rev_wr': round(rev_wr, 1)
    }

def main():
    print("=" * 55)
    print("  BACKTESTER ADAPTATIF V6.1")
    print(f"  Stop ATR×{ATR_MULTIPLIER} | Ratio 1:{RATIO_RR} | Partiel 50% à 1:{RATIO_PARTIEL}")
    print(f"  Marches : {', '.join(MARCHES)}")
    print("=" * 55)

    resultats = []
    for symbole in MARCHES:
        df = get_data(symbole)
        if df is None or len(df) < 100:
            continue
        df = ajouter_indicateurs(df)
        print(f"  {len(df)} bougies valides")
        trades, capital = backtest(df, symbole)
        result = afficher(trades, capital, symbole)
        if result:
            resultats.append(result)
        time.sleep(2)

    if resultats:
        print(f"\n  {'='*55}")
        print(f"  SYNTHÈSE GLOBALE V6.1")
        print(f"  {'='*55}")
        for r in resultats:
            print(f"  {r['symbole']:8} : {r['nb_trades']:3} trades | "
                  f"{r['trades_semaine']}/sem | WR {r['win_rate']}% | "
                  f"Perf {'+' if r['performance']>=0 else ''}{r['performance']}% | "
                  f"DD {r['drawdown_max']}% | "
                  f"DON {r['don_wr']}% | REV {r['rev_wr']}%")
        print(f"  {'='*55}")

if __name__ == "__main__":
    main()
