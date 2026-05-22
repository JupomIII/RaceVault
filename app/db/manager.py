import sqlite3
from typing import Optional
from .schema import SCHEMA_SQL

class DatabaseManager:
    def __init__(self, db_path: str = "sports_results.db"):
        self.db_path = db_path
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA_SQL)
        self.conn.commit()
        return self.conn

    def close(self):
        if self.conn:
            self.conn.close()
