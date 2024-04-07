
# Simple personal HTTPS encrypted file server

## Overview

Share files from your home with a simple URL.
This project implements a secure file server in Python, designed for private files serving over HTTPS with unique token-based access control. It supports range requests for efficient data transfer and logs all file transfer events to a SQLite database for auditing and analysis. The server is built to handle multiple concurrent connections by leveraging threading, ensuring robust performance.

## Basic usage

- Put your files and folders under _server/serve/public_html_  
- Share the unique URL given by the server
https://myIP:8000/5_UjznnDUlqagVEkA4hUz_tjEmrNCeypUJ6wqQqW4mEv3TyWRypbPePZxM8Y4T2f/

## Features

- **HTTPS Support**: Ensures all data transferred between the client and server is encrypted, providing confidentiality and integrity.
- **Token-Based Access Control**: Limits access to files based on a secure token, enhancing security by preventing unauthorized file access.
- **Range Requests**: Supports partial file transfers, allowing clients to resume interrupted downloads without starting over.
- **Concurrent Connections**: Utilizes threading to handle multiple simultaneous requests, ensuring the server can scale to support many users.
- **Transfer Logging**: Logs detailed information about each file transfer to a SQLite database, including timestamps, file paths, client IP addresses, and transfer status, facilitating auditing and monitoring.
- **Custom Directory Listings**: Provides styled HTML listings of directories, making navigation and file access user-friendly.

## Installation

1. **Clone the repository**:
2. **Set up a virtual environment**:
This project was developed using Python 3.12.2. We recommend using pyenv to avoid changing you system Python.
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install dependencies**:
   ```
   pip install -r requirements.txt
   ```

## Configuration

Before running the server, configure it by editing the `config.json` file. The following settings are available:

- `url`: The URL the server will listen on (https://yourdomain.com or https://yourIP).
- `port`: The port number the server will use (set up your router port forwarding if required).
- `certfile`: Path to the SSL certificate file for HTTPS.
- `keyfile`: Path to the SSL key file for HTTPS.
- `download_extensions`: A list of file extensions that should trigger a download in the browser.

For a more secure and user-friendly experience, consider using certificates from Let's Encrypt if you own a domain. Let's Encrypt provides free, automated, and open certificates recognized by most browsers, avoiding the common trust issues associated with self-signed certificates.

## Running the Server

To start the server, run:

```
cd "serve"
python server.py
```

The server will start and print an access URL containing a unique token to the console. Try accessing the server by navigating to the provided URL in a web browser.  
Share this URL to share your files.

## Security Considerations

- HTTPS ensures privacy by encrypting transferred data and the full URL of the resources being accessed. This means that the data and specific path and query parameters of the URL (unique token, your folder names and file names) are not visible to eavesdroppers. **However, IP address and domain name may be intercepted.**
- Make sure to only share the unique URL with trusted persons. Restart the server to generate a new URL token and keep URL confidential to prevent unauthorized access.
- Ensure the SSL certificate and key are securely generated and stored.
- You can monitor the log file for any unusual or unauthorized access patterns. The log can be read using an SQLite DB browser.
- It is your own responsibility to use this server code respectfully of the laws of your jurisdiction.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
