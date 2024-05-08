import os
from unittest.mock import MagicMock, patch

import pytest
from isort import io

from server import TokenRangeHTTPRequestHandler, file_transfer_log, token


def test_init(handler):
    assert (
        handler.file_transfer_log is file_transfer_log
    ), "FileTransferLog should be correctly initialized in handler"


@pytest.fixture
def handler():
    request = MagicMock()
    client_address = ("127.0.0.1", 8080)
    server = MagicMock()

    with patch.object(TokenRangeHTTPRequestHandler, "handle", return_value=None):
        handler_instance = TokenRangeHTTPRequestHandler(
            request, client_address, server, file_transfer_log=file_transfer_log
        )
        # Set necessary HTTP attributes
        handler_instance.requestline = "GET /public_html HTTP/1.1"
        handler_instance.request_version = (
            "HTTP/1.1"  # This is typically set by the base server
        )
        handler_instance.command = "GET"
        handler_instance.path = "/public_html"
        handler_instance.headers = {"Host": "localhost"}
        handler_instance.parse_request = MagicMock(return_value=True)
    return handler_instance


@pytest.fixture
def mock_os_path_exists():
    with patch("os.path.exists", return_value=True) as mock_exists:
        yield mock_exists


@pytest.fixture
def mock_os_listdir():
    with patch("os.listdir", return_value=["file1.txt", "file2.jpg"]) as mock_listdir:
        yield mock_listdir


def test_translate_path_valid_token_and_path(handler, mock_os_path_exists):
    # Ensuring the token is the one expected by the handler
    test_path = f"/{token}/resources/image.png"
    expected_path = os.path.join(os.getcwd(), "resources", "image.png")

    # Act
    actual_path = handler.translate_path(test_path)

    # Assert
    assert os.path.normpath(actual_path) == os.path.normpath(
        expected_path
    ), "Should translate valid path correctly"


def test_translate_path_root_request(handler):
    # Test when the path requests the root of a directory
    test_path = f"/{token}/"
    expected_path = os.path.join(
        os.getcwd(), "public_html", ""
    )  # Assuming root redirects to public_html

    # Act
    actual_path = handler.translate_path(test_path)

    # Assert
    assert os.path.normpath(actual_path) == os.path.normpath(
        expected_path
    ), "Root path should translate to public_html directory"


def test_translate_path_directory_request(handler):
    # Test when the path requests a directory without specifying a file
    test_path = f"/{token}/resources/"
    expected_path = os.path.join(os.getcwd(), "resources", "")

    # Act
    actual_path = handler.translate_path(test_path)

    # Assert
    assert os.path.normpath(actual_path) == os.path.normpath(
        expected_path
    ), "Directory path should translate correctly and include trailing slash handling if necessary"


def test_translate_path_permission_error(handler, mock_os_path_exists):
    # Simulate a permission error when accessing the filesystem
    with patch("os.path.join", side_effect=PermissionError):
        test_path = f"/{token}/resources/image.png"

        # Act and assert
        with pytest.raises(PermissionError):
            _ = handler.translate_path(test_path)


def test_translate_path_invalid_token(handler):
    # Test with an invalid token in the path
    test_path = "/wrong-token/resources/image.png"
    expected_path = (
        ""  # Assuming that an invalid token leads to an unauthorized response
    )

    # Act
    actual_path = handler.translate_path(test_path)

    # Assert
    assert (
        actual_path == expected_path
    ), "Should return an empty string for invalid token"


def test_translate_path_no_resource_directory(handler):
    # Test when path does not specify a resource or public_html directory
    test_path = f"/{token}/unrecognized/image.png"
    # Expect the path to be constructed under public_html, as your method does
    expected_path = os.path.join(os.getcwd(), "public_html", "unrecognized/image.png")

    # Act
    actual_path = handler.translate_path(test_path)

    # Assert
    assert os.path.normpath(actual_path) == os.path.normpath(
        expected_path
    ), "Should construct path under public_html even for unrecognized directories"


def test_directory_listing(handler, mock_os_listdir):
    # Substitute wfile with a BytesIO object to capture the output
    handler.wfile = io.BytesIO()

    # Execute the method which writes the directory listing to wfile
    handler.list_directory(handler.path)

    # Retrieve the output from wfile
    response = handler.wfile.getvalue().decode()

    # Assertions to check if the expected files are listed in the HTML response
    assert "file1.txt" in response, "Directory listing should include 'file1.txt'"
    assert "file2.jpg" in response, "Directory listing should include 'file2.jpg'"


@pytest.fixture
def mock_empty_listdir():
    with patch("os.listdir", return_value=[]) as mock:
        yield mock


def test_directory_listing_empty(handler, mock_empty_listdir):
    handler.wfile = io.BytesIO()
    handler.list_directory(handler.path)
    response = handler.wfile.getvalue().decode()
    assert (
        "<ul>\n</ul>" in response or "No files found" in response
    ), "Empty directory should be handled gracefully"


@pytest.fixture
def mock_listdir_failure():
    with patch("os.listdir", side_effect=OSError("No permission")) as mock:
        yield mock


def test_directory_listing_access_error(handler, mock_listdir_failure):
    response = handler.list_directory(handler.path)
    # Check if the method handles the error gracefully without raising an exception
    assert response is None, "Should handle access errors gracefully"


def test_directory_listing_format(handler, mock_os_listdir):
    # Patch the wfile where the HTTP response is written
    handler.wfile = io.BytesIO()

    # Run the method that doesn't return the output but writes directly to wfile
    handler.list_directory(handler.path)

    # Get the output from wfile
    response = handler.wfile.getvalue().decode()

    # Assertions based on the output written to wfile
    assert (
        "<html>" in response and "</html>" in response
    ), "Response should be formatted in HTML"
    assert "<ul>" in response and "</ul>" in response, "Should include list tags"
    assert (
        "file1.txt" in response and "file2.jpg" in response
    ), "Should list all files with links"


def test_directory_listing_includes_files(handler, mock_os_listdir):
    # Mock the wfile to capture output
    handler.wfile = io.BytesIO()

    # Execute the list_directory method, which writes to wfile
    handler.list_directory(handler.path)

    # Retrieve the output from wfile and decode it to a string for assertion
    response = handler.wfile.getvalue().decode()

    # Assertions to check if the expected files are listed in the HTML response
    assert "file1.txt" in response, "Directory listing should include 'file1.txt'"
    assert "file2.jpg" in response, "Directory listing should include 'file2.jpg'"


@pytest.fixture
def mock_os_listdir_with_directory():
    # No trailing slash in the mocked filesystem
    with patch("os.listdir", return_value=["file1.txt", "directory"]) as mock_listdir:
        yield mock_listdir


@pytest.fixture
def mock_os_path_isdir():
    # The isdir mock should return True for the directory path
    def mock_isdir(path):
        return path.endswith("directory")

    with patch("os.path.isdir", side_effect=mock_isdir) as mock_isdir:
        yield mock_isdir


def test_directory_listing_includes_directory(
    handler, mock_os_listdir_with_directory, mock_os_path_isdir
):
    # Mock the wfile to capture output
    handler.wfile = io.BytesIO()

    # Execute the list_directory method, which writes to wfile
    handler.list_directory(handler.path)

    # Retrieve the output from wfile and decode it to a string for assertion
    response = handler.wfile.getvalue().decode()

    # Assertions to check if directories are properly indicated in the HTML response
    assert (
        "directory/" in response
    ), "Directory listing should indicate 'directory' as a directory"
