import requests
from datetime import datetime
import time

# === CONFIGURATION ===
INITIAL_BET   = 5.0
LEVERAGE      = 3
OBJECTIF_PCT  = 0.15   # 5% de mouvement sur le prix = +15% sur la mise avec levier x3
GAIN_RATIO    = LEVERAGE * OBJECTIF_PCT   # = 0.15 soit +15% de la mise
STOP_PCT      = 0.15   # Stop-loss symétrique à 5%
DAYS_BACKTEST = 90

def get_klines_coingecko(coin_id, days=90):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
    params = {"vs_currency": "usd", "days": str(days)}
    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        seen = set()
        daily = []
        for item in data:
            day = datetime.fromtimestamp(item[0]/1000).strftime("%Y-%m-%d")
            if day not in seen:
                seen.add(day)
                daily.append({
                    "open_time": item[0],
                    "open":  float(item[1]),
                    "high":  float(item[2]),
                    "low":   float(item[3]),
                    "close": float(item[4]),
                })
        return daily[-days:]
    except Exception as e:
        print(f"Erreur CoinGecko ({coin_id}): {e}")
        return []

def simulate_trade(candle, bet, direction):
    """
    Simule un trade avec objectif 5% et stop-loss 5%.
    On regarde si le high/low de la bougie a atteint l'objectif ou le stop.
    """
    open_price = candle["open"]
    high       = candle["high"]
    low        = candle["low"]

    if direction == "LONG":
        prix_objectif  = open_price * (1 + OBJECTIF_PCT)
        prix_stop      = open_price * (1 - STOP_PCT)
        # Si le high atteint l'objectif → gagné
        if high >= prix_objectif:
            gain = round(bet * GAIN_RATIO, 2)
            return "GAGNE", gain
        # Si le low atteint le stop → perdu
        elif low <= prix_stop:
            return "PERDU", -bet
        else:
            # Ni l'un ni l'autre → on ferme au close
            pnl = (candle["close"] - open_price) / open_price * LEVERAGE
            gain = round(bet * pnl, 2)
            return ("GAGNE" if gain > 0 else "PERDU"), gain
    else:  # SHORT
        prix_objectif  = open_price * (1 - OBJECTIF_PCT)
        prix_stop      = open_price * (1 + STOP_PCT)
        if low <= prix_objectif:
            gain = round(bet * GAIN_RATIO, 2)
            return "GAGNE", gain
        elif high >= prix_stop:
            return "PERDU", -bet
        else:
            pnl = (open_price - candle["close"]) / open_price * LEVERAGE
            gain = round(bet * pnl, 2)
            return ("GAGNE" if gain > 0 else "PERDU"), gain

def run_backtest(symbol_name, candles):
    print(f"\n{'='*62}")
    print(f"  BACKTEST REALISTE — {symbol_name}")
    print(f"  Mise: {INITIAL_BET}EUR | Levier: x{LEVERAGE} | Objectif: +{int(OBJECTIF_PCT*100)}% | Stop: -{int(STOP_PCT*100)}%")
    print(f"  Gain si gagne : +{round(INITIAL_BET*GAIN_RATIO,2)}EUR | Perte si perdu : -{INITIAL_BET}EUR")
    print(f"{'='*62}")

    bet = INITIAL_BET
    total_profit = 0.0
    wins = 0
    losses = 0
    max_bet = INITIAL_BET
    max_consecutive_losses = 0
    consecutive_losses = 0

    for i, candle in enumerate(candles):
        date = datetime.fromtimestamp(candle["open_time"]/1000).strftime("%Y-%m-%d")

        # Direction : on suit la tendance (close vs open)
        direction = "LONG" if candle["close"] >= candle["open"] else "SHORT"

        resultat, gain = simulate_trade(candle, bet, direction)

        total_profit += gain

        if resultat == "GAGNE":
            wins += 1
            consecutive_losses = 0
            result_str = f"GAGNE +{gain:5.2f}EUR"
            next_bet = INITIAL_BET
        else:
            losses += 1
            consecutive_losses += 1
            max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
            result_str = f"PERDU {gain:6.2f}EUR"
            next_bet = bet * 2

        if bet > max_bet:
            max_bet = bet

        print(f"  J{i+1:03d} | {date} | {direction:5s} | Mise:{bet:8.2f}EUR | {result_str} | Cumul:{total_profit:+8.2f}EUR")
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
    print("="*62)
    print("  BACKTEST REALISTE — OBJECTIF 5% | STOP 5%")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*62)

    eth = get_klines_coingecko("ethereum", DAYS_BACKTEST)
    if eth:
        print(f"\n  OK : {len(eth)} bougies ETH")
        run_backtest("ETH/USDT", eth)

    time.sleep(2)

    sol = get_klines_coingecko("solana", DAYS_BACKTEST)
    if sol:
        print(f"\n  OK : {len(sol)} bougies SOL")
        run_backtest("SOL/USDT", sol)

    print("  Backtest termine !")

if __name__ == "__main__":
    main()
