import os
import socket
import tempfile
from threading import Thread
from time import sleep
from unittest.mock import patch

import pytest
import requests
from icecream import ic

from lib.server import TokenRangeHTTPRequestHandler, run


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
    file_content = b"0123456789abcdef" * 64  # 1024 bytes of predictable pattern

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
    assert (
        response.content == b"012345"
    )  # Check the content returned matches expected range


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
    response = requests.get(
        server_url + "/invalid/path", verify=False, timeout=3, allow_redirects=False
    )
    assert response.status_code in [200, 302, "ReadTimeout"]


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
    headers = {"Range": "bytes=1050-1065"}  # Provide a out of file size range
    response = requests.get(server_url + temp_file_path, headers=headers, verify=False)
    assert response.status_code == 416  # Expecting a Requested Range Not Satisfiable


def test_invalid_inverted_range(server_url, temp_file_path):
    """Test ranges that exceed the file size."""
    file_size = os.path.getsize(temp_file_path)
    headers = {"Range": f"bytes={file_size-10}-{100}"}
    response = requests.get(server_url + temp_file_path, headers=headers, verify=False)
    assert response.status_code == 416


def test_default_mime_type(server_url, temp_file_path):
    """Test that the server sets MIME type to 'application/octet-stream' for unknown file types."""
    response = requests.get(server_url + temp_file_path, verify=False)
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "application/octet-stream"


def test_content_disposition_attachment(server_url, temp_file_path):
    """Test that the server includes Content-Disposition header for files with allowed extensions."""
    with patch("lib.server.DOWNLOAD_EXTENSIONS", [".unknown"]):
        response = requests.get(server_url + temp_file_path, verify=False)
        filename = os.path.basename(temp_file_path)
        expected_header = f'attachment; filename="{filename}"'
        assert response.status_code == 200
        assert expected_header in response.headers["Content-Disposition"]


def test_boundary_range_request(server_url, temp_file_path):
    """Test range requests at the boundaries of the file."""
    file_size = os.path.getsize(temp_file_path)
    headers = {"Range": f"bytes=0-{file_size-1}"}
    response = requests.get(server_url + temp_file_path, headers=headers, verify=False)
    assert response.status_code == 206
    assert len(response.content) == file_size
    expected_content = (b"0123456789abcdef" * 64)[:file_size]
    assert response.content == expected_content


def test_single_side_range_request(server_url, temp_file_path):
    """Test range requests with only start or end specified."""
    # Start only
    headers_start = {"Range": "bytes=50-"}
    response_start = requests.get(
        server_url + temp_file_path, headers=headers_start, verify=False
    )
    assert response_start.status_code == 206
    expected_start_content = (b"0123456789abcdef" * 64)[50:]
    assert response_start.content == expected_start_content

    # End only
    headers_end = {"Range": "bytes=-50"}
    response_end = requests.get(
        server_url + temp_file_path, headers=headers_end, verify=False
    )
    assert response_end.status_code == 206
    expected_end_content = (b"0123456789abcdef" * 64)[-50:]
    assert response_end.content == expected_end_content


def test_overlapping_ranges(server_url, temp_file_path):
    """Test ranges that exceed the file size."""
    file_size = os.path.getsize(temp_file_path)
    headers = {"Range": f"bytes={file_size-10}-{file_size+100}"}
    response = requests.get(server_url + temp_file_path, headers=headers, verify=False)
    assert response.status_code == 416


def test_sequential_range_requests(server_url, temp_file_path):
    """Test handling of sequential range requests."""
    headers_first = {"Range": "bytes=0-10"}
    headers_second = {"Range": "bytes=11-20"}
    response_first = requests.get(
        server_url + temp_file_path, headers=headers_first, verify=False
    )
    response_second = requests.get(
        server_url + temp_file_path, headers=headers_second, verify=False
    )
    assert response_first.status_code == 206
    assert response_second.status_code == 206
    expected_content_first = (b"0123456789abcdef" * 64)[0:11]
    expected_content_second = (b"0123456789abcdef" * 64)[11:21]
    assert response_first.content == expected_content_first
    assert response_second.content == expected_content_second
