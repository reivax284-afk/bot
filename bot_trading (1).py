"""
╔══════════════════════════════════════════════════════════════╗
║          BOT DE TRADING — MARTINGALE JOURNALIÈRE             ║
║          Levier x3 · ETH/USDT & SOL/USDT · Binance          ║
╚══════════════════════════════════════════════════════════════╝

STRATÉGIE :
- 1 seul trade par jour
- Levier x3 → objectif tripler la mise
- Tant que tu gagnes → on reste à 5€
- Si tu perds → on double le lendemain
- On ne s'arrête jamais tant qu'on n'a pas récupéré
- Le bot choisit automatiquement ETH ou SOL selon le meilleur signal
"""

import requests
import json
import time
import math
import hashlib
import hmac
import os
from datetime import datetime, timedelta

# ══════════════════════════════════════════════════════════════
# ⚙️  CONFIGURATION — À MODIFIER AVEC TES INFORMATIONS
# ══════════════════════════════════════════════════════════════

API_KEY    = "METS_TA_CLÉ_API_BINANCE_ICI"
API_SECRET = "METS_TON_SECRET_API_BINANCE_ICI"

# Mode TEST (True = paper trading sans argent réel / False = argent réel)
MODE_TEST = True

# Mise de départ en USDT (équivalent euros)
MISE_DEPART = 5.0

# Levier utilisé
LEVIER = 3

# Marchés analysés
MARCHES = ["ETHUSDT", "SOLUSDT"]

# Fichier de sauvegarde de l'état du bot
FICHIER_ETAT = "etat_bot.json"

# ══════════════════════════════════════════════════════════════
# 🌐  URLS BINANCE
# ══════════════════════════════════════════════════════════════

if MODE_TEST:
    BASE_URL = "https://testnet.binancefuture.com"
else:
    BASE_URL = "https://fapi.binance.com"

# ══════════════════════════════════════════════════════════════
# 💾  GESTION DE L'ÉTAT DU BOT (sauvegarde entre les jours)
# ══════════════════════════════════════════════════════════════

def charger_etat():
    """Charge l'état sauvegardé du bot (mise actuelle, historique)"""
    if os.path.exists(FICHIER_ETAT):
        with open(FICHIER_ETAT, "r") as f:
            return json.load(f)
    # Premier démarrage — état initial
    return {
        "mise_actuelle": MISE_DEPART,
        "pertes_consecutives": 0,
        "total_perdu": 0.0,
        "total_gagné": 0.0,
        "cumul_net": 0.0,
        "trade_du_jour_fait": False,
        "date_dernier_trade": "",
        "historique": []
    }

def sauvegarder_etat(etat):
    """Sauvegarde l'état du bot pour le lendemain"""
    with open(FICHIER_ETAT, "w") as f:
        json.dump(etat, f, indent=2, ensure_ascii=False)
    print("✅ État sauvegardé")

# ══════════════════════════════════════════════════════════════
# 🔐  SIGNATURE BINANCE (sécurité des requêtes)
# ══════════════════════════════════════════════════════════════

def signer_requete(params):
    """Ajoute la signature sécurisée à la requête Binance"""
    query = "&".join([f"{k}={v}" for k, v in params.items()])
    signature = hmac.new(
        API_SECRET.encode("utf-8"),
        query.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    params["signature"] = signature
    return params

def headers():
    """Headers avec la clé API"""
    return {"X-MBX-APIKEY": API_KEY}

# ══════════════════════════════════════════════════════════════
# 📊  RÉCUPÉRATION DES DONNÉES DE MARCHÉ
# ══════════════════════════════════════════════════════════════

def get_klines(symbole, intervalle="1h", limite=100):
    """
    Récupère les bougies (prix historiques) d'un marché
    intervalle : 1h = bougies d'1 heure
    limite : nombre de bougies récupérées
    """
    url = f"{BASE_URL}/fapi/v1/klines"
    params = {
        "symbol": symbole,
        "interval": intervalle,
        "limit": limite
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        closes = [float(k[4]) for k in data]  # Prix de clôture
        highs  = [float(k[2]) for k in data]  # Prix les plus hauts
        lows   = [float(k[3]) for k in data]  # Prix les plus bas
        return closes, highs, lows
    except Exception as e:
        print(f"❌ Erreur récupération données {symbole} : {e}")
        return None, None, None

def get_prix_actuel(symbole):
    """Récupère le prix actuel d'un marché"""
    url = f"{BASE_URL}/fapi/v1/ticker/price"
    try:
        r = requests.get(url, params={"symbol": symbole}, timeout=10)
        return float(r.json()["price"])
    except Exception as e:
        print(f"❌ Erreur prix {symbole} : {e}")
        return None

# ══════════════════════════════════════════════════════════════
# 📈  CALCUL DES INDICATEURS TECHNIQUES
# ══════════════════════════════════════════════════════════════

def calculer_rsi(closes, periode=14):
    """
    Calcule le RSI (Relative Strength Index)
    RSI < 30 = marché survendu → signal ACHAT
    RSI > 70 = marché suracheté → signal VENTE
    """
    if len(closes) < periode + 1:
        return 50  # Valeur neutre si pas assez de données

    gains = []
    pertes = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        if diff > 0:
            gains.append(diff)
            pertes.append(0)
        else:
            gains.append(0)
            pertes.append(abs(diff))

    # Moyenne des gains et pertes sur la période
    moy_gain  = sum(gains[-periode:]) / periode
    moy_perte = sum(pertes[-periode:]) / periode

    if moy_perte == 0:
        return 100
    rs  = moy_gain / moy_perte
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 2)

def calculer_moyenne_mobile(closes, periode):
    """Calcule la moyenne mobile simple sur une période donnée"""
    if len(closes) < periode:
        return None
    return sum(closes[-periode:]) / periode

def calculer_volatilite(closes, highs, lows, periode=14):
    """
    Calcule la volatilité moyenne sur la période
    Plus la volatilité est haute → plus le marché bouge
    → Plus de chances d'atteindre l'objectif x3
    """
    if len(closes) < periode:
        return 0
    amplitudes = []
    for i in range(-periode, 0):
        amplitude = (highs[i] - lows[i]) / closes[i] * 100
        amplitudes.append(amplitude)
    return round(sum(amplitudes) / len(amplitudes), 2)

# ══════════════════════════════════════════════════════════════
# 🎯  SYSTÈME DE SCORING — CHOIX DU MEILLEUR MARCHÉ
# ══════════════════════════════════════════════════════════════

def scorer_marche(symbole):
    """
    Analyse un marché et lui attribue un score sur 30
    Critère 1 : Force du RSI        (0 à 10 points)
    Critère 2 : Moyenne Mobile      (0 à 10 points)
    Critère 3 : Volatilité          (0 à 10 points)
    """
    print(f"\n📊 Analyse de {symbole}...")

    closes, highs, lows = get_klines(symbole, "1h", 100)
    if closes is None:
        return 0, "NEUTRE", {}

    rsi        = calculer_rsi(closes)
    ma_courte  = calculer_moyenne_mobile(closes, 10)   # MA 10 périodes
    ma_longue  = calculer_moyenne_mobile(closes, 30)   # MA 30 périodes
    volatilite = calculer_volatilite(closes, highs, lows)

    # ── Score RSI (0-10) ──
    # Plus le RSI est extrême (< 30 ou > 70), plus le score est élevé
    if rsi < 25:
        score_rsi = 10
        direction = "ACHAT"
    elif rsi < 30:
        score_rsi = 8
        direction = "ACHAT"
    elif rsi < 40:
        score_rsi = 5
        direction = "ACHAT"
    elif rsi > 75:
        score_rsi = 10
        direction = "VENTE"
    elif rsi > 70:
        score_rsi = 8
        direction = "VENTE"
    elif rsi > 60:
        score_rsi = 5
        direction = "VENTE"
    else:
        score_rsi = 2
        direction = "NEUTRE"

    # ── Score Moyenne Mobile (0-10) ──
    if ma_courte and ma_longue:
        ecart = abs(ma_courte - ma_longue) / ma_longue * 100
        if ma_courte > ma_longue:
            # Tendance haussière
            direction_ma = "ACHAT"
        else:
            # Tendance baissière
            direction_ma = "VENTE"

        if ecart > 2:
            score_ma = 10
        elif ecart > 1:
            score_ma = 7
        elif ecart > 0.5:
            score_ma = 4
        else:
            score_ma = 1
    else:
        score_ma     = 0
        direction_ma = "NEUTRE"

    # ── Score Volatilité (0-10) ──
    if volatilite > 3:
        score_vol = 10
    elif volatilite > 2:
        score_vol = 8
    elif volatilite > 1:
        score_vol = 5
    elif volatilite > 0.5:
        score_vol = 3
    else:
        score_vol = 1

    # ── Score Total ──
    score_total = score_rsi + score_ma + score_vol

    # ── Direction finale ──
    # RSI a priorité, si neutre on suit la MA
    if direction == "NEUTRE":
        direction = direction_ma

    details = {
        "rsi":        rsi,
        "score_rsi":  score_rsi,
        "ma_courte":  round(ma_courte, 4) if ma_courte else None,
        "ma_longue":  round(ma_longue, 4) if ma_longue else None,
        "score_ma":   score_ma,
        "volatilite": volatilite,
        "score_vol":  score_vol,
        "score_total": score_total,
        "direction":  direction
    }

    print(f"   RSI        : {rsi} → {score_rsi}/10")
    print(f"   MA         : écart → {score_ma}/10 ({direction_ma})")
    print(f"   Volatilité : {volatilite}% → {score_vol}/10")
    print(f"   ⭐ SCORE TOTAL : {score_total}/30 ({direction})")

    return score_total, direction, details

def choisir_meilleur_marche():
    """
    Compare ETH et SOL et choisit le meilleur marché du jour
    Retourne : symbole gagnant, direction (ACHAT/VENTE), détails
    """
    print("\n" + "═"*55)
    print("🔍 SÉLECTION DU MEILLEUR MARCHÉ DU JOUR")
    print("═"*55)

    resultats = {}
    for marche in MARCHES:
        score, direction, details = scorer_marche(marche)
        resultats[marche] = {
            "score": score,
            "direction": direction,
            "details": details
        }
        time.sleep(0.5)  # Petite pause entre les requêtes

    # Tri par score décroissant
    meilleur = max(resultats, key=lambda x: resultats[x]["score"])

    print(f"\n{'═'*55}")
    print(f"🏆 MARCHÉ CHOISI : {meilleur}")
    print(f"   Score     : {resultats[meilleur]['score']}/30")
    print(f"   Direction : {resultats[meilleur]['direction']}")
    print(f"{'═'*55}\n")

    return meilleur, resultats[meilleur]["direction"], resultats[meilleur]["details"]

# ══════════════════════════════════════════════════════════════
# 💰  GESTION DES ORDRES BINANCE
# ══════════════════════════════════════════════════════════════

def configurer_levier(symbole):
    """Configure le levier x3 sur le marché choisi"""
    url = f"{BASE_URL}/fapi/v1/leverage"
    params = signer_requete({
        "symbol":    symbole,
        "leverage":  LEVIER,
        "timestamp": int(time.time() * 1000)
    })
    try:
        r = requests.post(url, params=params, headers=headers(), timeout=10)
        data = r.json()
        if "leverage" in data:
            print(f"✅ Levier x{LEVIER} configuré sur {symbole}")
            return True
        else:
            print(f"❌ Erreur configuration levier : {data}")
            return False
    except Exception as e:
        print(f"❌ Erreur levier : {e}")
        return False

def get_precision(symbole):
    """Récupère la précision des quantités pour le marché"""
    url = f"{BASE_URL}/fapi/v1/exchangeInfo"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        for s in data["symbols"]:
            if s["symbol"] == symbole:
                return s["quantityPrecision"]
        return 3
    except:
        return 3

def calculer_quantite(symbole, mise_usdt):
    """
    Calcule la quantité à acheter/vendre
    Avec levier x3 : la mise contrôle mise*3 en valeur
    """
    prix     = get_prix_actuel(symbole)
    if prix is None:
        return None, None
    # Avec levier x3, on contrôle mise*3
    valeur_controllee = mise_usdt * LEVIER
    precision         = get_precision(symbole)
    quantite          = round(valeur_controllee / prix, precision)
    return quantite, prix

def placer_ordre(symbole, direction, mise_usdt):
    """
    Place l'ordre d'ouverture du trade
    direction : ACHAT (LONG) ou VENTE (SHORT)
    """
    quantite, prix_entree = calculer_quantite(symbole, mise_usdt)
    if quantite is None:
        return None

    side = "BUY" if direction == "ACHAT" else "SELL"

    # Prix objectif (x3 la mise = gain de 2x la mise)
    # Avec levier x3, il faut un mouvement de 66.7% pour tripler
    # En pratique on vise +33% de mouvement sur le prix avec levier x3
    if direction == "ACHAT":
        prix_objectif   = round(prix_entree * 1.333, 2)
        prix_stop_loss  = round(prix_entree * 0.667, 2)  # -33% = perte totale
    else:
        prix_objectif   = round(prix_entree * 0.667, 2)
        prix_stop_loss  = round(prix_entree * 1.333, 2)

    params = signer_requete({
        "symbol":    symbole,
        "side":      side,
        "type":      "MARKET",
        "quantity":  quantite,
        "timestamp": int(time.time() * 1000)
    })

    print(f"\n📤 PLACEMENT DU TRADE")
    print(f"   Marché     : {symbole}")
    print(f"   Direction  : {direction}")
    print(f"   Mise       : {mise_usdt} USDT")
    print(f"   Quantité   : {quantite}")
    print(f"   Prix entrée: {prix_entree}")
    print(f"   Objectif   : {prix_objectif} (x3 = +{mise_usdt*2}€)")
    print(f"   Stop-Loss  : {prix_stop_loss} (perte totale)")

    try:
        r = requests.post(
            f"{BASE_URL}/fapi/v1/order",
            params=params,
            headers=headers(),
            timeout=10
        )
        data = r.json()
        if "orderId" in data:
            print(f"✅ Trade ouvert ! ID : {data['orderId']}")
            return {
                "ordre_id":       data["orderId"],
                "symbole":        symbole,
                "direction":      direction,
                "mise":           mise_usdt,
                "quantite":       quantite,
                "prix_entree":    prix_entree,
                "prix_objectif":  prix_objectif,
                "prix_stop_loss": prix_stop_loss,
                "heure_ouverture": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        else:
            print(f"❌ Erreur ordre : {data}")
            return None
    except Exception as e:
        print(f"❌ Erreur placement ordre : {e}")
        return None

def fermer_position(symbole, direction, quantite):
    """Ferme la position ouverte"""
    # Pour fermer : on fait l'ordre inverse
    side = "SELL" if direction == "ACHAT" else "BUY"
    params = signer_requete({
        "symbol":         symbole,
        "side":           side,
        "type":           "MARKET",
        "quantity":       quantite,
        "reduceOnly":     "true",
        "timestamp":      int(time.time() * 1000)
    })
    try:
        r = requests.post(
            f"{BASE_URL}/fapi/v1/order",
            params=params,
            headers=headers(),
            timeout=10
        )
        data = r.json()
        if "orderId" in data:
            print(f"✅ Position fermée !")
            return True
        else:
            print(f"❌ Erreur fermeture : {data}")
            return False
    except Exception as e:
        print(f"❌ Erreur fermeture position : {e}")
        return False

# ══════════════════════════════════════════════════════════════
# 👁️  SURVEILLANCE DU TRADE EN TEMPS RÉEL
# ══════════════════════════════════════════════════════════════

def surveiller_trade(trade):
    """
    Surveille le trade ouvert en temps réel
    Ferme automatiquement quand :
    - Prix atteint l'objectif x3 → GAGNÉ
    - Prix atteint le stop-loss  → PERDU
    """
    symbole        = trade["symbole"]
    direction      = trade["direction"]
    prix_objectif  = trade["prix_objectif"]
    prix_stop_loss = trade["prix_stop_loss"]
    mise           = trade["mise"]
    quantite       = trade["quantite"]

    print(f"\n👁️  SURVEILLANCE EN COURS...")
    print(f"   Objectif  : {prix_objectif}")
    print(f"   Stop-Loss : {prix_stop_loss}")
    print(f"   (Vérification toutes les 60 secondes)\n")

    while True:
        prix_actuel = get_prix_actuel(symbole)
        if prix_actuel is None:
            time.sleep(30)
            continue

        heure = datetime.now().strftime("%H:%M:%S")

        if direction == "ACHAT":
            if prix_actuel >= prix_objectif:
                print(f"\n🎉 [{heure}] OBJECTIF ATTEINT ! Prix : {prix_actuel}")
                fermer_position(symbole, direction, quantite)
                return "GAGNÉ", mise * 2  # Bénéfice net = double de la mise
            elif prix_actuel <= prix_stop_loss:
                print(f"\n❌ [{heure}] STOP-LOSS ATTEINT ! Prix : {prix_actuel}")
                fermer_position(symbole, direction, quantite)
                return "PERDU", -mise
        else:  # VENTE
            if prix_actuel <= prix_objectif:
                print(f"\n🎉 [{heure}] OBJECTIF ATTEINT ! Prix : {prix_actuel}")
                fermer_position(symbole, direction, quantite)
                return "GAGNÉ", mise * 2
            elif prix_actuel >= prix_stop_loss:
                print(f"\n❌ [{heure}] STOP-LOSS ATTEINT ! Prix : {prix_actuel}")
                fermer_position(symbole, direction, quantite)
                return "PERDU", -mise

        print(f"   [{heure}] Prix actuel : {prix_actuel} | Objectif : {prix_objectif} | Stop : {prix_stop_loss}")
        time.sleep(60)  # Vérification chaque minute

# ══════════════════════════════════════════════════════════════
# 📋  AFFICHAGE DU TABLEAU DE BORD
# ══════════════════════════════════════════════════════════════

def afficher_tableau_de_bord(etat):
    """Affiche un résumé clair de la situation du bot"""
    print("\n" + "═"*55)
    print("📊 TABLEAU DE BORD — BOT MARTINGALE")
    print("═"*55)
    print(f"   Mode              : {'🧪 TEST (Paper Trading)' if MODE_TEST else '💰 RÉEL'}")
    print(f"   Mise actuelle     : {etat['mise_actuelle']} USDT")
    print(f"   Pertes consécutives: {etat['pertes_consecutives']}")
    print(f"   Total perdu       : -{etat['total_perdu']} USDT")
    print(f"   Total gagné       : +{etat['total_gagné']} USDT")
    print(f"   Bénéfice net      : {'+' if etat['cumul_net'] >= 0 else ''}{round(etat['cumul_net'], 2)} USDT")
    print(f"   Dernier trade     : {etat['date_dernier_trade'] or 'Aucun'}")
    if etat["historique"]:
        print(f"\n   📅 Derniers trades :")
        for h in etat["historique"][-5:]:
            icone = "✅" if h["resultat"] == "GAGNÉ" else "❌"
            print(f"      {icone} {h['date']} | {h['marche']} | {h['mise']}€ | {h['resultat']} | {'+' if h['gain'] >= 0 else ''}{h['gain']}€")
    print("═"*55 + "\n")

# ══════════════════════════════════════════════════════════════
# 🔄  LOGIQUE MARTINGALE — CALCUL DE LA PROCHAINE MISE
# ══════════════════════════════════════════════════════════════

def calculer_prochaine_mise(etat, resultat):
    """
    Applique les règles de la martingale journalière :
    - Si GAGNÉ  → revenir à 5€
    - Si PERDU  → doubler la mise
    """
    if resultat == "GAGNÉ":
        prochaine_mise             = MISE_DEPART
        etat["pertes_consecutives"] = 0
        print(f"\n✅ GAGNÉ ! Retour à la mise de départ : {MISE_DEPART} USDT demain")
    else:
        prochaine_mise              = etat["mise_actuelle"] * 2
        etat["pertes_consecutives"] += 1
        print(f"\n❌ PERDU. Mise doublée pour demain : {prochaine_mise} USDT")
        print(f"   ({etat['pertes_consecutives']} perte(s) consécutive(s))")
        print(f"   On continue jusqu'à récupérer — ne pas abandonner !")

    etat["mise_actuelle"] = prochaine_mise
    return etat

# ══════════════════════════════════════════════════════════════
# 🚀  FONCTION PRINCIPALE — TRADE DU JOUR
# ══════════════════════════════════════════════════════════════

def trade_du_jour():
    """
    Fonction principale exécutée une fois par jour.
    Elle gère tout le cycle : analyse → choix → trade → surveillance → mise à jour
    """
    print("\n" + "█"*55)
    print("█   BOT MARTINGALE — DÉMARRAGE DU TRADE DU JOUR       █")
    print(f"█   {datetime.now().strftime('%A %d %B %Y — %H:%M:%S')}         █")
    print("█"*55)

    # Chargement de l'état
    etat = charger_etat()
    afficher_tableau_de_bord(etat)

    # Vérification : trade déjà fait aujourd'hui ?
    aujourd_hui = datetime.now().strftime("%Y-%m-%d")
    if etat["trade_du_jour_fait"] and etat["date_dernier_trade"] == aujourd_hui:
        print("⚠️  Trade du jour déjà effectué. On attend demain.")
        print(f"   Prochaine mise prévue : {etat['mise_actuelle']} USDT")
        return

    mise = etat["mise_actuelle"]
    print(f"💰 Mise du jour : {mise} USDT (levier x{LEVIER})")
    print(f"🎯 Objectif     : {mise * LEVIER} USDT (bénéfice net : +{mise * 2} USDT)")

    # Étape 1 : Choisir le meilleur marché
    symbole, direction, details = choisir_meilleur_marche()

    if direction == "NEUTRE":
        print("⚠️  Aucun signal clair aujourd'hui. On passe cette journée.")
        print("   La mise reste inchangée pour demain.")
        return

    # Étape 2 : Configurer le levier
    if not configurer_levier(symbole):
        print("❌ Impossible de configurer le levier. Abandon.")
        return

    # Étape 3 : Placer le trade
    trade = placer_ordre(symbole, direction, mise)
    if trade is None:
        print("❌ Impossible de placer l'ordre. Abandon.")
        return

    # Marquer le trade comme fait aujourd'hui
    etat["trade_du_jour_fait"] = True
    etat["date_dernier_trade"] = aujourd_hui
    sauvegarder_etat(etat)

    # Étape 4 : Surveiller le trade
    resultat, gain_perte = surveiller_trade(trade)

    # Étape 5 : Mettre à jour l'état
    if resultat == "GAGNÉ":
        etat["total_gagné"] += abs(gain_perte)
    else:
        etat["total_perdu"] += abs(gain_perte)

    etat["cumul_net"] = round(etat["total_gagné"] - etat["total_perdu"], 2)

    # Enregistrement dans l'historique
    etat["historique"].append({
        "date":     aujourd_hui,
        "marche":   symbole,
        "mise":     mise,
        "resultat": resultat,
        "gain":     round(gain_perte, 2),
        "cumul":    etat["cumul_net"],
        "direction": direction,
        "score":    details.get("score_total", 0)
    })

    # Étape 6 : Appliquer la martingale
    etat = calculer_prochaine_mise(etat, resultat)
    etat["trade_du_jour_fait"] = False  # Reset pour demain

    # Sauvegarde finale
    sauvegarder_etat(etat)

    # Résumé final
    print("\n" + "═"*55)
    print("📊 RÉSUMÉ DU TRADE DU JOUR")
    print("═"*55)
    print(f"   Marché    : {symbole}")
    print(f"   Direction : {direction}")
    print(f"   Mise      : {mise} USDT")
    print(f"   Résultat  : {'🎉 GAGNÉ' if resultat == 'GAGNÉ' else '❌ PERDU'}")
    print(f"   Gain/Perte: {'+' if gain_perte >= 0 else ''}{round(gain_perte, 2)} USDT")
    print(f"   Cumul net : {'+' if etat['cumul_net'] >= 0 else ''}{etat['cumul_net']} USDT")
    print(f"   Mise demain: {etat['mise_actuelle']} USDT")
    print("═"*55)
    print("✅ Bot en veille jusqu'à demain.")

# ══════════════════════════════════════════════════════════════
# 🔁  BOUCLE PRINCIPALE — Le bot vérifie toutes les heures
# ══════════════════════════════════════════════════════════════

def demarrer_bot():
    """
    Lance le bot en boucle.
    Il exécute le trade du jour une fois, puis attend jusqu'au lendemain.
    """
    print("\n🚀 DÉMARRAGE DU BOT DE TRADING MARTINGALE")
    print(f"   Mode : {'🧪 PAPER TRADING (TEST)' if MODE_TEST else '💰 RÉEL'}")
    print(f"   Marchés : {', '.join(MARCHES)}")
    print(f"   Mise de départ : {MISE_DEPART} USDT")
    print(f"   Levier : x{LEVIER}")
    print()

    while True:
        try:
            trade_du_jour()
        except KeyboardInterrupt:
            print("\n⛔ Bot arrêté manuellement.")
            break
        except Exception as e:
            print(f"\n❌ Erreur inattendue : {e}")
            print("   Nouvelle tentative dans 5 minutes...")

        # Attendre jusqu'au lendemain (vérification toutes les heures)
        print(f"\n⏰ Prochaine vérification dans 1 heure...")
        time.sleep(3600)

# ══════════════════════════════════════════════════════════════
# ▶️  POINT D'ENTRÉE
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    demarrer_bot()
