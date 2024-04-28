import os
import socket
import tempfile
from threading import Thread
from time import sleep
from unittest.mock import patch

import pytest
import requests
from icecream import ic

from server import TokenRangeHTTPRequestHandler, run


def is_server_ready(host, port):
    """Check if the server is up by attempting to connect."""
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def server_url():
    server_thread = Thread(target=run)
    server_thread.daemon = True
    server_thread.start()

    # Ensure server is ready
    while not is_server_ready("localhost", 443):
        sleep(0.1)  # Small sleep to avoid hammering the server

    # Retrieve the URL from the TokenRangeHTTPRequestHandler class
    url = TokenRangeHTTPRequestHandler.url
    return url


def test_server_response(server_url):
    """Test that the server responds correctly to a GET request."""
    response = requests.get(server_url, verify=False)
    assert response.status_code == 200


@pytest.fixture(scope="session")
def temp_file_path(request):
    # Determine the extension for the temporary file
    extension = "unknown"  # Use the first extension from the list
    file_content = b"Temporary file content"

    # Create a temporary file with the specified extension
    with tempfile.NamedTemporaryFile(
        dir="public_html", delete=False, suffix=f".{extension}"
    ) as temp_file:
        temp_file.write(file_content)
        temp_file_path = temp_file.name

    # Define a finalizer to ensure the temporary file is closed and deleted
    def finalize():
        try:
            # Close the temporary file to release its resources
            temp_file.close()
        finally:
            # Attempt to delete the file with retries
            retries = 3
            for _ in range(retries):
                try:
                    os.unlink(temp_file_path)
                    break  # File deletion successful, exit loop
                except Exception:
                    sleep(0.1)  # Short delay before retrying

    # Register the finalizer
    request.addfinalizer(finalize)

    # Return the path to the temporary file
    ic(temp_file_path)
    return temp_file_path


def test_range_header(server_url, temp_file_path):
    """Test that the server handles Range header correctly."""
    headers = {"Range": "bytes=0-5"}  # Define your desired range here
    response = requests.get(server_url + temp_file_path, headers=headers, verify=False)
    assert response.status_code == 206  # Expected status code for partial content


def test_invalid_range_header(server_url):
    """Test that the server handles invalid Range header correctly."""
    headers = {"Range": "invalid_range_format"}  # Provide a malformed range header
    response = requests.get(server_url, headers=headers, verify=False)
    assert response.status_code == 400  # Expecting a 400 Bad Request response


def test_incoherent_range(server_url, temp_file_path):
    """Test that the server handles Range header correctly."""
    headers = {"Range": "bytes=5-0"}  # Define your desired range here
    response = requests.get(server_url + temp_file_path, headers=headers, verify=False)
    assert response.status_code == 416  # Requested Range Not Satisfiable


# Test case for handling invalid file path
def test_invalid_file_path(server_url):
    response = requests.get(server_url + "/invalid/path", verify=False)
    assert response.status_code == 404


def test_index_html_exists(server_url, temp_file_path, temp_index_html):
    """Test that the server serves index.html if it exists."""
    # Assume index.html exists in the public_html directory
    response = requests.get(server_url, verify=False)
    assert response.status_code == 200
    assert "Temporary Index HTML" in response.text


@pytest.fixture(scope="session")
def temp_index_html(request):
    # Create a temporary index.html file within the public_html directory
    with open("public_html/index.html", "w") as temp_file:
        temp_file.write("<html><body><h1>Temporary Index HTML</h1></body></html>")

    # Define a finalizer to ensure the temporary file is deleted after the test
    def finalize():
        os.remove("public_html/index.html")

    request.addfinalizer(finalize)


def test_invalid_range(server_url, temp_file_path):
    """Test that the server handles Requested Range Not Satisfiable"""
    headers = {"Range": "bytes=1000-1005"}  # Provide a out of file size range
    response = requests.get(server_url + temp_file_path, headers=headers, verify=False)
    assert response.status_code == 416  # Expecting a Requested Range Not Satisfiable


def test_default_mime_type(server_url, temp_file_path):
    """Test that the server sets MIME type to 'application/octet-stream' for unknown file types."""
    response = requests.get(server_url + temp_file_path, verify=False)
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "application/octet-stream"


def test_content_disposition_attachment(server_url, temp_file_path):
    """Test that the server includes Content-Disposition header for files with allowed extensions."""
    with patch("server.DOWNLOAD_EXTENSIONS", [".unknown"]):
        response = requests.get(server_url + temp_file_path, verify=False)
        filename = os.path.basename(temp_file_path)
        expected_header = f'attachment; filename="{filename}"'
        assert response.status_code == 200
        assert expected_header in response.headers["Content-Disposition"]
