"""
╔══════════════════════════════════════════════════════════════╗
║          BACKTESTING — 30 DERNIERS JOURS                     ║
║          Stratégie Martingale · ETH & SOL · Levier x3        ║
╚══════════════════════════════════════════════════════════════╝
"""

import requests
import json
from datetime import datetime, timedelta

# ══════════════════════════════════════════════════════════════
# ⚙️  PARAMÈTRES
# ══════════════════════════════════════════════════════════════

MISE_DEPART = 5.0
LEVIER      = 3
MARCHES     = ["ETHUSDT", "SOLUSDT"]
BASE_URL    = "https://fapi.binance.com"

# ══════════════════════════════════════════════════════════════
# 📊  DONNÉES HISTORIQUES
# ══════════════════════════════════════════════════════════════

def get_donnees_journalieres(symbole, jours=30):
    """Récupère les données journalières des 30 derniers jours"""
    url = f"{BASE_URL}/fapi/v1/klines"
    params = {"symbol": symbole, "interval": "1d", "limit": jours}
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        journees = []
        for k in data:
            journees.append({
                "date":      datetime.fromtimestamp(k[0]/1000).strftime("%Y-%m-%d"),
                "open":      float(k[1]),
                "high":      float(k[2]),
                "low":       float(k[3]),
                "close":     float(k[4]),
                "variation": round((float(k[4]) - float(k[1])) / float(k[1]) * 100, 2)
            })
        return journees
    except Exception as e:
        print(f"❌ Erreur données {symbole} : {e}")
        return []

def get_klines_horaires(symbole, jours=30):
    """Récupère les données horaires pour calculer RSI et MA"""
    url = f"{BASE_URL}/fapi/v1/klines"
    params = {"symbol": symbole, "interval": "1h", "limit": jours * 24}
    try:
        r = requests.get(url, params=params, timeout=10)
        return [float(k[4]) for k in r.json()]
    except:
        return []

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
    mg = sum(gains[-periode:]) / periode
    mp = sum(pertes[-periode:]) / periode
    return round(100 - (100 / (1 + mg/mp)), 2) if mp != 0 else 100

def calculer_ma(closes, periode):
    return sum(closes[-periode:]) / periode if len(closes) >= periode else None

# ══════════════════════════════════════════════════════════════
# 🎯  SIMULATION D'UN JOUR
# ══════════════════════════════════════════════════════════════

def simuler_journee(jour_data_eth, jour_data_sol, closes_eth, closes_sol):
    """
    Simule le trade d'une journée.
    Choisit le meilleur marché et détermine si le trade est gagné ou perdu.
    """

    # Calcul des scores pour ETH
    rsi_eth = calculer_rsi(closes_eth)
    ma_c_eth = calculer_ma(closes_eth, 10)
    ma_l_eth = calculer_ma(closes_eth, 30)

    if rsi_eth < 30:   score_eth, dir_eth = 8, "ACHAT"
    elif rsi_eth > 70: score_eth, dir_eth = 8, "VENTE"
    else:              score_eth, dir_eth = 3, "NEUTRE"

    if ma_c_eth and ma_l_eth:
        score_eth += 5 if abs(ma_c_eth - ma_l_eth) / ma_l_eth * 100 > 1 else 2
        if dir_eth == "NEUTRE":
            dir_eth = "ACHAT" if ma_c_eth > ma_l_eth else "VENTE"

    # Calcul des scores pour SOL
    rsi_sol = calculer_rsi(closes_sol)
    ma_c_sol = calculer_ma(closes_sol, 10)
    ma_l_sol = calculer_ma(closes_sol, 30)

    if rsi_sol < 30:   score_sol, dir_sol = 8, "ACHAT"
    elif rsi_sol > 70: score_sol, dir_sol = 8, "VENTE"
    else:              score_sol, dir_sol = 3, "NEUTRE"

    if ma_c_sol and ma_l_sol:
        score_sol += 5 if abs(ma_c_sol - ma_l_sol) / ma_l_sol * 100 > 1 else 2
        if dir_sol == "NEUTRE":
            dir_sol = "ACHAT" if ma_c_sol > ma_l_sol else "VENTE"

    # Choix du meilleur marché
    if score_eth >= score_sol:
        marche, direction, jour_data = "ETH", dir_eth, jour_data_eth
    else:
        marche, direction, jour_data = "SOL", dir_sol, jour_data_sol

    if direction == "NEUTRE":
        return marche, direction, "SKIP", 0

    # Simulation du résultat
    # Avec levier x3, on gagne si le prix bouge de +33% dans la bonne direction
    # On perd si le prix bouge de -33% dans la mauvaise direction
    variation = jour_data["variation"]

    if direction == "ACHAT":
        # On gagne si le prix monte suffisamment (variation positive > seuil)
        # Avec levier x3 : gain si variation > 10% en journée
        if variation > 8:
            resultat = "GAGNÉ"
        elif variation < -8:
            resultat = "PERDU"
        elif variation > 0:
            resultat = "GAGNÉ"
        else:
            resultat = "PERDU"
    else:  # VENTE
        if variation < -8:
            resultat = "GAGNÉ"
        elif variation > 8:
            resultat = "PERDU"
        elif variation < 0:
            resultat = "GAGNÉ"
        else:
            resultat = "PERDU"

    return marche, direction, resultat, variation

# ══════════════════════════════════════════════════════════════
# 🔄  BACKTESTING PRINCIPAL
# ══════════════════════════════════════════════════════════════

def lancer_backtesting():
    print("\n" + "█"*60)
    print("█   BACKTESTING — 30 DERNIERS JOURS                      █")
    print("█   Stratégie : Martingale Journalière · Levier x3       █")
    print("█"*60)

    print("\n⏳ Récupération des données historiques...")
    donnees_eth = get_donnees_journalieres("ETHUSDT", 30)
    donnees_sol = get_donnees_journalieres("SOLUSDT", 30)
    closes_eth  = get_klines_horaires("ETHUSDT", 30)
    closes_sol  = get_klines_horaires("SOLUSDT", 30)

    if not donnees_eth or not donnees_sol:
        print("❌ Impossible de récupérer les données.")
        return

    print(f"✅ {len(donnees_eth)} jours de données récupérés\n")

    # Variables de simulation
    mise_actuelle       = MISE_DEPART
    cumul_net           = 0.0
    total_gagne         = 0.0
    total_perdu         = 0.0
    pertes_consecutives = 0
    nb_gagnes           = 0
    nb_perdus           = 0
    nb_skips            = 0
    historique          = []
    max_drawdown        = 0.0
    pic_cumul           = 0.0

    print("═"*70)
    print(f"{'Jour':<12} {'Marché':<8} {'Dir':<7} {'Mise':<8} {'Résultat':<10} {'Gain/Perte':<12} {'Cumul':<10}")
    print("═"*70)

    for i, (jour_eth, jour_sol) in enumerate(zip(donnees_eth, donnees_sol)):
        # Calcul des indicateurs sur les données disponibles jusqu'à ce jour
        idx_debut = max(0, i * 24 - 720)
        idx_fin   = min(len(closes_eth), (i + 1) * 24)
        closes_eth_jour = closes_eth[idx_debut:idx_fin]
        closes_sol_jour = closes_sol[idx_debut:idx_fin]

        marche, direction, resultat, variation = simuler_journee(
            jour_eth, jour_sol, closes_eth_jour, closes_sol_jour
        )

        if resultat == "SKIP":
            nb_skips += 1
            print(f"{jour_eth['date']:<12} {marche:<8} {'—':<7} {mise_actuelle:<8.1f} {'⏭ SKIP':<10} {'0.00':<12} {cumul_net:<10.2f}")
            historique.append({"date": jour_eth["date"], "marche": marche, "direction": "—",
                                "mise": mise_actuelle, "resultat": "SKIP", "gain": 0, "cumul": cumul_net})
            continue

        if resultat == "GAGNÉ":
            gain = mise_actuelle * 2
            total_gagne += gain
            cumul_net += gain
            nb_gagnes += 1
            pertes_consecutives = 0
            prochaine_mise = MISE_DEPART
            icone = "✅"
        else:
            gain = -mise_actuelle
            total_perdu += abs(gain)
            cumul_net += gain
            nb_perdus += 1
            pertes_consecutives += 1
            prochaine_mise = mise_actuelle * 2
            icone = "❌"

        # Calcul du drawdown maximum
        if cumul_net > pic_cumul:
            pic_cumul = cumul_net
        drawdown = pic_cumul - cumul_net
        if drawdown > max_drawdown:
            max_drawdown = drawdown

        print(f"{jour_eth['date']:<12} {marche:<8} {direction:<7} {mise_actuelle:<8.1f} {icone+' '+resultat:<10} {'+' if gain >= 0 else ''}{gain:<11.2f} {cumul_net:<10.2f}")

        historique.append({
            "date": jour_eth["date"], "marche": marche, "direction": direction,
            "mise": mise_actuelle, "resultat": resultat,
            "gain": round(gain, 2), "cumul": round(cumul_net, 2),
            "variation_marche": variation
        })

        mise_actuelle = prochaine_mise

    # ══════════════════════════════════════════════════════════
    # 📊  RAPPORT FINAL
    # ══════════════════════════════════════════════════════════

    print("\n" + "═"*60)
    print("📊 RAPPORT DE BACKTESTING — 30 JOURS")
    print("═"*60)
    print(f"   Trades gagnés      : {nb_gagnes} ✅")
    print(f"   Trades perdus      : {nb_perdus} ❌")
    print(f"   Jours sans signal  : {nb_skips} ⏭")
    print(f"   Taux de réussite   : {round(nb_gagnes / max(nb_gagnes + nb_perdus, 1) * 100, 1)}%")
    print(f"   Total gagné        : +{round(total_gagne, 2)}€")
    print(f"   Total perdu        : -{round(total_perdu, 2)}€")
    print(f"   Bénéfice net total : {'+' if cumul_net >= 0 else ''}{round(cumul_net, 2)}€")
    print(f"   Drawdown maximum   : -{round(max_drawdown, 2)}€")
    print(f"   Mise finale        : {mise_actuelle}€")
    print("═"*60)

    if cumul_net > 0:
        print(f"\n🎉 RÉSULTAT POSITIF : +{round(cumul_net, 2)}€ sur 30 jours !")
        print(f"   Rentabilité       : +{round(cumul_net / MISE_DEPART * 100, 1)}% du capital de départ")
    else:
        print(f"\n⚠️  RÉSULTAT NÉGATIF : {round(cumul_net, 2)}€ sur 30 jours")
        print(f"   La stratégie aurait besoin d'ajustements")

    # Sauvegarde du rapport
    rapport = {
        "date_backtesting": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "periode": "30 jours",
        "nb_gagnes": nb_gagnes,
        "nb_perdus": nb_perdus,
        "nb_skips": nb_skips,
        "taux_reussite": round(nb_gagnes / max(nb_gagnes + nb_perdus, 1) * 100, 1),
        "total_gagne": round(total_gagne, 2),
        "total_perdu": round(total_perdu, 2),
        "cumul_net": round(cumul_net, 2),
        "max_drawdown": round(max_drawdown, 2),
        "mise_finale": mise_actuelle,
        "historique": historique
    }

    with open("rapport_backtest.json", "w") as f:
        json.dump(rapport, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Rapport sauvegardé dans rapport_backtest.json")
    print("═"*60)

if __name__ == "__main__":
    lancer_backtesting()
