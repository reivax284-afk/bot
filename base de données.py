"""
═══════════════════════════════════════════════════════════════
  database.py — Persistance PostgreSQL Railway via pg8000
  100% Python — pas de dépendance système
═══════════════════════════════════════════════════════════════
"""

import os
import pg8000
import pg8000.native
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def parse_database_url(url):
    """Parse DATABASE_URL en paramètres de connexion."""
    import urllib.parse
    result = urllib.parse.urlparse(url)
    return {
        'host':     result.hostname,
        'port':     result.port or 5432,
        'database': result.path[1:],
        'user':     result.username,
        'password': result.password,
        'ssl_context': True
    }

def get_connection():
    DATABASE_URL = os.environ.get('DATABASE_URL')
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL non définie dans Railway Variables")
    params = parse_database_url(DATABASE_URL)
    return pg8000.native.Connection(
        host=params['host'],
        port=params['port'],
        database=params['database'],
        user=params['user'],
        password=params['password'],
        ssl_context=params['ssl_context']
    )

def init_database():
    conn = get_connection()
    try:
        conn.run("""
            CREATE TABLE IF NOT EXISTS bot_state (
                id INTEGER PRIMARY KEY DEFAULT 1,
                capital NUMERIC(15,2) NOT NULL DEFAULT 500.0,
                total_gagne NUMERIC(15,2) NOT NULL DEFAULT 0.0,
                total_perdu NUMERIC(15,2) NOT NULL DEFAULT 0.0,
                cumul_net NUMERIC(15,2) NOT NULL DEFAULT 0.0,
                nb_trades INTEGER NOT NULL DEFAULT 0,
                nb_wins INTEGER NOT NULL DEFAULT 0,
                nb_losses INTEGER NOT NULL DEFAULT 0,
                nb_skips INTEGER NOT NULL DEFAULT 0,
                pertes_consecutives INTEGER NOT NULL DEFAULT 0,
                avg_win_pct NUMERIC(10,4) NOT NULL DEFAULT 0.0,
                avg_loss_pct NUMERIC(10,4) NOT NULL DEFAULT 0.0,
                pause_until BIGINT DEFAULT 0,
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                CONSTRAINT single_row CHECK (id = 1)
            )
        """)
        conn.run("""
            CREATE TABLE IF NOT EXISTS trade_history (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
                marche VARCHAR(20) NOT NULL,
                direction VARCHAR(10) NOT NULL,
                resultat VARCHAR(10) NOT NULL,
                prix_entree NUMERIC(20,8) NOT NULL,
                prix_sortie NUMERIC(20,8) NOT NULL,
                stop_loss NUMERIC(20,8) NOT NULL,
                objectif NUMERIC(20,8) NOT NULL,
                mise NUMERIC(15,2) NOT NULL,
                gain NUMERIC(15,2) NOT NULL,
                capital_apres NUMERIC(15,2) NOT NULL,
                duree_minutes INTEGER NOT NULL,
                score INTEGER,
                adx NUMERIC(6,2),
                atr NUMERIC(20,8),
                rsi NUMERIC(6,2)
            )
        """)
        conn.run("""
            CREATE INDEX IF NOT EXISTS idx_trade_timestamp
            ON trade_history(timestamp DESC)
        """)
        conn.run("""
            INSERT INTO bot_state (id, capital)
            VALUES (1, 500.0)
            ON CONFLICT (id) DO NOTHING
        """)
        logger.info("Base PostgreSQL initialisee")
    except Exception as e:
        logger.error(f"Erreur init_database : {e}")
        raise
    finally:
        conn.close()

def charger_etat():
    conn = get_connection()
    try:
        rows = conn.run("SELECT * FROM bot_state WHERE id = 1")
        columns = [col['name'] for col in conn.columns]

        if not rows:
            conn.close()
            init_database()
            return charger_etat()

        etat = dict(zip(columns, rows[0]))

        for key in ['capital', 'total_gagne', 'total_perdu', 'cumul_net',
                    'avg_win_pct', 'avg_loss_pct']:
            if etat.get(key) is not None:
                etat[key] = float(etat[key])

        for key in ['nb_trades', 'nb_wins', 'nb_losses', 'nb_skips',
                    'pertes_consecutives']:
            if etat.get(key) is not None:
                etat[key] = int(etat[key])

        etat['pause_until'] = int(etat.get('pause_until') or 0)

        rows_h = conn.run("""
            SELECT * FROM trade_history
            ORDER BY timestamp DESC LIMIT 5
        """)
        cols_h = [col['name'] for col in conn.columns]

        historique = []
        for row in reversed(rows_h):
            h = dict(zip(cols_h, row))
            historique.append({
                'heure':     str(h['timestamp'])[:16],
                'marche':    h['marche'],
                'direction': h['direction'],
                'resultat':  h['resultat'],
                'gain':      float(h['gain']),
                'mise':      float(h['mise']),
                'capital':   float(h['capital_apres'])
            })

        etat['historique'] = historique
        etat.pop('updated_at', None)
        etat.pop('id', None)
        return etat
    except Exception as e:
        logger.error(f"Erreur charger_etat : {e}")
        raise
    finally:
        conn.close()

def sauvegarder_etat(etat):
    conn = get_connection()
    try:
        conn.run("""
            UPDATE bot_state SET
                capital=:capital,
                total_gagne=:total_gagne,
                total_perdu=:total_perdu,
                cumul_net=:cumul_net,
                nb_trades=:nb_trades,
                nb_wins=:nb_wins,
                nb_losses=:nb_losses,
                nb_skips=:nb_skips,
                pertes_consecutives=:pertes_consecutives,
                avg_win_pct=:avg_win_pct,
                avg_loss_pct=:avg_loss_pct,
                pause_until=:pause_until,
                updated_at=NOW()
            WHERE id=1
        """,
        capital=etat.get('capital', 500.0),
        total_gagne=etat.get('total_gagne', 0.0),
        total_perdu=etat.get('total_perdu', 0.0),
        cumul_net=etat.get('cumul_net', 0.0),
        nb_trades=etat.get('nb_trades', 0),
        nb_wins=etat.get('nb_wins', 0),
        nb_losses=etat.get('nb_losses', 0),
        nb_skips=etat.get('nb_skips', 0),
        pertes_consecutives=etat.get('pertes_consecutives', 0),
        avg_win_pct=etat.get('avg_win_pct', 0.0),
        avg_loss_pct=etat.get('avg_loss_pct', 0.0),
        pause_until=int(etat.get('pause_until', 0)),
        )
    except Exception as e:
        logger.error(f"Erreur sauvegarder_etat : {e}")
        raise
    finally:
        conn.close()

def enregistrer_trade(trade_data):
    conn = get_connection()
    try:
        conn.run("""
            INSERT INTO trade_history (
                marche, direction, resultat,
                prix_entree, prix_sortie, stop_loss, objectif,
                mise, gain, capital_apres, duree_minutes,
                score, adx, atr, rsi
            ) VALUES (
                :marche, :direction, :resultat,
                :prix_entree, :prix_sortie, :stop_loss, :objectif,
                :mise, :gain, :capital_apres, :duree_minutes,
                :score, :adx, :atr, :rsi
            )
        """,
        marche=trade_data['marche'],
        direction=trade_data['direction'],
        resultat=trade_data['resultat'],
        prix_entree=trade_data['prix_entree'],
        prix_sortie=trade_data['prix_sortie'],
        stop_loss=trade_data['stop_loss'],
        objectif=trade_data['objectif'],
        mise=trade_data['mise'],
        gain=trade_data['gain'],
        capital_apres=trade_data['capital_apres'],
        duree_minutes=trade_data['duree_minutes'],
        score=trade_data.get('score'),
        adx=trade_data.get('adx'),
        atr=trade_data.get('atr'),
        rsi=trade_data.get('rsi'),
        )
    except Exception as e:
        logger.error(f"Erreur enregistrer_trade : {e}")
        raise
    finally:
        conn.close()
