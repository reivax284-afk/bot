"""
╔══════════════════════════════════════════════════════════════╗
║                    BACKTESTER V1                             ║
║     Stratégie BOT ULTIME V4.2 sur données historiques        ║
║     BTC + ETH | H1 | 6 mois | Frais + Slippage réels        ║
╚══════════════════════════════════════════════════════════════╝
"""

import requests
import pandas as pd
import time
from ta.trend import ADXIndicator
from ta.volatility import AverageTrueRange
from ta.momentum import RSIIndicator
from datetime import datetime, timedelta

# ══════════════════════════════════════════════════════════════
# PARAMÈTRES — IDENTIQUES AU BOT ULTIME V4.2
# ══════════════════════════════════════════════════════════════

CAPITAL_INITIAL  = 50.0
LEVIER           = 3
MISE_PCT         = 0.01      # 1% du capital (avant Kelly)
ATR_MULTIPLIER   = 2.0
RATIO_RR         = 2.0
ADX_SEUIL        = 20
VOLUME_MINI      = 0.50
SCORE_MIN        = 18
FRAIS_PCT        = 0.0004    # 0.04% par côté Binance taker
SLIPPAGE_PCT     = 0.0002    # 0.02% slippage estimé

MARCHES = ["BTCUSDT", "ETHUSDT"]

KRAKEN_SYMBOLS = {
    "BTCUSDT": "XXBTZUSD",
    "ETHUSDT": "XETHZUSD"
}

# ══════════════════════════════════════════════════════════════
# RÉCUPÉRATION DES DONNÉES HISTORIQUES
# ══════════════════════════════════════════════════════════════

def get_historical_data(symbole, jours=180):
    """
    Récupère les données historiques H1 via Kraken.
    Kraken limite à 720 bougies par requête.
    """
    kraken_symbol = KRAKEN_SYMBOLS.get(symbole, symbole)
    url    = "https://api.kraken.com/0/public/OHLC"
    since  = int((datetime.now() - timedelta(days=jours)).timestamp())
    params = {"pair": kraken_symbol, "interval": 60, "since": since}

    print(f"  Téléchargement {symbole} ({jours} jours)...")
    try:
        r    = requests.get(url, params=params, timeout=30)
        data = r.json()
        if data.get("error") and data["error"]:
            print(f"  Erreur API : {data['error']}")
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
            'time': int, 'open': float, 'high': float,
            'low': float, 'close': float, 'volume': float
        })
        df['datetime'] = pd.to_datetime(df['time'], unit='s')
        df = df.set_index('datetime').sort_index()
        print(f"  {len(df)} bougies H1 récupérées")
        return df
    except Exception as e:
        print(f"  Erreur : {e}")
        return None

# ══════════════════════════════════════════════════════════════
# CALCUL DES INDICATEURS
# ══════════════════════════════════════════════════════════════

def ajouter_indicateurs(df):
    """Ajoute ADX, ATR, RSI, MA sur le DataFrame."""
    df = df.copy()

    # ADX
    adx_ind  = ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=14)
    df['adx'] = adx_ind.adx()

    # ATR
    atr_ind  = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14)
    df['atr'] = atr_ind.average_true_range()

    # RSI
    rsi_ind  = RSIIndicator(close=df['close'], window=14)
    df['rsi'] = rsi_ind.rsi()

    # MA 10 et 30
    df['ma10'] = df['close'].rolling(10).mean()
    df['ma30'] = df['close'].rolling(30).mean()

    # Volume moyen 24h (24 bougies H1)
    df['vol_moy_24h'] = df['volume'].rolling(24).mean()
    df['vol_ratio']   = df['volume'] / df['vol_moy_24h']

    # ATR en %
    df['atr_pct'] = df['atr'] / df['close'] * 100

    return df.dropna()

# ══════════════════════════════════════════════════════════════
# GÉNÉRATION DES SIGNAUX
# ══════════════════════════════════════════════════════════════

def generer_signal(row):
    """
    Applique exactement la même logique que le Bot Ultime V4.2.
    Retourne (score, direction) pour chaque bougie.
    """
    # Filtre ADX
    if row['adx'] < ADX_SEUIL:
        return 0, "NEUTRE"

    # Filtre Volume
    if row['vol_ratio'] < VOLUME_MINI:
        return 0, "NEUTRE"

    # Score RSI
    rsi = row['rsi']
    if rsi < 30:   score_rsi, direction_rsi = 10, "ACHAT"
    elif rsi < 40: score_rsi, direction_rsi = 6,  "ACHAT"
    elif rsi > 70: score_rsi, direction_rsi = 10, "VENTE"
    elif rsi > 60: score_rsi, direction_rsi = 6,  "VENTE"
    else:          score_rsi, direction_rsi = 2,  "NEUTRE"

    # Score MA
    direction_ma = "ACHAT" if row['ma10'] > row['ma30'] else "VENTE"
    ecart_ma     = abs(row['ma10'] - row['ma30']) / row['ma30'] * 100
    if ecart_ma > 1:     score_ma = 10
    elif ecart_ma > 0.5: score_ma = 6
    else:                score_ma = 2

    # Score ATR
    atr_pct = row['atr_pct']
    if atr_pct > 2:     score_vol = 10
    elif atr_pct > 1:   score_vol = 6
    elif atr_pct > 0.5: score_vol = 3
    else:               score_vol = 1

    # Direction finale
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
    if row['adx'] > 25:
        score_total = min(score_total + 3, 30)

    score_total = min(score_total, 30)
    return score_total, direction_finale

# ══════════════════════════════════════════════════════════════
# SIMULATION DU TRADE
# ══════════════════════════════════════════════════════════════

def simuler_trade_backtest(df, idx_entree, direction):
    """
    Simule un trade depuis l'index d'entrée.
    Retourne (gain_net, duree, idx_sortie).
    """
    row_entree  = df.iloc[idx_entree]
    prix_entree = row_entree['close']
    atr         = row_entree['atr']

    # Stop dynamique ATR + Structure (10 dernières bougies)
    lookback = min(10, idx_entree)
    if direction == "ACHAT":
        stop_atr       = prix_entree - (atr * ATR_MULTIPLIER)
        stop_structure = df['low'].iloc[idx_entree-lookback:idx_entree].min()
        stop_loss      = min(stop_atr, stop_structure)
        prix_objectif  = prix_entree + (abs(prix_entree - stop_loss) * RATIO_RR)
    else:
        stop_atr       = prix_entree + (atr * ATR_MULTIPLIER)
        stop_structure = df['high'].iloc[idx_entree-lookback:idx_entree].max()
        stop_loss      = max(stop_atr, stop_structure)
        prix_objectif  = prix_entree - (abs(prix_entree - stop_loss) * RATIO_RR)

    distance_stop = abs(prix_entree - stop_loss)
    mise          = CAPITAL_INITIAL * MISE_PCT

    # Frais aller-retour + slippage
    frais_total = (FRAIS_PCT + SLIPPAGE_PCT) * 2 * mise * LEVIER

    # Simulation bougie par bougie (max 6h = 6 bougies H1)
    max_bougies = 6
    for i in range(idx_entree + 1, min(idx_entree + max_bougies + 1, len(df))):
        row = df.iloc[i]
        if direction == "ACHAT":
            if row['low'] <= stop_loss:
                pnl_brut = (stop_loss - prix_entree) / prix_entree * mise * LEVIER
                return round(pnl_brut - frais_total, 2), i - idx_entree, i, "PERDU"
            if row['high'] >= prix_objectif:
                pnl_brut = (prix_objectif - prix_entree) / prix_entree * mise * LEVIER
                return round(pnl_brut - frais_total, 2), i - idx_entree, i, "GAGNE"
        else:
            if row['high'] >= stop_loss:
                pnl_brut = (prix_entree - stop_loss) / prix_entree * mise * LEVIER
                return round(pnl_brut - frais_total, 2), i - idx_entree, i, "PERDU"
            if row['low'] <= prix_objectif:
                pnl_brut = (prix_entree - prix_objectif) / prix_entree * mise * LEVIER
                return round(pnl_brut - frais_total, 2), i - idx_entree, i, "GAGNE"

    # Timeout 6h → fermeture au prix de clôture
    if idx_entree + max_bougies < len(df):
        prix_sortie = df.iloc[idx_entree + max_bougies]['close']
        if direction == "ACHAT":
            pnl_brut = (prix_sortie - prix_entree) / prix_entree * mise * LEVIER
        else:
            pnl_brut = (prix_entree - prix_sortie) / prix_entree * mise * LEVIER
        resultat = "GAGNE" if pnl_brut > 0 else "PERDU"
        return round(pnl_brut - frais_total, 2), max_bougies, idx_entree + max_bougies, resultat

    return 0, 0, idx_entree + 1, "NEUTRE"

# ══════════════════════════════════════════════════════════════
# BACKTEST PRINCIPAL
# ══════════════════════════════════════════════════════════════

def lancer_backtest(symbole, df, score_min=18):
    """Lance le backtest complet sur un symbole."""
    print(f"\n  {'='*50}")
    print(f"  BACKTEST : {symbole} | Score min : {score_min}/30")
    print(f"  Période  : {df.index[0].strftime('%Y-%m-%d')} → {df.index[-1].strftime('%Y-%m-%d')}")
    print(f"  Bougies  : {len(df)} H1")
    print(f"  {'='*50}")

    trades      = []
    capital     = CAPITAL_INITIAL
    i           = 30  # On commence après 30 bougies pour avoir les MA

    while i < len(df) - 7:
        row           = df.iloc[i]
        score, direction = generer_signal(row)

        if score >= score_min and direction != "NEUTRE":
            gain, duree, idx_sortie, resultat = simuler_trade_backtest(df, i, direction)

            capital += gain
            trades.append({
                'date':      df.index[i].strftime('%Y-%m-%d %H:%M'),
                'direction': direction,
                'resultat':  resultat,
                'gain':      gain,
                'duree_h':   duree,
                'capital':   round(capital, 2),
                'score':     score,
                'adx':       round(row['adx'], 1),
                'rsi':       round(row['rsi'], 1)
            })

            # Skip les bougies du trade + 2h de pause
            i = idx_sortie + 2
        else:
            i += 1

    return trades, capital

# ══════════════════════════════════════════════════════════════
# ANALYSE DES RÉSULTATS
# ══════════════════════════════════════════════════════════════

def analyser_resultats(trades, capital_final, symbole, score_min):
    if not trades:
        print(f"\n  Aucun trade trouvé avec score >= {score_min}")
        return

    df_trades  = pd.DataFrame(trades)
    nb_trades  = len(trades)
    nb_wins    = len(df_trades[df_trades['resultat'] == 'GAGNE'])
    nb_losses  = len(df_trades[df_trades['resultat'] == 'PERDU'])
    win_rate   = nb_wins / nb_trades * 100
    gain_total = df_trades['gain'].sum()
    avg_win    = df_trades[df_trades['resultat']=='GAGNE']['gain'].mean() if nb_wins > 0 else 0
    avg_loss   = df_trades[df_trades['resultat']=='PERDU']['gain'].mean() if nb_losses > 0 else 0
    perf_pct   = (capital_final - CAPITAL_INITIAL) / CAPITAL_INITIAL * 100

    # Drawdown max
    capitals   = [CAPITAL_INITIAL] + [t['capital'] for t in trades]
    peak       = CAPITAL_INITIAL
    max_dd     = 0
    for c in capitals:
        if c > peak:
            peak = c
        dd = (c - peak) / peak * 100
        if dd < max_dd:
            max_dd = dd

    # Trades par semaine
    jours      = (pd.to_datetime(trades[-1]['date']) - pd.to_datetime(trades[0]['date'])).days
    semaines   = max(jours / 7, 1)
    trades_sem = nb_trades / semaines

    print(f"\n  {'='*55}")
    print(f"  RÉSULTATS BACKTEST — {symbole}")
    print(f"  {'='*55}")
    print(f"  Période analysée  : {jours} jours")
    print(f"  Trades total      : {nb_trades}")
    print(f"  Trades/semaine    : {round(trades_sem, 1)}")
    print(f"  Victoires         : {nb_wins} ({round(win_rate, 1)}%)")
    print(f"  Défaites          : {nb_losses}")
    print(f"  Gain moyen win    : +{round(avg_win, 2)}EUR")
    print(f"  Perte moyenne     : {round(avg_loss, 2)}EUR")
    print(f"  Capital initial   : {CAPITAL_INITIAL}EUR")
    print(f"  Capital final     : {round(capital_final, 2)}EUR")
    print(f"  Performance       : {'+' if perf_pct >= 0 else ''}{round(perf_pct, 1)}%")
    print(f"  Gain total net    : {'+' if gain_total >= 0 else ''}{round(gain_total, 2)}EUR")
    print(f"  Drawdown max      : {round(max_dd, 1)}%")
    print(f"  {'='*55}")

    # Afficher les 10 derniers trades
    print(f"\n  Derniers trades :")
    for t in trades[-10:]:
        icone = "✅" if t['resultat'] == "GAGNE" else "❌"
        print(f"    {icone} {t['date']} | {t['direction']} | "
              f"{'+' if t['gain'] >= 0 else ''}{t['gain']}EUR | "
              f"Score {t['score']} | ADX {t['adx']} | RSI {t['rsi']} | "
              f"{t['duree_h']}h | Capital: {t['capital']}EUR")

    return {
        'symbole': symbole,
        'nb_trades': nb_trades,
        'trades_semaine': round(trades_sem, 1),
        'win_rate': round(win_rate, 1),
        'performance': round(perf_pct, 1),
        'gain_total': round(gain_total, 2),
        'drawdown_max': round(max_dd, 1)
    }

# ══════════════════════════════════════════════════════════════
# TEST AVEC DIFFÉRENTS SCORE_MIN
# ══════════════════════════════════════════════════════════════

def tester_score_min(df, symbole):
    """Compare les résultats avec différents score min."""
    print(f"\n  {'='*55}")
    print(f"  COMPARAISON SCORE MIN — {symbole}")
    print(f"  {'='*55}")
    print(f"  {'Score':>6} | {'Trades':>6} | {'T/sem':>5} | {'WinRate':>7} | {'Perf%':>6} | {'MaxDD%':>6}")
    print(f"  {'-'*55}")

    for score in [15, 16, 17, 18, 20]:
        trades, capital = lancer_backtest(symbole, df, score_min=score)
        if trades:
            df_t     = pd.DataFrame(trades)
            nb       = len(trades)
            wins     = len(df_t[df_t['resultat']=='GAGNE'])
            wr       = wins / nb * 100
            gain     = df_t['gain'].sum()
            perf     = (capital - CAPITAL_INITIAL) / CAPITAL_INITIAL * 100
            jours    = (pd.to_datetime(trades[-1]['date']) - pd.to_datetime(trades[0]['date'])).days
            sem      = nb / max(jours/7, 1)

            capitals = [CAPITAL_INITIAL] + [t['capital'] for t in trades]
            peak     = CAPITAL_INITIAL
            max_dd   = 0
            for c in capitals:
                if c > peak: peak = c
                dd = (c - peak) / peak * 100
                if dd < max_dd: max_dd = dd

            print(f"  {score:>6} | {nb:>6} | {round(sem,1):>5} | {round(wr,1):>6}% | "
                  f"{'+' if perf>=0 else ''}{round(perf,1):>5}% | {round(max_dd,1):>5}%")
        else:
            print(f"  {score:>6} | {'0':>6} | {'0':>5} | {'N/A':>7} | {'N/A':>6} | {'N/A':>6}")

# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

def main():
    print("=" * 55)
    print("  BACKTESTER BOT ULTIME V4.2")
    print(f"  Frais : {FRAIS_PCT*100}% | Slippage : {SLIPPAGE_PCT*100}%")
    print(f"  Capital : {CAPITAL_INITIAL}EUR | Levier : x{LEVIER}")
    print(f"  Période : 6 mois de données H1")
    print("=" * 55)

    resultats = []

    for symbole in MARCHES:
        # Télécharge 6 mois de données
        df = get_historical_data(symbole, jours=180)
        if df is None or len(df) < 100:
            print(f"  Impossible de récupérer les données {symbole}")
            continue

        # Ajoute les indicateurs
        df = ajouter_indicateurs(df)
        print(f"  {len(df)} bougies valides après calcul des indicateurs")

        # Backtest principal avec score 18
        trades, capital = lancer_backtest(symbole, df, score_min=SCORE_MIN)
        result = analyser_resultats(trades, capital, symbole, SCORE_MIN)
        if result:
            resultats.append(result)

        # Comparaison des score min
        tester_score_min(df, symbole)

        time.sleep(2)

    # Synthèse finale
    if resultats:
        print(f"\n  {'='*55}")
        print(f"  SYNTHÈSE GLOBALE")
        print(f"  {'='*55}")
        for r in resultats:
            print(f"  {r['symbole']} : {r['nb_trades']} trades | "
                  f"WR {r['win_rate']}% | "
                  f"Perf {'+' if r['performance']>=0 else ''}{r['performance']}% | "
                  f"MaxDD {r['drawdown_max']}%")
        print(f"\n  Recommandation score min optimal : voir tableau comparatif ci-dessus")
        print(f"  {'='*55}")

if __name__ == "__main__":
    main()
