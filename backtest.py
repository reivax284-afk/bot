import requests
from datetime import datetime, timedelta
import time

# === CONFIGURATION ===
INITIAL_BET  = 5.0
LEVERAGE     = 3
OBJECTIF_PCT = 0.15   # 15% de mouvement
STOP_PCT     = 0.15   # Stop-loss 15%
GAIN_RATIO   = LEVERAGE * OBJECTIF_PCT  # 0.45 = +45% de la mise si gagné
DAYS         = 365

KRAKEN_SYMBOLS = {
    "ETH/USDT": "XETHZUSD",
    "SOL/USDT": "SOLUSDT"
}

def get_klines_kraken(symbol, days=92):
    """Récupère les bougies journalières depuis Kraken (gratuit, sans restriction)"""
    url = "https://api.kraken.com/0/public/OHLC"
    since = int((datetime.now() - timedelta(days=days+1)).timestamp())
    params = {
        "pair": symbol,
        "interval": 1440,  # 1440 minutes = 1 jour
        "since": since
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        if data.get("error"):
            print(f"  Erreur Kraken : {data['error']}")
            return []
        result = data.get("result", {})
        # Kraken retourne les données sous la clé du symbole (parfois différent)
        key = list(result.keys())[0] if result else None
        if not key or key == "last":
            print(f"  Pas de données pour {symbol}")
            return []
        candles = []
        for k in result[key]:
            candles.append({
                "open_time": int(k[0]) * 1000,
                "open":  float(k[1]),
                "high":  float(k[2]),
                "low":   float(k[3]),
                "close": float(k[4]),
            })
        return candles[-days:]
    except Exception as e:
        print(f"  Erreur Kraken ({symbol}): {e}")
        return []

def simulate_trade(candle, bet, direction):
    open_price = candle["open"]
    high       = candle["high"]
    low        = candle["low"]
    close      = candle["close"]

    if direction == "LONG":
        prix_objectif = open_price * (1 + OBJECTIF_PCT)
        prix_stop     = open_price * (1 - STOP_PCT)
        if high >= prix_objectif:
            return "GAGNE", round(bet * GAIN_RATIO, 2)
        elif low <= prix_stop:
            return "PERDU", -bet
        else:
            pnl = (close - open_price) / open_price * LEVERAGE
            gain = round(bet * pnl, 2)
            return ("GAGNE" if gain > 0 else "PERDU"), gain
    else:  # SHORT
        prix_objectif = open_price * (1 - OBJECTIF_PCT)
        prix_stop     = open_price * (1 + STOP_PCT)
        if low <= prix_objectif:
            return "GAGNE", round(bet * GAIN_RATIO, 2)
        elif high >= prix_stop:
            return "PERDU", -bet
        else:
            pnl = (open_price - close) / open_price * LEVERAGE
            gain = round(bet * pnl, 2)
            return ("GAGNE" if gain > 0 else "PERDU"), gain

def run_backtest(symbol_name, candles):
    print(f"\n{'='*65}")
    print(f"  BACKTEST — {symbol_name}")
    print(f"  Mise: {INITIAL_BET}EUR | Levier: x{LEVERAGE} | Objectif: +{int(OBJECTIF_PCT*100)}% | Stop: -{int(STOP_PCT*100)}%")
    print(f"  Gain si gagne: +{round(INITIAL_BET*GAIN_RATIO,2)}EUR | Perte si perdu: -{INITIAL_BET}EUR")
    print(f"{'='*65}")

    bet = INITIAL_BET
    total_profit = 0.0
    wins = 0
    losses = 0
    max_bet = INITIAL_BET
    max_consecutive_losses = 0
    consecutive_losses = 0

    for i, candle in enumerate(candles):
        date      = datetime.fromtimestamp(candle["open_time"]/1000).strftime("%Y-%m-%d")
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
    print(f"\n{'='*65}")
    print(f"  RESUME — {symbol_name}")
    print(f"{'='*65}")
    print(f"  Jours trades            : {len(candles)}")
    print(f"  Victoires               : {wins} ({win_rate:.1f}%)")
    print(f"  Defaites                : {losses} ({100-win_rate:.1f}%)")
    print(f"  Profit net              : {total_profit:+.2f} EUR")
    print(f"  Mise maximale atteinte  : {max_bet:.2f} EUR")
    print(f"  Pertes consecutives max : {max_consecutive_losses}")
    print(f"  Capital min recommande  : {max_bet * 2:.2f} EUR")
    print(f"{'='*65}\n")

def main():
    print("="*65)
    print("  BACKTEST MARTINGALE — KRAKEN API — 365 JOURS REELS")
    print(f"  Objectif: 15% | Stop: 15% | Levier: x3 | Mise: {INITIAL_BET}EUR")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*65)

    for symbol_name, kraken_symbol in KRAKEN_SYMBOLS.items():
        print(f"\n  Recuperation {symbol_name} depuis Kraken...")
        candles = get_klines_kraken(kraken_symbol, DAYS)
        if candles:
            print(f"  OK : {len(candles)} bougies journalieres recuperees")
            run_backtest(symbol_name, candles)
        else:
            print(f"  ERREUR : Impossible de recuperer {symbol_name}")
        time.sleep(1)

    print("  Backtest termine !")

if __name__ == "__main__":
    main()
