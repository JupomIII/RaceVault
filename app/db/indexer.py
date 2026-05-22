class Indexer:
    def __init__(self, db):
        self.db = db

    def index_pdf_folder(self, folder):
        # placeholder pipeline
        conn = self.db.connect()
        cur = conn.cursor()
        cur.execute("INSERT INTO results (athlete_name, time_raw, time_seconds) VALUES (?,?,?)",
                    ("TEST", "1:00.0", 60.0))
        conn.commit()
