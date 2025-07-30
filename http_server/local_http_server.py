import sys
sys.path.append("..")

import sqlite3
import urllib.parse
import ast
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import logging
from datetime import datetime

os.makedirs("logs", exist_ok=True)
log_filename = f"logs/http_server_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,  
    format='%(asctime)s - %(levelname)s - %(message)s'
)

filename = sys.argv[1]

class ArchiveHandler(BaseHTTPRequestHandler):
    global filename
    with open("../" + filename, 'r') as f_r:
        website_infos = json.load(f_r)
        entry = website_infos

    db_paths = [
        {
            "path": "/your/db/dir/" + entry['db_file'],
            "table": entry["db_name"]
        }
    ]

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        url = params.get("url", [None])[0]

        if not url:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Missing 'url' query parameter")
            return

        found_row = None

        for db_entry in self.db_paths:
            db_path = db_entry["path"]
            table_name = db_entry["table"]

            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                row = cursor.execute(
                    f"SELECT http_response, headers, body, content_length FROM {table_name} WHERE url = ?",
                    (url,)
                ).fetchone()
                print(f"SELECT http_response, headers, body, content_length FROM {table_name} WHERE url = {url};")
                if row:
                    found_row = row
                    break
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Database error: {e}".encode())
                return
            finally:
                conn.close()

        if not found_row:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"URL not found in archive")
            logging.info("URL:" + url + "|CT:None" + "|status:404")
            return

        http_code, raw_headers, body, content_length = found_row

        try:
            headers = ast.literal_eval(raw_headers)
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f"Header parse error: {e}".encode())
            return

        self.send_response(int(http_code))

        content_type = None

        for k, v in headers.items():
            key = k.decode() if isinstance(k, bytes) else k
            if key.lower() == "content-length": continue
            if key.lower() == "content-type":
                raw_val = v[0] if isinstance(v, list) and v else v
                content_type = raw_val.decode() if isinstance(raw_val, bytes) else raw_val
                continue
            for value in v:
                val = value.decode() if isinstance(value, bytes) else value
                self.send_header(key, val)

        if content_type is None:
            content_type = "None"

        if "html" in content_type:
            self.send_header("Content-Type", "text/html; charset=UTF-8")
        else:
            self.send_header("Content-Type", content_type)

        self.send_header("Content-Length", str(len(body.encode("utf-8"))))
        self.end_headers()

        if isinstance(body, str):
            body = body.encode("utf-8")
        self.wfile.write(body)
        logging.info("URL:" + url + "|CT:" + content_type + "|status:" + http_code)

def run(server_class=HTTPServer, handler_class=ArchiveHandler, port=8025):
    server_address = ("", port)
    httpd = server_class(server_address, handler_class)
    logging.info(f"Serving on port {port}...")
    httpd.serve_forever()

if __name__ == "__main__":
    run()
