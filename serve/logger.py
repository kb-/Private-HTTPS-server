import sqlite3
from datetime import datetime
from threading import Lock, Thread


class FileTransferLog:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = None
        self.lock = Lock()  # Ensure thread-safety for the connection
        self.open_connection()
        self.init_db()

    def open_connection(self):
        """Open a persistent database connection."""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)

    def close_connection(self):
        """Close the database connection if it's open."""
        with self.lock:
            if self.conn:
                self.conn.close()
                self.conn = None

    def init_db(self):
        """Initialize the database and create the table if it doesn't exist."""
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS transfer_log (
                    id INTEGER PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    start_byte INTEGER,
                    end_byte INTEGER,
                    client_ip TEXT
                );
            """
            )
            self.conn.commit()

    def log_transfer(
        self, path, status, start_byte=None, end_byte=None, client_ip=None
    ):
        """Log a file transfer event in a separate thread."""
        thread = Thread(
            target=self._log_transfer,
            args=(path, status, start_byte, end_byte, client_ip),
        )
        thread.start()

    def _log_transfer(self, path, status, start_byte, end_byte, client_ip):
        """The actual logging implementation, using the persistent connection."""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO transfer_log (timestamp, file_path, status, start_byte, end_byte, client_ip)
                    VALUES (?, ?, ?, ?, ?, ?);
                """,
                    (timestamp, path, status, start_byte, end_byte, client_ip),
                )
                self.conn.commit()
        except sqlite3.Error as e:
            # Handle the error, e.g., by logging it to a file or standard error
            print(f"Error logging transfer to database: {e}")
