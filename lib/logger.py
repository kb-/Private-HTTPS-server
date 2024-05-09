import sqlite3
from datetime import datetime
from threading import Lock, Thread
from typing import Optional


class FileTransferLog:
    """
    A class to log file transfer events to a SQLite database asynchronously.

    Attributes:
        db_path (str): The path to the SQLite database file.
        conn (Optional[sqlite3.Connection]): A SQLite connection object. It is `None` until the connection is opened.
        lock (Lock): A threading lock to ensure thread-safe operations on the database.
    """

    def __init__(self, db_path: str) -> None:
        """
        Initializes the FileTransferLog with the path to the database.

        Args:
            db_path (str): The path to the SQLite database file.
        """
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self.lock = Lock()  # Ensure thread-safety for the connection
        self.open_connection()
        self.init_db()

    def open_connection(self) -> None:
        """Open a persistent database connection."""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)

    def close_connection(self) -> None:
        """Close the database connection if it's open."""
        with self.lock:
            if self.conn:
                self.conn.close()
                self.conn = None

    def init_db(self) -> None:
        """Initialize the database and create the table if it doesn't exist."""
        with self.lock:
            if self.conn is None:
                raise RuntimeError("Database connection is not open")
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
        self,
        path: str,
        status: str,
        start_byte: Optional[int] = None,
        end_byte: Optional[int] = None,
        client_ip: Optional[str] = None,
    ) -> None:
        """
        Logs a file transfer event in a separate thread for asynchronous execution.

        Args:
            path (str): The path of the file transferred.
            status (str): The status of the file transfer (e.g., 'start', 'complete', 'failed').
            start_byte (Optional[int]): The starting byte of the file transfer. Default is None.
            end_byte (Optional[int]): The ending byte of the file transfer. Default is None.
            client_ip (Optional[str]): The IP address of the client. Default is None.
        """
        thread = Thread(
            target=self._log_transfer,
            args=(path, status, start_byte, end_byte, client_ip),
        )
        thread.start()

    def _log_transfer(
        self,
        path: str,
        status: str,
        start_byte: Optional[int],
        end_byte: Optional[int],
        client_ip: Optional[str],
    ) -> None:
        """
        The actual logging implementation that inserts a transfer log entry into the database.

        This method is intended to be run in a separate thread initiated by `log_transfer`.

        Args:
            path (str): The path of the file transferred.
            status (str): The status of the file transfer (e.g., 'start', 'complete', 'failed').
            start_byte (Optional[int]): The starting byte of the file transfer.
            end_byte (Optional[int]): The ending byte of the file transfer.
            client_ip (Optional[str]): The IP address of the client.
        """
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with self.lock:
                if self.conn is None:
                    raise RuntimeError("Database connection is not open")
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
