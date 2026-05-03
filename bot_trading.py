"""
╔══════════════════════════════════════════════════════════════╗
║          BOT DE TRADING — MARTINGALE JOURNALIÈRE             ║
║          Levier x3 · ETH/USDT & SOL/USDT · Binance          ║
╚══════════════════════════════════════════════════════════════╝
"""

import requests
import json
import time
import hashlib
import hmac
import os
from datetime import datetime

# ══════════════════════════════════════════════════════════════
# ⚙️  CONFIGURATION — Clés lues depuis Railway automatiquement
# ══════════════════════════════════════════════════════════════

API_KEY    = os.environ.get("API_KEY", "")
API_SECRET = os.environ.get("API_SECRET", "")

MODE_TEST   = True
MISE_DEPART = 5.0
LEVIER      = 3
MARCHES     = ["ETHUSDT", "SOLUSDT"]
FICHIER_ETAT = "etat_bot.json"

BASE_URL = "https://testnet.binancefuture.com" if MODE_TEST else "https://fapi.binance.com"

# ══════════════════════════════════════════════════════════════
# 💾  ÉTAT DU BOT
# ══════════════════════════════════════════════════════════════

def charger_etat():
    if os.path.exists(FICHIER_ETAT):
        with open(FICHIER_ETAT, "r") as f:
            return json.load(f)
    return {"mise_actuelle": MISE_DEPART, "pertes_consecutives": 0,
            "total_perdu": 0.0, "total_gagne": 0.0, "cumul_net": 0.0,
            "trade_du_jour_fait": False, "date_dernier_trade": "", "historique": []}

def sauvegarder_etat(etat):
    with open(FICHIER_ETAT, "w") as f:
        json.dump(etat, f, indent=2, ensure_ascii=False)
    print("✅ État sauvegardé")

# ══════════════════════════════════════════════════════════════
# 🔐  SÉCURITÉ
# ══════════════════════════════════════════════════════════════

def signer_requete(params):
    query = "&".join([f"{k}={v}" for k, v in params.items()])
    signature = hmac.new(API_SECRET.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
    params["signature"] = signature
    return params

def headers():
    return {"X-MBX-APIKEY": API_KEY}

# ══════════════════════════════════════════════════════════════
# 📊  DONNÉES
# ══════════════════════════════════════════════════════════════

def get_klines(symbole, intervalle="1h", limite=100):
    try:
        r = requests.get(f"{BASE_URL}/fapi/v1/klines",
                         params={"symbol": symbole, "interval": intervalle, "limit": limite}, timeout=10)
        data = r.json()
        return [float(k[4]) for k in data], [float(k[2]) for k in data], [float(k[3]) for k in data]
    except Exception as e:
        print(f"❌ Erreur données {symbole} : {e}")
        return None, None, None

def get_prix_actuel(symbole):
    try:
        r = requests.get(f"{BASE_URL}/fapi/v1/ticker/price", params={"symbol": symbole}, timeout=10)
        return float(r.json()["price"])
    except Exception as e:
        print(f"❌ Erreur prix : {e}")
        return None

# ══════════════════════════════════════════════════════════════
# 📈  INDICATEURS
# ══════════════════════════════════════════════════════════════

def calculer_rsi(closes, periode=14):
    if len(closes) < periode + 1:
        return 50
    gains, pertes = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(diff if diff > 0 else 0)
        pertes.append(abs(diff) if diff < 0 else 0)
    mg, mp = sum(gains[-periode:]) / periode, sum(pertes[-periode:]) / periode
    return round(100 - (100 / (1 + mg/mp)), 2) if mp != 0 else 100

def calculer_ma(closes, periode):
    return sum(closes[-periode:]) / periode if len(closes) >= periode else None

def calculer_volatilite(closes, highs, lows, periode=14):
    if len(closes) < periode:
        return 0
    return round(sum((highs[i] - lows[i]) / closes[i] * 100 for i in range(-periode, 0)) / periode, 2)

# ══════════════════════════════════════════════════════════════
# 🎯  SCORING
# ══════════════════════════════════════════════════════════════

def scorer_marche(symbole):
    print(f"\n📊 Analyse {symbole}...")
    closes, highs, lows = get_klines(symbole)
    if closes is None:
        return 0, "NEUTRE", {}

    rsi = calculer_rsi(closes)
    ma_c, ma_l = calculer_ma(closes, 10), calculer_ma(closes, 30)
    vol = calculer_volatilite(closes, highs, lows)

    if rsi < 25:   score_rsi, direction = 10, "ACHAT"
    elif rsi < 30: score_rsi, direction = 8,  "ACHAT"
    elif rsi < 40: score_rsi, direction = 5,  "ACHAT"
    elif rsi > 75: score_rsi, direction = 10, "VENTE"
    elif rsi > 70: score_rsi, direction = 8,  "VENTE"
    elif rsi > 60: score_rsi, direction = 5,  "VENTE"
    else:          score_rsi, direction = 2,  "NEUTRE"

    if ma_c and ma_l:
        ecart = abs(ma_c - ma_l) / ma_l * 100
        dir_ma = "ACHAT" if ma_c > ma_l else "VENTE"
        score_ma = 10 if ecart > 2 else 7 if ecart > 1 else 4 if ecart > 0.5 else 1
    else:
        score_ma, dir_ma = 0, "NEUTRE"

    score_vol = 10 if vol > 3 else 8 if vol > 2 else 5 if vol > 1 else 3 if vol > 0.5 else 1
    score_total = score_rsi + score_ma + score_vol
    if direction == "NEUTRE":
        direction = dir_ma

    print(f"   RSI:{rsi} MA:{score_ma}/10 Vol:{vol}% → Score:{score_total}/30 ({direction})")
    return score_total, direction, {"score_total": score_total}

def choisir_meilleur_marche():
    print("\n🔍 SÉLECTION DU MARCHÉ DU JOUR")
    resultats = {}
    for m in MARCHES:
        score, direction, details = scorer_marche(m)
        resultats[m] = {"score": score, "direction": direction, "details": details}
        time.sleep(0.5)
    meilleur = max(resultats, key=lambda x: resultats[x]["score"])
    print(f"🏆 CHOIX : {meilleur} ({resultats[meilleur]['score']}/30)")
    return meilleur, resultats[meilleur]["direction"], resultats[meilleur]["details"]

# ══════════════════════════════════════════════════════════════
# 💰  ORDRES
# ══════════════════════════════════════════════════════════════

def configurer_levier(symbole):
    params = signer_requete({"symbol": symbole, "leverage": LEVIER, "timestamp": int(time.time() * 1000)})
    try:
        r = requests.post(f"{BASE_URL}/fapi/v1/leverage", params=params, headers=headers(), timeout=10)
        if "leverage" in r.json():
            print(f"✅ Levier x{LEVIER} OK")
            return True
    except Exception as e:
        print(f"❌ Erreur levier : {e}")
    return False

def get_precision(symbole):
    try:
        r = requests.get(f"{BASE_URL}/fapi/v1/exchangeInfo", timeout=10)
        for s in r.json()["symbols"]:
            if s["symbol"] == symbole:
                return s["quantityPrecision"]
    except:
        pass
    return 3

def placer_ordre(symbole, direction, mise_usdt):
    prix = get_prix_actuel(symbole)
    if prix is None:
        return None
    quantite = round((mise_usdt * LEVIER) / prix, get_precision(symbole))
    side = "BUY" if direction == "ACHAT" else "SELL"
    prix_obj = round(prix * 1.333, 2) if direction == "ACHAT" else round(prix * 0.667, 2)
    prix_sl  = round(prix * 0.667, 2) if direction == "ACHAT" else round(prix * 1.333, 2)

    params = signer_requete({"symbol": symbole, "side": side, "type": "MARKET",
                              "quantity": quantite, "timestamp": int(time.time() * 1000)})
    print(f"📤 TRADE : {symbole} {direction} {mise_usdt}€ | Obj:{prix_obj} SL:{prix_sl}")
    try:
        r = requests.post(f"{BASE_URL}/fapi/v1/order", params=params, headers=headers(), timeout=10)
        data = r.json()
        if "orderId" in data:
            print(f"✅ Trade #{data['orderId']}")
            return {"ordre_id": data["orderId"], "symbole": symbole, "direction": direction,
                    "mise": mise_usdt, "quantite": quantite, "prix_objectif": prix_obj, "prix_stop_loss": prix_sl}
        print(f"❌ Erreur : {data}")
    except Exception as e:
        print(f"❌ Erreur : {e}")
    return None

def fermer_position(symbole, direction, quantite):
    side = "SELL" if direction == "ACHAT" else "BUY"
    params = signer_requete({"symbol": symbole, "side": side, "type": "MARKET",
                              "quantity": quantite, "reduceOnly": "true", "timestamp": int(time.time() * 1000)})
    try:
        r = requests.post(f"{BASE_URL}/fapi/v1/order", params=params, headers=headers(), timeout=10)
        if "orderId" in r.json():
            print("✅ Position fermée")
            return True
    except Exception as e:
        print(f"❌ Erreur fermeture : {e}")
    return False

# ══════════════════════════════════════════════════════════════
# 👁️  SURVEILLANCE
# ══════════════════════════════════════════════════════════════

def surveiller_trade(trade):
    print(f"\n👁️  Surveillance | Obj:{trade['prix_objectif']} | SL:{trade['prix_stop_loss']}")
    while True:
        prix = get_prix_actuel(trade["symbole"])
        if prix is None:
            time.sleep(30)
            continue
        h = datetime.now().strftime("%H:%M:%S")
        if trade["direction"] == "ACHAT":
            if prix >= trade["prix_objectif"]:
                print(f"🎉 [{h}] GAGNÉ ! {prix}")
                fermer_position(trade["symbole"], trade["direction"], trade["quantite"])
                return "GAGNÉ", trade["mise"] * 2
            elif prix <= trade["prix_stop_loss"]:
                print(f"❌ [{h}] STOP-LOSS ! {prix}")
                fermer_position(trade["symbole"], trade["direction"], trade["quantite"])
                return "PERDU", -trade["mise"]
        else:
            if prix <= trade["prix_objectif"]:
                print(f"🎉 [{h}] GAGNÉ ! {prix}")
                fermer_position(trade["symbole"], trade["direction"], trade["quantite"])
                return "GAGNÉ", trade["mise"] * 2
            elif prix >= trade["prix_stop_loss"]:
                print(f"❌ [{h}] STOP-LOSS ! {prix}")
                fermer_position(trade["symbole"], trade["direction"], trade["quantite"])
                return "PERDU", -trade["mise"]
        print(f"   [{h}] Prix:{prix}")
        time.sleep(60)

# ══════════════════════════════════════════════════════════════
# 🚀  TRADE DU JOUR
# ══════════════════════════════════════════════════════════════

def trade_du_jour():
    print(f"\n{'█'*50}\n█ BOT MARTINGALE — {datetime.now().strftime('%d/%m/%Y %H:%M')}\n{'█'*50}")
    etat = charger_etat()

    aujourd_hui = datetime.now().strftime("%Y-%m-%d")
    if etat["trade_du_jour_fait"] and etat["date_dernier_trade"] == aujourd_hui:
        print("⚠️  Trade du jour déjà fait.")
        return

    mise = etat["mise_actuelle"]
    print(f"💰 Mise : {mise}€ | Objectif : +{mise*2}€ net")

    symbole, direction, details = choisir_meilleur_marche()
    if direction == "NEUTRE":
        print("⚠️  Pas de signal. On passe.")
        return

    if not configurer_levier(symbole):
        return

    trade = placer_ordre(symbole, direction, mise)
    if trade is None:
        return

    etat["trade_du_jour_fait"] = True
    etat["date_dernier_trade"] = aujourd_hui
    sauvegarder_etat(etat)

    resultat, gain = surveiller_trade(trade)

    if resultat == "GAGNÉ":
        etat["total_gagne"] += abs(gain)
    else:
        etat["total_perdu"] += abs(gain)

    etat["cumul_net"] = round(etat["total_gagne"] - etat["total_perdu"], 2)
    etat["historique"].append({"date": aujourd_hui, "marche": symbole, "mise": mise,
                                "resultat": resultat, "gain": round(gain, 2), "cumul": etat["cumul_net"]})

    if resultat == "GAGNÉ":
        etat["mise_actuelle"] = MISE_DEPART
        etat["pertes_consecutives"] = 0
    else:
        etat["mise_actuelle"] *= 2
        etat["pertes_consecutives"] += 1

    etat["trade_du_jour_fait"] = False
    sauvegarder_etat(etat)

    print(f"\n📊 {resultat} | {'+' if gain >= 0 else ''}{round(gain,2)}€ | Cumul:{etat['cumul_net']}€ | Demain:{etat['mise_actuelle']}€")

# ══════════════════════════════════════════════════════════════
# ▶️  DÉMARRAGE
# ══════════════════════════════════════════════════════════════

def demarrer_bot():
    print(f"\n🚀 BOT MARTINGALE — {'TEST' if MODE_TEST else 'RÉEL'} | {', '.join(MARCHES)} | {MISE_DEPART}€/j | x{LEVIER}")

    if not API_KEY or not API_SECRET:
        print("❌ Clés API manquantes dans les Variables Railway !")
        return

    print("✅ Clés API OK — Démarrage...")

    while True:
        try:
            trade_du_jour()
        except KeyboardInterrupt:
            print("\n⛔ Bot arrêté.")
            break
        except Exception as e:
            print(f"\n❌ Erreur : {e}")
        print("⏰ Prochaine vérification dans 1h...")
        time.sleep(3600)

if __name__ == "__main__":
    demarrer_bot()
