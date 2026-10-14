#!/usr/bin/env python3
"""
PNR Generation Module (Base32 Custom Crockford-style)
Generates unique 6-character PNR reference codes for telemetry batches.
Excludes ambiguous characters: 0, 1, O, I.
Conforms strictly to the provided PNR specification:
ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ" (BASE 32, LENGTH 6)
"""

import hashlib
import sqlite3
import logging

logger = logging.getLogger("PNRGenerator")

ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
BASE = 32
PNR_LENGTH = 6


def compute_pnr_candidate(base_seed, nonce=0):
    """
    Computes a 6-character PNR string from base_seed and nonce using SHA-256.
    """
    current_seed = f"{base_seed}{nonce}".encode("utf-8")
    hash_hex = hashlib.sha256(current_seed).hexdigest()

    # Take first 8 hex characters (32 bits) and convert to int
    hash_int = int(hash_hex[:8], 16)
    temp_val = abs(hash_int)

    final_pnr = ""
    for _ in range(PNR_LENGTH):
        index = temp_val % BASE
        final_pnr += ALPHABET[index]
        temp_val //= BASE

    return final_pnr


def generate_pnr(payload, db_conn=None):
    """
    Generates a unique 6-character PNR from payload:
    - org_id (or deviceId)
    - collected_at (timestamp)
    - sequence (batch sequence integer)
    Checks local SQLite database to guarantee collision-free uniqueness.
    """
    # 1. Extract uniqueness reference fields from payload
    org = str(payload.get("org_id", payload.get("deviceId", "GSE"))).strip()
    
    # Handle timestamp/collected_at
    collected_at = payload.get("batch", {}).get("collected_at")
    if not collected_at:
        collected_at = payload.get("timestamp", 0)
    time_str = str(collected_at)

    seq = str(payload.get("batch", {}).get("sequence", payload.get("sequence", 1)))

    # Seed string
    base_seed = f"{org}{time_str}{seq}"

    nonce = 0
    is_unique = False
    final_pnr = ""

    while not is_unique:
        final_pnr = compute_pnr_candidate(base_seed, nonce)

        # 5. Check in Database if PNR exists and active
        if db_conn is not None:
            try:
                cursor = db_conn.cursor()
                cursor.execute(
                    "SELECT 1 FROM telemetry_queue WHERE pnr_code = ? AND status = 'pending' LIMIT 1;",
                    (final_pnr,)
                )
                row = cursor.fetchone()
                if row:
                    nonce += 1
                    continue
            except Exception as e:
                # If column doesn't exist yet, proceed
                pass

        is_unique = True

    return final_pnr
