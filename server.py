#!/usr/bin/env python3
from http.server import HTTPServer, SimpleHTTPRequestHandler
import json, os, shutil
from datetime import datetime

SAVEABLE = {'/games.json', '/discovery.json'}
BACKUP_DIR = 'backups'
MAX_BACKUPS = 20  # keep last 20 saves per file

def backup(filename):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    name = filename.replace('.json', '')
    dst = os.path.join(BACKUP_DIR, f'{name}_{ts}.json')
    if os.path.exists(filename):
        shutil.copy2(filename, dst)
    # rotate: keep only the last MAX_BACKUPS per file prefix
    all_backups = sorted(
        f for f in os.listdir(BACKUP_DIR) if f.startswith(name + '_')
    )
    for old in all_backups[:-MAX_BACKUPS]:
        os.remove(os.path.join(BACKUP_DIR, old))

class Handler(SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path in SAVEABLE:
            length = int(self.headers.get('Content-Length', 0))
            data = self.rfile.read(length)
            filename = self.path.lstrip('/')
            backup(filename)
            with open(filename, 'wb') as f:
                f.write(data)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        else:
            self.send_response(403)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass

os.chdir(os.path.dirname(os.path.abspath(__file__)))
print('GameLog server running at http://localhost:7432')
print(f'Backups: ./{BACKUP_DIR}/ (last {MAX_BACKUPS} per file)')
HTTPServer(('', 7432), Handler).serve_forever()
