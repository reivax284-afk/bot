import requests
import json
from datetime import datetime, timedelta

# === CONFIGURATION ===
SYMBOL_ETH = "ETHUSDT"
SYMBOL_SOL = "SOLUSDT"
INITIAL_BET = 5.0
LEVERAGE = 3
TARGET_MULTIPLIER = 3  # x3 objectif
DAYS_BACKTEST = 90  # Nombre de jours à backtester

def get_klines(symbol, interval="1d", limit=100):
    """Récupère les données historiques depuis api.binance.com (spot)"""
    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        candles = []
        for candle in data:
            candles.append({
                "open_time": candle[0],
                "open":  float(candle[1]),
                "high":  float(candle[2]),
                "low":   float(candle[3]),
                "close": float(candle[4]),
                "volume": float(candle[5]),
            })
        return candles
    except Exception as e:
        print(f"Erreur récupération données {symbol}: {e}")
        return []

def simulate_trade(candle, bet, leverage):
    """
    Simule un trade sur une bougie journalière.
    Stratégie : on prend la direction de la bougie (haussière ou baissière).
    - Si close > open → LONG
    - Si close < open → SHORT
    Résultat avec levier x3.
    """
    open_price = candle["open"]
    close_price = candle["close"]
    
    price_change_pct = (close_price - open_price) / open_price  # ex: +0.02 = +2%
    
    # On suit la direction de la bougie
    if close_price >= open_price:
        direction = "LONG"
        pnl_pct = price_change_pct * leverage
    else:
        direction = "SHORT"
        pnl_pct = -price_change_pct * leverage  # short profite quand ça baisse
    
    pnl = bet * pnl_pct
    won = pnl > 0
    
    return {
        "direction": direction,
        "open": open_price,
        "close": close_price,
        "change_pct": price_change_pct * 100,
        "pnl_pct": pnl_pct * 100,
        "pnl": pnl,
        "won": won
    }

def run_backtest(symbol, candles):
    """Lance le backtest avec stratégie martingale"""
    print(f"\n{'='*60}")
    print(f"BACKTEST MARTINGALE — {symbol}")
    print(f"Mise de départ: {INITIAL_BET}€ | Levier: x{LEVERAGE} | {len(candles)} jours")
    print(f"{'='*60}")
    
    bet = INITIAL_BET
    total_profit = 0.0
    total_invested = 0.0
    wins = 0
    losses = 0
    max_bet = INITIAL_BET
    max_drawdown = 0.0
    consecutive_losses = 0
    max_consecutive_losses = 0
    
    results = []
    
    for i, candle in enumerate(candles):
        date = datetime.fromtimestamp(candle["open_time"] / 1000).strftime("%Y-%m-%d")
        
        trade = simulate_trade(candle, bet, LEVERAGE)
        total_invested += bet
        
        if trade["won"]:
            # Gain : on encaisse et on repart à la mise initiale
            profit = bet * (TARGET_MULTIPLIER - 1)  # x3 donc profit = mise x2
            total_profit += profit
            wins += 1
            consecutive_losses = 0
            result_str = f"✅ GAGNÉ  +{profit:.2f}€"
            next_bet = INITIAL_BET
        else:
            # Perte : on double la mise
            total_profit -= bet
            losses += 1
            consecutive_losses += 1
            max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
            result_str = f"❌ PERDU  -{bet:.2f}€"
            next_bet = bet * 2
        
        if bet > max_bet:
            max_bet = bet
        
        cumulative = total_profit
        
        print(f"Jour {i+1:3d} | {date} | {trade['direction']:5s} | "
              f"Mise: {bet:8.2f}€ | {result_str} | "
              f"Cumul: {cumulative:+.2f}€")
        
        results.append({
            "day": i + 1,
            "date": date,
            "bet": bet,
            "won": trade["won"],
            "profit": total_profit
        })
        
        bet = next_bet
    
    # === RÉSUMÉ FINAL ===
    print(f"\n{'='*60}")
    print(f"RÉSUMÉ FINAL — {symbol}")
    print(f"{'='*60}")
    print(f"Jours tradés       : {len(candles)}")
    print(f"Trades gagnés      : {wins} ({wins/len(candles)*100:.1f}%)")
    print(f"Trades perdus      : {losses} ({losses/len(candles)*100:.1f}%)")
    print(f"Profit net total   : {total_profit:+.2f}€")
    print(f"Mise max atteinte  : {max_bet:.2f}€")
    print(f"Pertes consécutives max : {max_consecutive_losses}")
    print(f"Capital nécessaire : ~{max_bet * 2:.2f}€ (sécurité x2)")
    print(f"{'='*60}\n")
    
    return results

def main():
    print("🚀 Démarrage du backtesting Martingale...")
    print(f"📅 Date : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📊 Récupération des données depuis api.binance.com...\n")
    
    # Récupération des données ETH
    eth_candles = get_klines(SYMBOL_ETH, "1d", DAYS_BACKTEST)
    if eth_candles:
        run_backtest(SYMBOL_ETH, eth_candles)
    else:
        print(f"❌ Impossible de récupérer les données pour {SYMBOL_ETH}")
    
    # Récupération des données SOL
    sol_candles = get_klines(SYMBOL_SOL, "1d", DAYS_BACKTEST)
    if sol_candles:
        run_backtest(SYMBOL_SOL, sol_candles)
    else:
        print(f"❌ Impossible de récupérer les données pour {SYMBOL_SOL}")
    
    print("✅ Backtesting terminé !")

if __name__ == "__main__":
    main()
