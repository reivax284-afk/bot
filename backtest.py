import requests
import json
from datetime import datetime, timedelta
import time

# === CONFIGURATION ===
INITIAL_BET = 5.0
LEVERAGE = 3
TARGET_MULTIPLIER = 3
DAYS_BACKTEST = 90

def get_klines_coingecko(coin_id, days=90):
    """
    Recupere les donnees historiques depuis CoinGecko (sans restriction geo).
    coin_id : 'ethereum' ou 'solana'
    """
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
    params = {
        "vs_currency": "usd",
        "days": str(days)
    }
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        candles = []
        for item in data:
            candles.append({
                "open_time": item[0],
                "open":  float(item[1]),
                "high":  float(item[2]),
                "low":   float(item[3]),
                "close": float(item[4]),
            })
        seen_days = set()
        daily_candles = []
        for c in candles:
            day_str = datetime.fromtimestamp(c["open_time"] / 1000).strftime("%Y-%m-%d")
            if day_str not in seen_days:
                seen_days.add(day_str)
                daily_candles.append(c)
        return daily_candles[-days:]
    except Exception as e:
        print(f"  Erreur CoinGecko ({coin_id}): {e}")
        return []

def simulate_trade_realistic(candle):
    open_price = candle["open"]
    close_price = candle["close"]
    change_pct = abs((close_price - open_price) / open_price) * 100
    won = change_pct > 1.5
    return {"open": open_price, "close": close_price, "change_pct": change_pct, "won": won}

def run_backtest(symbol_name, candles):
    print(f"\n{'='*62}")
    print(f"  BACKTEST MARTINGALE — {symbol_name}")
    print(f"  Mise depart: {INITIAL_BET}EUR | Levier: x{LEVERAGE} | {len(candles)} jours")
    print(f"{'='*62}")

    bet = INITIAL_BET
    total_profit = 0.0
    wins = 0
    losses = 0
    max_bet = INITIAL_BET
    max_consecutive_losses = 0
    consecutive_losses = 0

    for i, candle in enumerate(candles):
        date = datetime.fromtimestamp(candle["open_time"] / 1000).strftime("%Y-%m-%d")
        trade = simulate_trade_realistic(candle)

        if trade["won"]:
            profit = bet * (TARGET_MULTIPLIER - 1)
            total_profit += profit
            wins += 1
            consecutive_losses = 0
            result_str = f"GAGNE  +{profit:7.2f}EUR"
            next_bet = INITIAL_BET
        else:
            total_profit -= bet
            losses += 1
            consecutive_losses += 1
            max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
            result_str = f"PERDU  -{bet:7.2f}EUR"
            next_bet = bet * 2

        if bet > max_bet:
            max_bet = bet

        print(f"  J{i+1:03d} | {date} | Mise:{bet:8.2f}EUR | {result_str} | Cumul:{total_profit:+8.2f}EUR")
        bet = next_bet

    win_rate = wins / len(candles) * 100 if candles else 0
    print(f"\n{'='*62}")
    print(f"  RESUME — {symbol_name}")
    print(f"{'='*62}")
    print(f"  Jours trades            : {len(candles)}")
    print(f"  Victoires               : {wins} ({win_rate:.1f}%)")
    print(f"  Defaites                : {losses} ({100-win_rate:.1f}%)")
    print(f"  Profit net              : {total_profit:+.2f} EUR")
    print(f"  Mise maximale atteinte  : {max_bet:.2f} EUR")
    print(f"  Pertes consecutives max : {max_consecutive_losses}")
    print(f"  Capital min recommande  : {max_bet * 2:.2f} EUR")
    print(f"{'='*62}\n")

def main():
    print("=" * 62)
    print("  BOT MARTINGALE — BACKTESTING VIA COINGECKO")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 62)
    print(f"\n  Source : api.coingecko.com (sans restriction geo)")
    print(f"  Recuperation des donnees...\n")

    eth_candles = get_klines_coingecko("ethereum", DAYS_BACKTEST)
    if eth_candles:
        print(f"  OK : {len(eth_candles)} bougies ETH recuperees")
        run_backtest("ETH/USDT", eth_candles)
    else:
        print("  ERREUR : Impossible de recuperer ETH")

    time.sleep(2)

    sol_candles = get_klines_coingecko("solana", DAYS_BACKTEST)
    if sol_candles:
        print(f"  OK : {len(sol_candles)} bougies SOL recuperees")
        run_backtest("SOL/USDT", sol_candles)
    else:
        print("  ERREUR : Impossible de recuperer SOL")

    print("\n  Backtesting termine !")

if __name__ == "__main__":
    main()
