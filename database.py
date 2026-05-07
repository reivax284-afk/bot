"""
═══════════════════════════════════════════════════════════════
  database.py — Persistance PostgreSQL Railway
  Toutes les données survivent aux redéploiements
═══════════════════════════════════════════════════════════════
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get('DATABASE_URL')

def get_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL non définie dans Railway Variables")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_database():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bot_state (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    capital NUMERIC(15,2) NOT NULL DEFAULT 50.0,
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
            cur.execute("""
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
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_trade_timestamp
                ON trade_history(timestamp DESC)
            """)
            cur.execute("""
                INSERT INTO bot_state (id)
                VALUES (1)
                ON CONFLICT (id) DO NOTHING
            """)
            conn.commit()
            logger.info("Base PostgreSQL initialisee")
    finally:
        conn.close()

def charger_etat():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM bot_state WHERE id = 1")
            row = cur.fetchone()
            if not row:
                init_database()
                return charger_etat()
            etat = dict(row)
            for key in ['capital','total_gagne','total_perdu','cumul_net',
                        'avg_win_pct','avg_loss_pct']:
                if etat.get(key) is not None:
                    etat[key] = float(etat[key])
            for key in ['nb_trades','nb_wins','nb_losses','nb_skips',
                        'pertes_consecutives']:
                if etat.get(key) is not None:
                    etat[key] = int(etat[key])
            etat['pause_until'] = int(etat.get('pause_until') or 0)
            cur.execute("""
                SELECT * FROM trade_history
                ORDER BY timestamp DESC LIMIT 5
            """)
            rows = cur.fetchall()
            etat['historique'] = [
                {
                    'heure': h['timestamp'].strftime('%Y-%m-%d %H:%M'),
                    'marche': h['marche'],
                    'direction': h['direction'],
                    'resultat': h['resultat'],
                    'gain': float(h['gain']),
                    'mise': float(h['mise']),
                    'capital': float(h['capital_apres'])
                }
                for h in reversed(rows)
            ]
            etat.pop('updated_at', None)
            etat.pop('id', None)
            return etat
    finally:
        conn.close()

def sauvegarder_etat(etat):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE bot_state SET
                    capital=%s, total_gagne=%s, total_perdu=%s,
                    cumul_net=%s, nb_trades=%s, nb_wins=%s,
                    nb_losses=%s, nb_skips=%s, pertes_consecutives=%s,
                    avg_win_pct=%s, avg_loss_pct=%s, pause_until=%s,
                    updated_at=NOW()
                WHERE id=1
            """, (
                etat.get('capital',50.0),
                etat.get('total_gagne',0.0),
                etat.get('total_perdu',0.0),
                etat.get('cumul_net',0.0),
                etat.get('nb_trades',0),
                etat.get('nb_wins',0),
                etat.get('nb_losses',0),
                etat.get('nb_skips',0),
                etat.get('pertes_consecutives',0),
                etat.get('avg_win_pct',0.0),
                etat.get('avg_loss_pct',0.0),
                int(etat.get('pause_until',0)),
            ))
            conn.commit()
    finally:
        conn.close()

def enregistrer_trade(trade_data):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO trade_history (
                    marche, direction, resultat,
                    prix_entree, prix_sortie, stop_loss, objectif,
                    mise, gain, capital_apres, duree_minutes,
                    score, adx, atr, rsi
                ) VALUES (
                    %(marche)s, %(direction)s, %(resultat)s,
                    %(prix_entree)s, %(prix_sortie)s, %(stop_loss)s, %(objectif)s,
                    %(mise)s, %(gain)s, %(capital_apres)s, %(duree_minutes)s,
                    %(score)s, %(adx)s, %(atr)s, %(rsi)s
                )
            """, trade_data)
            conn.commit()
    finally:
        conn.close()

def get_statistiques_globales():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) as total_trades,
                    COUNT(*) FILTER (WHERE resultat='GAGNE') as wins,
                    COUNT(*) FILTER (WHERE resultat='PERDU') as losses,
                    AVG(gain) FILTER (WHERE resultat='GAGNE') as avg_win,
                    AVG(gain) FILTER (WHERE resultat='PERDU') as avg_loss,
                    SUM(gain) as total_pnl,
                    AVG(duree_minutes) as duree_moyenne
                FROM trade_history
            """)
            return dict(cur.fetchone())
    finally:
        conn.close()
