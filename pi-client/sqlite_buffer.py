#!/usr/bin/env python3
"""
Store-and-Forward SQLite Buffer for Edge Gateway Redundancy
Provides persistent, crash-safe local offline queue for telemetry data.
"""

import sqlite3
import json
import time
import os
import logging

logger = logging.getLogger("SQLiteBuffer")

class SQLiteBuffer:
    def __init__(self, db_path="buffer.db", max_records=50000):
        self.db_path = db_path
        self.max_records = max_records
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        # Enable WAL mode for high concurrency and crash resilience
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS telemetry_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pnr_code TEXT,
                    created_at REAL NOT NULL,
                    payload TEXT NOT NULL,
                    retry_count INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending'
                );
            """)
            try:
                conn.execute("ALTER TABLE telemetry_queue ADD COLUMN pnr_code TEXT;")
            except Exception:
                pass
            conn.execute("CREATE INDEX IF NOT EXISTS idx_status_created ON telemetry_queue(status, created_at);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pnr ON telemetry_queue(pnr_code);")
            conn.commit()

    def enqueue(self, payload_dict, pnr_code=None):
        """Stores a telemetry record persistently when offline or failed."""
        try:
            pnr = pnr_code or payload_dict.get("pnrCode") or payload_dict.get("batch", {}).get("pnr_code")
            payload_str = json.dumps(payload_dict)
            now = time.time()
            with self._get_connection() as conn:
                # Check maximum limit to protect SD card storage
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM telemetry_queue WHERE status = 'pending';")
                count = cursor.fetchone()[0]
                if count >= self.max_records:
                    # Drop oldest pending records if threshold reached
                    cursor.execute("""
                        DELETE FROM telemetry_queue WHERE id IN (
                            SELECT id FROM telemetry_queue WHERE status = 'pending' ORDER BY created_at ASC LIMIT 100
                        );
                    """)
                    logger.warning(f"Buffer exceeded max records ({self.max_records}). Purged 100 oldest records.")

                cursor.execute(
                    "INSERT INTO telemetry_queue (pnr_code, created_at, payload, retry_count, status) VALUES (?, ?, ?, 0, 'pending');",
                    (pnr, now, payload_str)
                )
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Failed to enqueue record to SQLite buffer: {e}")
            return None

    def get_pending_batch(self, limit=20):
        """Retrieves a batch of pending records in FIFO order."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, created_at, payload, retry_count 
                    FROM telemetry_queue 
                    WHERE status = 'pending' 
                    ORDER BY created_at ASC 
                    LIMIT ?;
                """, (limit,))
                rows = cursor.fetchall()

                batch = []
                for row_id, created_at, payload_str, retry_count in rows:
                    try:
                        data = json.loads(payload_str)
                        batch.append({
                            "queue_id": row_id,
                            "created_at": created_at,
                            "retry_count": retry_count,
                            "payload": data
                        })
                    except Exception:
                        pass
                return batch
        except Exception as e:
            logger.error(f"Failed to fetch pending batch from SQLite buffer: {e}")
            return []

    def mark_sent(self, queue_ids):
        """Deletes or marks transmitted records as sent."""
        if not queue_ids:
            return
        try:
            with self._get_connection() as conn:
                placeholders = ",".join("?" for _ in queue_ids)
                conn.execute(f"DELETE FROM telemetry_queue WHERE id IN ({placeholders});", queue_ids)
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to mark records as sent: {e}")

    def increment_retry(self, queue_ids):
        """Increments retry count for failed transmissions."""
        if not queue_ids:
            return
        try:
            with self._get_connection() as conn:
                placeholders = ",".join("?" for _ in queue_ids)
                conn.execute(f"UPDATE telemetry_queue SET retry_count = retry_count + 1 WHERE id IN ({placeholders});", queue_ids)
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to increment retry count: {e}")

    def get_queue_depth(self):
        """Returns the number of pending unsent records in the buffer."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM telemetry_queue WHERE status = 'pending';")
                return cursor.fetchone()[0]
        except Exception:
            return 0
