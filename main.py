from lib.server import file_transfer_log, run, shutdown_in_progress

if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        if not shutdown_in_progress:
            # Ensures the connection is closed on other types of exits
            file_transfer_log.close_connection()
