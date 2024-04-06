import html
import http.server
import io
import ssl
from secrets import token_urlsafe
import os
from urllib.parse import urlparse, quote
from icecream import ic

# Generate a secure token
token = token_urlsafe(16)  # Shorter token for readability; adjust length as needed


class TokenRangeHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        parsed_path = urlparse(path)
        path_parts = parsed_path.path.strip("/").split("/", 1)

        if len(path_parts) >= 1 and path_parts[0] == token:
            if len(path_parts) == 2:
                # Split the second part of the path to check for 'resources'
                resource_parts = path_parts[1].split("/", 1)

                if resource_parts[0] == 'resources':
                    # Accessing the 'resources' directory
                    new_path = '/' + (
                        resource_parts[1] if len(resource_parts) > 1 else '')
                    return os.path.join(os.getcwd(), 'resources', new_path.strip('/'))
                else:
                    # Accessing the 'public_html' directory
                    new_path = '/' + path_parts[1]
                    return os.path.join(os.getcwd(), 'public_html', new_path.strip('/'))
            else:
                # No specific file/directory requested; default to the root of 'public_html'
                return os.path.join(os.getcwd(), 'public_html', '')
        else:
            # Invalid or missing token; return an empty string to signal unauthorized access
            return ""

    def list_directory(self, path):
        """Generate and serve a simple directory listing."""
        try:
            list = os.listdir(path)
        except os.error:
            self.send_error(404, "No permission to list directory")
            return None
        list.sort(key=lambda a: a.lower())
        f = io.BytesIO()  # Use BytesIO to handle binary data

        # URL or path to the background image
        background_image_url = f'/{token}/resources/background.webp'

        displaypath = html.escape(quote(self.path))
        f.write(f'<!DOCTYPE html>\n'.encode())
        f.write(
            f'<html>\n<head>\n<title>Directory listing for {displaypath}</title>\n'.encode())
        # Include CSS for the background image
        f.write(
            f'<style>body {{ background-image: url("{background_image_url}"); background-size: cover; }}</style>\n'.encode())
        f.write(
            f'</head>\n<body>\n<h2>Directory listing for {displaypath}</h2>\n'.encode())
        f.write('<hr>\n<ul>\n'.encode())

        for name in list:
            fullname = os.path.join(path, name)
            displayname = linkname = name
            # Append / for directories or @ for symbolic links
            if os.path.isdir(fullname):
                displayname = name + "/"
                linkname = name + "/"
            if os.path.islink(fullname):
                displayname = name + "@"
                # Note: a link to a directory displays with @ and links with /
            f.write(
                f'<li><a href="{quote(linkname)}">{html.escape(displayname)}</a>\n'.encode())
        f.write('</ul>\n<hr>\n</body>\n</html>\n'.encode())
        length = f.tell()
        f.seek(0)
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.send_header("Content-Length", str(length))
        self.end_headers()
        if f:
            try:
                self.copyfile(f, self.wfile)
            finally:
                f.close()

    def do_GET(self):
        """Serve a GET request with support for range requests."""
        self.range = None
        range_header = self.headers.get('Range')
        if range_header:
            try:
                self.range = range_header.split('=')[1].split('-')
                self.range = (int(self.range[0]), int(self.range[1]) if self.range[1] else None)
            except ValueError:
                self.send_error(400, 'Invalid range request')
                return
        
        ic(self.path)
        path = self.translate_path(self.path)
        ic(path)
        if path == "":
            self.send_error(404, "File not found")
            return
            
        # Check if the path is a directory
        if os.path.isdir(path):
            if "index.html" in os.listdir(path):
                path = os.path.join(path, "index.html")
                self.send_header('Content-Type', 'text/html')
            else:
                ic()
                # This should automatically set the content type
                dir_content = self.list_directory(path)
                ic(dir_content)
                return dir_content
        else:
            # When serving files, especially HTML, ensure the content type is set if not automatically handled
            if path.endswith(".html"):
                self.send_header('Content-Type', 'text/html')

            try:
                f = open(path, 'rb')
            except OSError:
                self.send_error(404, "File not found")
                return

        try:
            fs = os.fstat(f.fileno())
            if self.range:
                start, end = self.range
                if not end or end >= fs.st_size:
                    end = fs.st_size - 1
                if start > fs.st_size or start > end:
                    self.send_error(416, 'Requested Range Not Satisfiable')
                    return
                length = end - start + 1
                f.seek(start)
                self.send_response(206)
                self.send_header('Content-Range', f'bytes {start}-{end}/{fs.st_size}')
                self.send_header('Content-Length', str(length))
                self.send_header('Accept-Ranges', 'bytes')
                self.end_headers()
                self.wfile.write(f.read(length))
            else:
                self.send_response(200)
                self.send_header('Content-Length', str(fs.st_size))
                self.send_header('Accept-Ranges', 'bytes')
                self.end_headers()
                self.copyfile(f, self.wfile)
        finally:
            f.close()

def run(server_class=http.server.HTTPServer, handler_class=TokenRangeHTTPRequestHandler, port=8000):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)

    # Use SSLContext instead of wrap_socket
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain('../cert/fullchain.pem', '../cert/privkey.pem')  # Specify your cert and key files

    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    
    print(f"https://myworldspots.com:{port}/{token}/")
    httpd.serve_forever()

if __name__ == '__main__':
    ic()
    run()
