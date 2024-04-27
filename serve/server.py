import html
import http
import io
import json
import os
import signal
import ssl
import sys
from datetime import datetime
from http.server import HTTPServer
from secrets import token_urlsafe
from socketserver import ThreadingMixIn
from types import FrameType
from typing import Any, Optional, Type, Union
from urllib.parse import quote, unquote, urlparse

from icecream import ic

from serve.logger import FileTransferLog

# Load config
with open("../config.json", "r") as f:
    config = json.load(f)

# Initialize your FileTransferLog instance
file_transfer_log = FileTransferLog("database.db")

# Access config values
URL = config["url"]
PORT = config["port"]
CERTFILE = config["certfile"]
KEYFILE = config["keyfile"]
DOWNLOAD_EXTENSIONS = config["download_extensions"]

# Generate a secure token
token = token_urlsafe(48)


class TokenRangeHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Custom HTTP request handler with token-based path translation and listing directory contents."""

    def __init__(self, *args, file_transfer_log: FileTransferLog, **kwargs):
        """
        Initialize the request handler instance with a reference to a FileTransferLog.

        Args:
            *args: Variable length argument list passed to the superclass initializer.
            file_transfer_log (Optional[FileTransferLog]): An instance of FileTransferLog to log file transfers.
            **kwargs: Arbitrary keyword arguments passed to the superclass initializer.
        """
        self.file_transfer_log = file_transfer_log
        super().__init__(*args, **kwargs)

    def translate_path(self, path: str) -> str:
        """
        Translate a request path to a filesystem path.

        This method overrides the SimpleHTTPRequestHandler's translate_path method to
        implement token-based access control and path translation.

        Args:
            path (str): The path from the HTTP request.

        Returns:
            str: The filesystem path corresponding to the request path.
        """
        parsed_path = urlparse(path)
        path_parts = parsed_path.path.strip("/").split("/", 1)

        if len(path_parts) >= 1 and path_parts[0] == token:
            if len(path_parts) == 2:
                # Decode percent-encoded characters
                decoded_path = unquote(path_parts[1])
                # ic(decoded_path)

                # Split the second part of the path to check for 'resources'
                resource_parts = decoded_path.split("/", 1)

                if resource_parts[0] == "resources":
                    # Accessing the 'resources' directory
                    new_path = "/" + (
                        resource_parts[1] if len(resource_parts) > 1 else ""
                    )
                    return os.path.join(os.getcwd(), "resources", new_path.strip("/"))
                else:
                    # Accessing the 'public_html' directory
                    new_path = "/" + path_parts[1]
                    return os.path.join(
                        os.getcwd(), "public_html", decoded_path.strip("/")
                    )
            else:
                # No specific file/directory requested; default to the root of 'public_html'
                return os.path.join(os.getcwd(), "public_html", "")
        else:
            # Invalid or missing token; return an empty string to signal unauthorized access
            return ""

    def list_directory(self, path: Union[str, os.PathLike]) -> None:
        """
        Generate and send a directory listing in HTML format to the client.

        This method overrides the SimpleHTTPRequestHandler's list_directory method to
        customize the appearance of directory listings. It directly writes the HTML
        listing to the HTTP response.

        Args:
            path (Union[str, os.PathLike]): The filesystem path to list contents for.
        """
        try:
            listing = os.listdir(path)
        except os.error:
            self.send_error(404, "No permission to list directory")
            return None
        listing.sort(key=lambda a: a.lower())
        f = io.BytesIO()

        display_path = html.escape(unquote(self.path))

        # Adjusted background image URL to include the token
        background_image_url = f"/{token}/resources/background.webp"

        f.write("<!DOCTYPE html>\n".encode())
        f.write("<html>\n<head>\n".encode())
        f.write(
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'.encode()
        )
        f.write("<title>Contents</title>\n".encode())
        # Updated CSS for cooler display
        f.write(
            f"""<style>
        body {{
            background-image: url("{background_image_url}");
            background-size: cover;
            color: white; /* Change text color to white */
            font-family: Arial, sans-serif; /* Use a more modern font */
            padding: 20px;
        }}
        h2 {{
            color: #f0f0f0; /* Lighter shade of white for heading */
        }}
        a {{
            color: #add8e6; /* Light blue color for links for better contrast */
            text-decoration: none; /* No underline */
        }}
        a:hover {{
            text-decoration: underline; /* Underline on hover */
        }}
        ul {{
            list-style-type: none; /* No bullets */
            padding: 0;
        }}
        li {{
            margin-bottom: 10px; /* Add space between items */
        }}
        </style>\n""".encode()
        )
        f.write("</head>\n<body>\n".encode())
        # Removed the verbose title, using a simple heading instead
        f.write("<h2>Contents</h2>\n".encode())
        f.write("<ul>\n".encode())

        for name in listing:
            fullname = os.path.join(path, name)
            displayname = linkname = name
            if os.path.isdir(fullname):
                displayname += "/"
                linkname += "/"

            # Here, the key change: prefix the token and the correctly encoded full path
            encoded_linkname = quote(linkname)
            # Use `display_path`, which already includes the token and the full path to the current directory.
            full_url = f"{display_path}{encoded_linkname}"

            f.write(
                f'<li><a href="{full_url}">{html.escape(displayname)}</a>\n'.encode()
            )
        length = f.tell()
        f.seek(0)
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.send_header("Content-Length", str(length))
        self.end_headers()
        if f:
            try:
                self.copyfile(f, self.wfile)  # type: ignore[misc]
            finally:
                f.close()
        return None

    def do_GET(self) -> None:
        """
        Handle a GET request.

        This method is called to handle each GET request received by the server. It handles
        serving files, directory listings, and implements range requests if specified.

        """
        self.range = None
        path = self.translate_path(self.path)
        client_ip = self.client_address[0]  # Client's IP address
        range_header = self.headers.get("Range")

        if range_header:
            try:
                self.range = range_header.split("=")[1].split("-")
                self.range = (
                    int(self.range[0]),
                    int(self.range[1]) if self.range[1] else None,
                )
                self.file_transfer_log.log_transfer(
                    path=self.path,
                    status="range-start",
                    start_byte=self.range[0],
                    end_byte=self.range[1] if self.range[1] else None,
                    client_ip=client_ip,
                )
            except ValueError:
                self.send_error(400, "Invalid range request")
                return

        # ic(path)
        if path == "":
            self.send_error(404, "File not found")
            return

        # Check if the path is a directory
        if os.path.isdir(path):
            if "index.html" in os.listdir(path):
                path = os.path.join(path, "index.html")
                self.send_header("Content-Type", "text/html")
            else:
                # ic()
                # This should automatically set the content type
                self.list_directory(path)
                return
        else:
            # When serving files, especially HTML, ensure the content type is set if not automatically handled
            if path.endswith(".html"):
                self.send_header("Content-Type", "text/html")

            # Log the start of a full file transfer here
            if not self.range:
                self.file_transfer_log.log_transfer(
                    path=path, status="start", client_ip=client_ip
                )

            try:
                f = open(path, "rb")
            except OSError as e:
                ic(e)
                self.send_error(404, "File not found")
                return

        try:
            fs = os.fstat(f.fileno())
            if self.range:
                start, end = self.range
                if not end or end >= fs.st_size:
                    end = fs.st_size - 1
                if start > fs.st_size or start > end:
                    self.send_error(416, "Requested Range Not Satisfiable")
                    return
                length = end - start + 1
                f.seek(start)
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{fs.st_size}")
                self.send_header("Content-Length", str(length))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                self.wfile.write(f.read(length))
                # Log the end of a range transfer here
                self.file_transfer_log.log_transfer(
                    path=path,
                    status="range-complete",
                    start_byte=start,
                    end_byte=end,
                    client_ip=client_ip,
                )
            else:
                self.send_response(200)
                self.send_header("Content-Length", str(fs.st_size))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                self.copyfile(f, self.wfile)  # type: ignore[misc]
                # Log the end of a full file transfer here
                self.file_transfer_log.log_transfer(
                    path=path, status="complete", client_ip=client_ip
                )
        except ssl.SSLEOFError:
            print(
                f"SSL connection closed prematurely by the client at {datetime.now()}."
            )
            # Log the premature closure here, if needed
            self.file_transfer_log.log_transfer(
                path=path, status="failed", client_ip=client_ip
            )
        finally:
            f.close()

    def send_error(
        self, code: int, message: Optional[str] = None, explain: Optional[str] = None
    ) -> None:
        """
        Send an HTTP error response to the client.

        This method overrides the SimpleHTTPRequestHandler's send_error method to customize
        error handling, such as redirecting on 404 errors.

        Args:
            code (int): The HTTP status code to send.
            message (Optional[str]): An optional human-readable message describing the error.
            explain (Optional[str]): An optional detailed explanation of the error.
        """
        if code == 404:
            self.send_response(302)  # 302 Found - Temporary redirect
            self.send_header("Location", URL)
            self.end_headers()
        else:
            super().send_error(code, message=message, explain=explain)

    def end_headers(self) -> None:
        """
        Send the headers to the client.

        This method is called by end_headers of SimpleHTTPRequestHandler to finalize sending
        the headers, with modifications to handle content disposition for file downloads.
        """
        try:
            # Extract the file extension from the requested path
            _, ext = os.path.splitext(self.path)
            # Check if the file extension is in our list of extensions to download
            if ext in DOWNLOAD_EXTENSIONS:
                # Set the Content-Disposition header to force a file download
                filename = os.path.basename(self.path)
                self.send_header(
                    "Content-Disposition", f'attachment; filename="{filename}"'
                )
        except AttributeError:
            # If self.path is not set or any other AttributeError occurs, handle it gracefully
            print(
                "Error handling headers: 'path' attribute is not set or other AttributeError."
            )

        # Continue with the standard header ending process
        super().end_headers()


# Create a threaded version of HTTPServer
class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""


def run(
    handler_class: Type[TokenRangeHTTPRequestHandler] = TokenRangeHTTPRequestHandler,
    port: int = PORT,
) -> None:
    """
    Starts an HTTPS server on a specified port with a given request handler class.

    This function configures and starts an HTTPS server running on the specified port,
    using the provided request handler class to handle incoming HTTPS requests. It
    utilizes SSLContext to secure the server.

    Args:
        handler_class: The request handler class that defines how to handle incoming HTTP requests.
                       This class should be a subclass of http.server.BaseHTTPRequestHandler
                       and override its methods to handle requests.
        port (int, optional): The port number on which the server should listen. Defaults to PORT.
    """
    server_address = ("", port)

    # Now using the threaded server with the file transfer log
    httpd = ThreadedHTTPServer(
        server_address,
        lambda *args, **kwargs: handler_class(
            *args, file_transfer_log=file_transfer_log, **kwargs
        ),
    )

    # Setup SSL context
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=CERTFILE, keyfile=KEYFILE)

    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)

    print(f"{URL}:{port}/{token}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        file_transfer_log.close_connection()
        print("Server stopped.")


shutdown_in_progress = False


def signal_handler(sig: int, frame: Optional[FrameType]) -> Any:
    """
    Handles incoming signals to initiate a graceful shutdown of the server.

    This function is designed to respond to SIGINT and SIGTERM signals by initiating
    a shutdown process for the server. It ensures that the file transfer log's
    connection is properly closed and any necessary cleanup is performed before
    terminating the process.

    Args:
        sig (int): The signal number.
        frame (FrameType): The current stack frame.
    """
    global shutdown_in_progress
    if not shutdown_in_progress:
        shutdown_in_progress = True
        print(f"Signal {sig} received, shutting down...")
        # Here, initiate the shutdown process, such as notifying threads to complete
        file_transfer_log.close_connection()
        # If you have threads or other resources to clean up, do so here
        sys.exit(0)


# Register handlers for multiple signals
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == "__main__":
    try:
        ic()
        run()
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        if not shutdown_in_progress:
            file_transfer_log.close_connection()  # Ensures the connection is closed on other types of exits
