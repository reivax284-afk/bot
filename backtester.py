"""
╔══════════════════════════════════════════════════════════════╗
║           BACKTESTER MEAN REVERSION V7                       ║
║   RSI < 30 → ACHAT | RSI > 70 → VENTE                      ║
║   8 marchés | H1 | Stop ATR×2.5 | Ratio 1:1.5              ║
║   Sortie partielle 50% | Frais réels                         ║
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
RSI_ACHAT        = 30
RSI_VENTE        = 70
ADX_MAX          = 40
VOLUME_MINI      = 0.40
FRAIS_PCT        = 0.0004
SLIPPAGE_PCT     = 0.0002
TIMEOUT_BOUGIES  = 12

MARCHES = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "LINKUSDT", "DOTUSDT", "ATOMUSDT"
]
KRAKEN_SYMBOLS = {
    "BTCUSDT":  "XXBTZUSD",
    "ETHUSDT":  "XETHZUSD",
    "BNBUSDT":  "BNBUSD",
    "XRPUSDT":  "XXRPZUSD",
    "ADAUSDT":  "ADAUSD",
    "LINKUSDT": "LINKUSD",
    "DOTUSDT":  "DOTUSD",
    "ATOMUSDT": "ATOMUSD"
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
            print(f"  Erreur API {symbole} : {data['error']}")
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
        print(f"  Erreur {symbole} : {e}")
        return None

def ajouter_indicateurs(df):
    df = df.copy()
    df['adx'] = ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=14).adx()
    df['atr'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range()
    df['rsi'] = RSIIndicator(close=df['close'], window=14).rsi()
    df['vol_moy']   = df['volume'].rolling(24).mean()
    df['vol_ratio'] = df['volume'] / df['vol_moy']
    return df.dropna()

def backtest_mean_reversion(df, symbole):
    trades   = []
    capital  = CAPITAL_INITIAL
    i        = 20
    frais    = (FRAIS_PCT + SLIPPAGE_PCT) * 2

    while i < len(df) - TIMEOUT_BOUGIES - 2:
        row = df.iloc[i]

        # Filtres
        if row['vol_ratio'] < VOLUME_MINI:
            i += 1
            continue
        if row['adx'] > ADX_MAX:
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

        mise          = CAPITAL_INITIAL * MISE_PCT
        distance_stop = atr * ATR_MULTIPLIER

        if signal == "ACHAT":
            stop_loss    = prix - distance_stop
            obj_partiel  = prix + (distance_stop * RATIO_PARTIEL)
            obj_final    = prix + (distance_stop * RATIO_RR)
        else:
            stop_loss    = prix + distance_stop
            obj_partiel  = prix - (distance_stop * RATIO_PARTIEL)
            obj_final    = prix - (distance_stop * RATIO_RR)

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
                    gain_partiel = (obj_partiel - prix) / prix * mise * LEVIER * 0.5
                    partiel_fait = True
                    stop_loss    = prix
                if row_j['low'] <= stop_loss:
                    gain_reste = (stop_loss - prix) / prix * mise * LEVIER * (0.5 if partiel_fait else 1.0)
                    gain_brut  = gain_partiel + gain_reste
                    resultat   = "GAGNE" if gain_brut > 0 else "PERDU"
                    break
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
                    gain_reste = (prix - stop_loss) / prix * mise * LEVIER * (0.5 if partiel_fait else 1.0)
                    gain_brut  = gain_partiel + gain_reste
                    resultat   = "GAGNE" if gain_brut > 0 else "PERDU"
                    break
                if row_j['low'] <= obj_final:
                    gain_reste = (prix - obj_final) / prix * mise * LEVIER * 0.5
                    gain_brut  = gain_partiel + gain_reste
                    resultat   = "GAGNE"
                    break

        if resultat == "NEUTRE":
            prix_fin  = df.iloc[min(i + TIMEOUT_BOUGIES, len(df)-1)]['close']
            if signal == "ACHAT":
                g = (prix_fin - prix) / prix * mise * LEVIER
            else:
                g = (prix - prix_fin) / prix * mise * LEVIER
            gain_brut = gain_partiel + g * (0.5 if partiel_fait else 1.0)
            resultat  = "GAGNE" if gain_brut > 0 else "PERDU"
            duree     = TIMEOUT_BOUGIES

        gain_net = round(gain_brut - frais * mise * LEVIER, 2)
        capital  = round(capital + gain_net, 2)

        trades.append({
            'date': df.index[i].strftime('%Y-%m-%d %H:%M'),
            'signal': signal, 'resultat': resultat,
            'gain': gain_net, 'partiel': partiel_fait,
            'duree_h': duree, 'capital': capital,
            'adx': round(row['adx'], 1),
            'rsi': round(rsi, 1),
            'atr_pct': round((atr / prix) * 100, 2)
        })

        i = i + duree + 2

    return trades, capital

def afficher(trades, capital_final, symbole):
    if not trades:
        print(f"  Aucun trade sur {symbole}")
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
    nb_part  = len(df_t[df_t['partiel'] == True])

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
    print(f"  RÉSULTATS MEAN REV V7 — {symbole}")
    print(f"  {'='*55}")
    print(f"  Période        : {jours} jours")
    print(f"  Trades         : {nb} ({round(sem,1)}/semaine)")
    print(f"  Victoires      : {wins} ({round(win_rate,1)}%)")
    print(f"  Défaites       : {losses}")
    print(f"  Sortie partiel : {nb_part} trades")
    print(f"  Gain moyen win : +{round(avg_win,2)}EUR")
    print(f"  Perte moyenne  : {round(avg_loss,2)}EUR")
    print(f"  Capital final  : {round(capital_final,2)}EUR")
    print(f"  Performance    : {'+' if perf>=0 else ''}{round(perf,1)}%")
    print(f"  Gain total net : {'+' if gain_tot>=0 else ''}{round(gain_tot,2)}EUR")
    print(f"  Drawdown max   : {round(max_dd,1)}%")
    print(f"  {'='*55}")

    print(f"\n  Tous les trades :")
    for t in trades:
        icone   = "✅" if t['resultat'] == "GAGNE" else "❌"
        partiel = "P" if t['partiel'] else " "
        print(f"    {icone}{partiel} {t['date']} | {t['signal']:5} | "
              f"RSI {t['rsi']:5} | ADX {t['adx']:5} | "
              f"{'+' if t['gain']>=0 else ''}{t['gain']}EUR | "
              f"{t['duree_h']}h | {t['capital']}EUR")

    return {
        'symbole': symbole, 'nb_trades': nb,
        'trades_semaine': round(sem, 1),
        'win_rate': round(win_rate, 1),
        'performance': round(perf, 1),
        'gain_total': round(gain_tot, 2),
        'drawdown_max': round(max_dd, 1)
    }

def main():
    print("=" * 55)
    print("  BACKTESTER MEAN REVERSION V7")
    print(f"  RSI < {RSI_ACHAT} → ACHAT | RSI > {RSI_VENTE} → VENTE")
    print(f"  ADX max {ADX_MAX} | Stop ATR×{ATR_MULTIPLIER} | Ratio 1:{RATIO_RR}")
    print(f"  Partiel 50% à 1:{RATIO_PARTIEL} | {len(MARCHES)} marchés")
    print("=" * 55)

    resultats = []
    for symbole in MARCHES:
        df = get_data(symbole)
        if df is None or len(df) < 50:
            print(f"  Skip {symbole}")
            continue
        df = ajouter_indicateurs(df)
        print(f"  {len(df)} bougies valides")
        trades, capital = backtest_mean_reversion(df, symbole)
        result = afficher(trades, capital, symbole)
        if result:
            resultats.append(result)
        time.sleep(1)

    if resultats:
        print(f"\n  {'='*55}")
        print(f"  SYNTHÈSE GLOBALE MEAN REVERSION V7")
        print(f"  {'='*55}")
        print(f"  {'Marché':10} | {'Trades':6} | {'T/sem':5} | {'WR':6} | {'Perf':6} | {'DD':6}")
        print(f"  {'-'*55}")
        for r in sorted(resultats, key=lambda x: x['performance'], reverse=True):
            print(f"  {r['symbole']:10} | {r['nb_trades']:6} | "
                  f"{r['trades_semaine']:5} | {r['win_rate']:5}% | "
                  f"{'+' if r['performance']>=0 else ''}{r['performance']:5}% | "
                  f"{r['drawdown_max']:5}%")
        print(f"  {'='*55}")
        print(f"\n  Meilleur marché : {max(resultats, key=lambda x: x['performance'])['symbole']}")
        print(f"  Meilleur WR     : {max(resultats, key=lambda x: x['win_rate'])['symbole']}")

if __name__ == "__main__":
    main()
