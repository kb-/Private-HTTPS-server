import html
import http
import io
import json
import mimetypes
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

from logger import FileTransferLog

# Load config
# Load config
try:
    with open("config.json", "r") as f:
        config = json.load(f)
except FileNotFoundError:
    sys.exit("Error: Configuration file not found.")
except json.JSONDecodeError:
    sys.exit("Error: Configuration file is not valid JSON.")

# Initialize your FileTransferLog instance
file_transfer_log = FileTransferLog("database.db")

# Access config values
URL = config.get("url", False) or "https://localhost"
PORT = config.get("port", False) or 443
CERTFILE = config["certfile"]
KEYFILE = config["keyfile"]
DOWNLOAD_EXTENSIONS = config["download_extensions"]

# Generate a secure token
token = token_urlsafe(48)

print(f"Server will start at {URL}:{PORT}.")


class TokenRangeHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Custom HTTP request handler with token-based path translation and listing
    directory contents."""

    url = ""

    def __init__(self, *args, file_transfer_log: FileTransferLog, **kwargs):
        """
        Initialize the request handler instance with a reference to a FileTransferLog.

        Args: *args: Variable length argument list passed to the superclass
        initializer. file_transfer_log (Optional[FileTransferLog]): An instance of
        FileTransferLog to log file transfers. **kwargs: Arbitrary keyword arguments
        passed to the superclass initializer.
        """
        self.file_transfer_log = file_transfer_log
        self.root = False  # Initialize root variable
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
                # No specific file/directory requested; default to the root of
                # 'public_html'
                return os.path.join(os.getcwd(), "public_html", "")
        else:
            # Invalid or missing token; return an empty string to signal unauthorized
            # access
            return ""

    def list_directory(self, path: Union[str, os.PathLike]) -> Optional[io.BytesIO]:
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
            # Use `display_path`, which already includes the token and the full path
            # to the current directory.
            full_url = f"{display_path}{encoded_linkname}"

            f.write(
                f'<li><a href="{full_url}">{html.escape(displayname)}</a>\n'.encode()
            )
        f.write("</ul>\n".encode())
        f.write("</body>\n</html>\n".encode())
        length = f.tell()
        f.seek(0)
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.send_header("Content-Length", str(length))
        self.end_headers()
        # content = ""
        if f:
            try:
                self.copyfile(f, self.wfile)  # type: ignore[misc]
            finally:
                # content = f.getvalue().decode()  # Convert BytesIO content to a string
                f.close()
        return None

    def do_GET(self) -> None:
        """
        Handle a GET request.

        This method is called to handle each GET request received by the server. It
        handles serving files, directory listings, and implements range requests if
        specified.
        """
        # Translate the URL path to a filesystem path
        path = self.translate_path(self.path)

        # if self.path == "/":
        #     self.root = True

        # Check if the path resolved to a valid location
        if not path:  # or not os.path.exists(path):
            self.send_error(404, "File not found")
            return

        # Get the client's IP address for logging purposes
        client_ip = self.client_address[0]

        # Early parsing of the range header, no validation yet
        range_header = self.headers.get("Range")
        if range_header:
            try:
                unit, range_spec = range_header.split("=")
                parts = range_spec.split("-")
                start = int(parts[0]) if parts[0] else None
                end = int(parts[1]) if len(parts) > 1 and parts[1] else None
            except (ValueError, IndexError):
                self.send_error(400, "Invalid range request")
                return
        else:
            start = end = None

        # Check if the path is a directory
        if os.path.isdir(path):
            # Look for an index.html to serve as the directory's default file
            if "index.html" in os.listdir(path):
                path = os.path.join(path, "index.html")
            else:
                # ic()
                # No index.html found, generate a directory listing instead
                self.list_directory(path)
                return

        try:
            with open(path, "rb") as f:
                fs = os.fstat(f.fileno())
                fs_size = fs.st_size

                # Now validate and adjust the range with file size info
                if start is not None or end is not None:
                    if start is None and end is not None:
                        # 'bytes=-500' end only
                        start = max(0, fs_size - end)
                        end = fs_size - 1
                    elif end is None:
                        # 'bytes=500-' start only
                        end = fs_size - 1
                    if (end is not None and end >= fs_size) or (
                        start is not None and end is not None and start > end
                    ):
                        self.send_error(416, "Requested Range Not Satisfiable")
                        return

                    # Log the start of a range transfer
                    self.file_transfer_log.log_transfer(
                        path=self.path,
                        status="range-start",
                        start_byte=start,
                        end_byte=end if end else None,
                        client_ip=client_ip,
                    )

                    # Valid range: process it
                    if isinstance(start, int) and isinstance(end, int):
                        f.seek(start)
                        self.send_response(206)
                        self.send_header(
                            "Content-Range", f"bytes {start}-{end}/{fs_size}"
                        )
                        self.send_header("Content-Length", str(end - start + 1))
                        self.send_header("Accept-Ranges", "bytes")
                        self.end_headers()
                        self.wfile.write(f.read(end - start + 1))

                        self.file_transfer_log.log_transfer(
                            path=path,
                            status="range-complete",
                            start_byte=start,
                            end_byte=end,
                            client_ip=client_ip,
                        )
                    return

                self.file_transfer_log.log_transfer(
                    path=path, status="start", client_ip=client_ip
                )

                # For non-range requests, handle according to file extension
                self.send_response(200)
                # Determine MIME type using mimetypes module
                mime_type, _ = mimetypes.guess_type(path)
                if mime_type is None:
                    # Default to binary stream if unknown
                    mime_type = "application/octet-stream"

                _, ext = os.path.splitext(path)  # Extract file extension

                if ext in DOWNLOAD_EXTENSIONS:
                    filename = os.path.basename(path)
                    self.send_header(
                        "Content-Disposition", f'attachment; filename="{filename}"'
                    )
                self.send_header("Content-Type", mime_type)

                self.send_header("Content-Length", str(fs.st_size))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                self.copyfile(f, self.wfile)  # type: ignore[misc]
                self.file_transfer_log.log_transfer(
                    path=path, status="complete", client_ip=client_ip
                )
                f.close()
        except ssl.SSLEOFError:
            print(
                f"SSL connection closed prematurely by the client at {datetime.now()}."
            )
            # Log unexpected closure of SSL connection
            self.file_transfer_log.log_transfer(
                path=path, status="failed", client_ip=client_ip
            )
            f.close()
        except OSError:
            # File opening or other OS-level errors
            self.send_error(404, "File not found")
            return

    def send_error(
        self, code: int, message: Optional[str] = None, explain: Optional[str] = None
    ) -> None:
        """
        Send an HTTP error response to the client.

        This method overrides the SimpleHTTPRequestHandler's send_error method to
        customize error handling, such as redirecting on 404 errors.

        Args: code (int): The HTTP status code to send. message (Optional[str]): An
        optional human-readable message describing the error. explain (Optional[
        str]): An optional detailed explanation of the error.
        """
        if code == 404 and not self.root:  # Check if not already at URL
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
        handler_class: The request handler class that defines how to handle incoming
                       HTTP requests.
                       This class should be a subclass of http.server.
                       BaseHTTPRequestHandler and override its methods to handle
                       requests.
        port (int, optional): The port number on which the server should listen.
                       Defaults to PORT.
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

    if port == 443:
        handler_class.url = f"{URL}/{token}/"
        print(f"{URL}/{token}/")
    else:
        handler_class.url = f"{URL}:{port}/{token}/"
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
        run()
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        if not shutdown_in_progress:
            # Ensures the connection is closed on other types of exits
            file_transfer_log.close_connection()
