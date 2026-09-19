#!/usr/bin/env python3
"""Deploy one checksum-pinned public game into an isolated persistent directory."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile

ARCHIVE_URL = "https://github.com/supercubegame/ridge-runner/releases/download/playtest-35445091317-1/RidgeRunner-web.zip"
ARCHIVE_SHA = "ad73d9ba67b3cf31f5c9ab57c84d1eeeb74653f748a73d76b5dc32c9b36192f5"
ARCHIVE_SIZE = 9423934
VERSION = {"game": "ridge-runner", "release": "playtest-35445091317-1", "archive_sha256": ARCHIVE_SHA}
PORT = 8060
SERVER = r'''
import functools,http.server,pathlib,sys,urllib.parse
root=pathlib.Path(sys.argv[1]).resolve()
class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map={**http.server.SimpleHTTPRequestHandler.extensions_map,".wasm":"application/wasm",".pck":"application/octet-stream"}
    def log_message(self,*args): pass
    def list_directory(self,path):
        self.send_error(404)
        return None
    def send_head(self):
        parts=pathlib.PurePosixPath(urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)).parts
        candidate=pathlib.Path(self.translate_path(self.path))
        if any(p.startswith(".") for p in parts if p != "/") or candidate.is_symlink() or not candidate.resolve().is_relative_to(root):
            self.send_error(404)
            return None
        return super().send_head()
    def end_headers(self):
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Cache-Control","no-store")
        super().end_headers()
http.server.ThreadingHTTPServer(("0.0.0.0",8060),functools.partial(Handler,directory=str(root))).serve_forever()
'''

def digest(data):
    return hashlib.sha256(data).hexdigest()

def safe_members(archive):
    members = archive.infolist()
    if not members or len(members) > 200:
        raise ValueError("ARCHIVE_FILE_COUNT")
    seen = set()
    total = 0
    for item in members:
        name = item.filename
        path = PurePosixPath(name)
        if (not name or "\\" in name or path.is_absolute() or
                any(p in (".", "..") or p.startswith(".") for p in path.parts) or
                stat.S_ISLNK(item.external_attr >> 16) or name in seen):
            raise ValueError("UNSAFE_ARCHIVE")
        seen.add(name)
        total += item.file_size
        if total > 150 * 1024 * 1024:
            raise ValueError("ARCHIVE_TOO_LARGE")
    if "index.html" not in seen or not any(n.endswith(".wasm") for n in seen) or not any(n.endswith(".pck") for n in seen):
        raise ValueError("MISSING_GAME_FILES")
    return members

def validate_url(value):
    if not isinstance(value, str):
        raise ValueError("PREVIEW_URL_TYPE")
    p = urllib.parse.urlsplit(value)
    host = p.hostname or ""
    if (p.scheme != "https" or p.username or p.password or p.query or p.fragment or
            not any(host.endswith(s) for s in (".lightning.ai", ".lightningapp.ai", ".cloudspaces.litng.ai"))):
        raise ValueError("PREVIEW_URL_NOT_SAFE_TO_PUBLISH")
    return value.rstrip("/")

def fetch_local(path):
    with urllib.request.urlopen("http://127.0.0.1:8060/" + path, timeout=5) as r:
        return r.read(), r.headers.get_content_type()

def deploy():
    result = {"status": "FAIL", "stage": "persistent_directory", "checks": {}}
    try:
        home = Path("/teamspace/studios/this_studio")
        if not home.is_dir():
            raise ValueError("PERSISTENT_HOME_NOT_FOUND")
        base = home / ".ridge-runner-preview"
        if base.is_symlink():
            raise ValueError("UNSAFE_DEPLOY_DIRECTORY")
        base.mkdir(mode=0o700, exist_ok=True)
        target = base / ARCHIVE_SHA
        result["stage"] = "download_and_verify"
        with urllib.request.urlopen(ARCHIVE_URL, timeout=45) as r:
            data = r.read(ARCHIVE_SIZE + 1)
        if len(data) != ARCHIVE_SIZE or digest(data) != ARCHIVE_SHA:
            raise ValueError("ARCHIVE_CHECKSUM_MISMATCH")
        result["checks"]["archive_checksum"] = True
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = safe_members(archive)
            manifest = {m.filename: digest(archive.read(m)) for m in members if not m.is_dir()}
            manifest["version.json"] = digest((json.dumps(VERSION, sort_keys=True) + "\n").encode())
            result["stage"] = "isolated_extract"
            if not target.exists():
                with tempfile.TemporaryDirectory(prefix="staging-", dir=base) as temp:
                    staging = Path(temp)
                    site = staging / "site"
                    site.mkdir()
                    for m in members:
                        p = site / m.filename
                        if m.is_dir():
                            p.mkdir(parents=True, exist_ok=True)
                        else:
                            p.parent.mkdir(parents=True, exist_ok=True)
                            p.write_bytes(archive.read(m))
                    (site / "version.json").write_text(json.dumps(VERSION, sort_keys=True) + "\n")
                    (staging / "server.py").write_text(SERVER)
                    staging.rename(target)
        site = target / "site"
        if target.is_symlink() or site.is_symlink():
            raise ValueError("UNSAFE_RELEASE_DIRECTORY")
        for name, expected in manifest.items():
            p = site / name
            if p.is_symlink() or not p.resolve().is_relative_to(site.resolve()) or digest(p.read_bytes()) != expected:
                raise ValueError("EXISTING_RELEASE_MISMATCH")
        if (target / "server.py").is_symlink() or (target / "server.py").read_text() != SERVER:
            raise ValueError("SERVER_SOURCE_MISMATCH")
        result["checks"]["extracted_files_match"] = True
        result["stage"] = "start_server"
        occupied = False
        with socket.socket() as s:
            try:
                s.bind(("0.0.0.0", PORT))
            except OSError:
                occupied = True
        if occupied:
            existing, _ = fetch_local("version.json")
            if json.loads(existing) != VERSION:
                raise ValueError("PORT_OCCUPIED_BY_OTHER_SERVICE")
            result["checks"]["reused_matching_service"] = True
        else:
            # Do not inherit platform credentials into the public static server.
            env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(home), "LANG": "C.UTF-8"}
            with (target / "server.log").open("ab") as log:
                child = subprocess.Popen([sys.executable, str(target / "server.py"), str(site)],
                                         stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                         cwd=target, env=env, start_new_session=True, close_fds=True)
            (target / "server.pid").write_text(str(child.pid) + "\n")
            ready = False
            for _ in range(30):
                try:
                    ready = json.loads(fetch_local("version.json")[0]) == VERSION
                    if ready:
                        break
                except Exception:
                    time.sleep(0.2)
            if not ready or child.poll() is not None:
                raise ValueError("SERVER_NOT_READY")
            result["checks"]["server_started"] = True
        result["stage"] = "loopback_asset_verification"
        for name, expected in manifest.items():
            body, mime = fetch_local(urllib.parse.quote(name))
            if digest(body) != expected:
                raise ValueError("HTTP_ASSET_MISMATCH")
            if name.endswith(".wasm") and mime != "application/wasm":
                raise ValueError("WASM_MIME_MISMATCH")
        result["checks"]["all_http_assets_match"] = True
        result["asset_count"] = len(manifest)
        result["release"] = VERSION["release"]
        result["status"] = "PASS"
        result["stage"] = "preview_port_registration"
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                from lightning_sdk import Studio
                studio = Studio()
                try:
                    url = studio.get_port_url(PORT)
                except Exception:
                    studio.add_ports(PORT)
                    url = studio.get_port_url(PORT)
                if not url:
                    studio.add_ports(PORT)
                    url = studio.get_port_url(PORT)
            result["preview_url"] = validate_url(url)
            result["preview_registration"] = "PASS"
        except Exception as error:
            result["preview_registration"] = "UNVERIFIED"
            result["preview_error_type"] = type(error).__name__
        result["stage"] = "complete"
    except Exception as error:
        result["error_type"] = type(error).__name__
        if isinstance(error, ValueError) and str(error).isupper() and len(str(error)) < 80:
            result["error_code"] = str(error)
    return result

if __name__ == "__main__":
    report = deploy()
    print("RIDGE_DEPLOY_JSON=" + json.dumps(report), flush=True)
    sys.exit(0 if report["status"] == "PASS" else 1)
