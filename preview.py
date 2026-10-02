"""Watch theme source and serve isolated, read-only rendered snapshots."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import mimetypes
import os
import secrets
import shutil
import stat
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from archive import BUNDLE_DIRECTORIES, BUNDLE_FILES, is_ds_store
from package import package

MAX_FILES = 2000
MAX_BYTES = 100 * 1024 * 1024
FRAME_CSP = (
    "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https:; "
    "img-src 'self' data: https:; font-src 'self' https: data:; media-src 'self' https:; "
    "connect-src 'none'; form-action 'none'; base-uri 'none'; object-src 'none'; "
    "frame-src 'none'; sandbox allow-scripts"
)


def source_signature(root: Path) -> str:
    """Only authoring inputs count; do not follow links or read unrelated files."""
    digest = hashlib.sha256()
    count = size = 0
    stack = [root / name for name in (*BUNDLE_DIRECTORIES, "src", *BUNDLE_FILES)]
    while stack:
        path = stack.pop()
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise ValueError(f"theme source symlinks are not supported: {path.relative_to(root)}")
        if stat.S_ISDIR(info.st_mode):
            stack.extend(sorted(path.iterdir(), reverse=True))
            continue
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f"unsupported theme source file: {path.relative_to(root)}")
        if is_ds_store(path):
            continue
        count += 1
        size += info.st_size
        if count > MAX_FILES or size > MAX_BYTES:
            raise ValueError("preview source exceeds 2,000 files or 100 MiB")
        digest.update(f"{path.relative_to(root).as_posix()}\0{info.st_size}:{info.st_mtime_ns}:{info.st_ctime_ns}\0".encode())
    return digest.hexdigest()


def renderer_path(value: str | None) -> str:
    value = value or os.environ.get("TRINGIFY_THEME_PREVIEW") or shutil.which("theme-preview-render")
    if not value:
        sibling = Path(__file__).with_name("theme-preview-render.exe" if os.name == "nt" else "theme-preview-render")
        if sibling.is_file():
            value = str(sibling)
    if not value:
        raise ValueError("theme-preview-render is required: pass --renderer or set TRINGIFY_THEME_PREVIEW")
    return str(value)


class Preview:
    def __init__(self, root: Path, temporary: Path, base: str, renderer: str, checker: str | None, preset: str):
        self.root = root.resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("theme root must be a directory")
        self.temporary, self.base = temporary, base
        self.renderer, self.checker, self.preset = renderer, checker, preset
        self.lock = threading.Lock()
        self.snapshot: dict[str, tuple[bytes, str]] = {}
        self.manifest: dict = {"name": self.root.name, "pages": []}
        self.revision = 0
        self.error = ""
        self.signature: str | None = None
        self.stopped = threading.Event()

    def rebuild(self) -> bool:
        try:
            signature = source_signature(self.root)
            if signature == self.signature:
                return False
            # A failed revision is retried only when its source changes.
            self.signature = signature
            with tempfile.TemporaryDirectory(dir=self.temporary, prefix="build-") as directory:
                work = Path(directory)
                bundle, output = work / "theme.zip", work / "rendered"
                package(self.root, bundle, checker=self.checker)
                result = subprocess.run(
                    [self.renderer, "--bundle", str(bundle), "--output", str(output), "--base", self.base, "--preset", self.preset],
                    capture_output=True, text=True, timeout=90, check=False,
                )
                if result.returncode:
                    raise ValueError((result.stderr or result.stdout).strip() or "theme rendering failed")
                manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
                pages = manifest.get("pages")
                if not isinstance(pages, list) or not pages:
                    raise ValueError("renderer returned no preview pages")
                snapshot: dict[str, tuple[bytes, str]] = {}
                total = 0
                for page in pages:
                    route, filename = page["path"], page["file"]
                    if not isinstance(route, str) or not route.startswith(self.base + "/") or "?" in route or "#" in route:
                        raise ValueError("renderer returned an invalid preview route")
                    file = output / filename
                    if file.is_symlink() or not file.resolve().is_relative_to(output.resolve()):
                        raise ValueError("renderer returned an invalid page file")
                    data = file.read_bytes()
                    bridge = b"<script>parent.postMessage({type:'tringify-preview-page',path:location.pathname},'*')</script>"
                    data += bridge
                    total += len(data)
                    snapshot[route] = (data, "text/html; charset=utf-8")
                for folder in ("__asset", "__demo-image"):
                    for file in sorted((output / folder).rglob("*")):
                        if file.is_symlink():
                            raise ValueError("renderer returned a symlink asset")
                        if file.is_file():
                            data = file.read_bytes()
                            total += len(data)
                            mime = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
                            snapshot[self.base + "/" + file.relative_to(output).as_posix()] = (data, mime)
                if total > 128 * 1024 * 1024:
                    raise ValueError("rendered preview exceeds 128 MiB")
                with self.lock:
                    self.snapshot, self.manifest = snapshot, manifest
                    self.revision += 1
                    self.error = ""
                print(f"Preview updated: {manifest['name']} · {len(pages)} pages", flush=True)
                return True
        except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
            message = str(exc)[:8000]
            with self.lock:
                changed = self.error != message
                self.error = message
            if changed:
                print(f"Preview needs attention: {message}", flush=True)
            return False

    def watch(self) -> None:
        while not self.stopped.wait(1):
            self.rebuild()

    def state(self) -> dict:
        with self.lock:
            return {"revision": self.revision, "error": self.error, "name": self.manifest["name"], "pages": self.manifest["pages"]}


def handler_for(preview: Preview, allowed_hosts: set[str]) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args) -> None:
            pass

        def send(self, status: int, data: bytes, mime: str, *, frame: bool = False) -> None:
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", FRAME_CSP if frame else "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            if self.headers.get("Host", "") not in allowed_hosts:
                self.send(403, b"Host not allowed", "text/plain")
                return
            route = unquote(urlsplit(self.path).path)
            if route == preview.base + "/studio":
                self.send(200, STUDIO.replace("__BASE__", preview.base).encode(), "text/html; charset=utf-8")
            elif route == preview.base + "/state":
                self.send(200, json.dumps(preview.state()).encode(), "application/json")
            else:
                with preview.lock:
                    item = preview.snapshot.get(route)
                if item is None:
                    self.send(404, b"This page is not part of the local preview.", "text/plain")
                else:
                    self.send(200, item[0], item[1], frame=True)

    return Handler


def serve(root: Path, host: str = "127.0.0.1", port: int = 9292, renderer: str | None = None, checker: str | None = None, preset: str = "") -> None:
    address = ipaddress.ip_address(host)
    if address.version != 4:
        raise ValueError("preview currently requires an IPv4 address")
    if not 0 <= port <= 65535:
        raise ValueError("port must be between 0 and 65535")
    if str(address) == "0.0.0.0":
        raise ValueError("use the specific LAN IP for remote preview, or 127.0.0.1 for local preview")
    executable = renderer_path(renderer)
    base = "/s/" + secrets.token_urlsafe(24)
    with tempfile.TemporaryDirectory(prefix="tringify-theme-preview-") as temporary:
        preview = Preview(root, Path(temporary), base, executable, checker, preset)
        allowed: set[str] = set()
        server = ThreadingHTTPServer((host, port), handler_for(preview, allowed))
        actual_port = server.server_address[1]
        allowed.add(f"{host}:{actual_port}")
        if address.is_loopback:
            allowed.add(f"localhost:{actual_port}")
        worker = threading.Thread(target=preview.watch, daemon=True)
        try:
            preview.rebuild()
            worker.start()
            print(f"Open http://{host}:{actual_port}{base}/studio", flush=True)
            print("Local sample preview. Shopper actions are disabled. Press Ctrl+C to stop.", flush=True)
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            pass
        finally:
            preview.stopped.set()
            server.server_close()
            if worker.is_alive():
                worker.join(timeout=95)


STUDIO = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Theme preview · Tringify</title>
<style>
*{box-sizing:border-box}body{margin:0;color:#171717;background:#f4f4f4;font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}button,select{font:inherit;color:inherit}header{background:white;border-bottom:1px solid #ddd;padding:14px 24px;display:flex;align-items:center;gap:24px;justify-content:space-between}h1{font-size:16px;line-height:1.3;margin:0;font-weight:650}.caption{color:#666;font-size:12px;margin-top:3px}.controls{display:flex;align-items:center;gap:16px;flex-wrap:wrap}label{display:flex;align-items:center;gap:8px}select{max-width:280px;min-width:160px;background:#fff;padding:8px 28px 8px 10px;border:1px solid #ccc;border-radius:6px}.devices{display:flex;border:1px solid #ccc;border-radius:6px;padding:3px;gap:3px}button{border:0;background:transparent;border-radius:3px;padding:5px 12px;cursor:pointer}button[aria-pressed=true]{background:#171717;color:white}:focus-visible{outline:2px solid #0066cc;outline-offset:3px}.status{font-size:12px;color:#555;padding:8px 24px;background:#fff;border-bottom:1px solid #ddd}.error{white-space:pre-wrap;overflow-wrap:anywhere;margin:0;padding:16px 24px;background:#fff5ed;border-bottom:1px solid #e2b18d;font:13px/1.5 ui-monospace,monospace}.canvas{height:calc(100dvh - 112px);padding:24px;display:flex;justify-content:center;align-items:stretch}iframe{width:100%;height:100%;border:1px solid #ddd;background:white;min-width:0}.canvas.mobile iframe{width:390px;max-width:100%}.empty{margin:auto;color:#555;text-align:center;padding:40px}body.has-error .canvas{height:65dvh}@media(max-width:750px){header{padding:12px 16px;align-items:flex-start;gap:12px;flex-direction:column}.controls{width:100%;gap:8px;justify-content:space-between}label{flex:1;min-width:0}select{min-width:0;width:100%;max-width:none}.caption{font-size:12px}.status{padding:8px 16px}.canvas{padding:12px;height:calc(100dvh - 160px)}button{padding:5px 10px}}
</style></head><body>
<header><div><h1 id="name">Theme preview</h1><div class="caption">Local sample data · Shopper actions are disabled</div></div><div class="controls"><label>Page <select id="pages" aria-label="Preview page"></select></label><div class="devices" aria-label="Preview width"><button type="button" data-device="desktop" aria-pressed="true">Desktop</button><button type="button" data-device="mobile" aria-pressed="false">Mobile</button></div></div></header>
<div class="status" role="status" id="status">Building your preview…</div><pre class="error" id="error" hidden></pre><main class="canvas" id="canvas"><div class="empty" id="empty">Your theme will appear here after a successful build.</div><iframe id="preview" title="Rendered theme" sandbox="allow-scripts" referrerpolicy="no-referrer" hidden></iframe></main>
<script>
const base='__BASE__',pages=document.getElementById('pages'),frame=document.getElementById('preview');let revision=-1,signature='',lastPath='';
window.addEventListener('message',event=>{if(event.source!==frame.contentWindow||event.data?.type!=='tringify-preview-page')return;const path=event.data.path;if([...pages.options].some(option=>option.value===path)){pages.value=path;lastPath=path;sessionStorage.setItem(base,path)}});
function openPage(){lastPath=pages.value;frame.src=lastPath;sessionStorage.setItem(base,lastPath)}
pages.addEventListener('change',openPage);
document.querySelectorAll('[data-device]').forEach(button=>button.addEventListener('click',()=>{document.getElementById('canvas').classList.toggle('mobile',button.dataset.device==='mobile');document.querySelectorAll('[data-device]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)))}));
async function update(){try{const response=await fetch(base+'/state');if(!response.ok)throw Error();const state=await response.json();document.getElementById('name').textContent=state.name;document.getElementById('error').hidden=!state.error;document.getElementById('error').textContent=state.error;document.body.classList.toggle('has-error',!!state.error);document.getElementById('status').textContent=state.error?(state.revision?'Build failed. Showing the last successful preview.':'Fix the build error to start the preview.'):'Watching for changes · '+state.pages.length+' pages';if(state.revision!==revision&&state.pages.length){const current=pages.value||sessionStorage.getItem(base),nextSignature=JSON.stringify(state.pages);if(nextSignature!==signature){pages.replaceChildren(...state.pages.map(p=>{const o=document.createElement('option');o.value=p.path;o.textContent=p.title;return o}));if(state.pages.some(p=>p.path===current))pages.value=current;signature=nextSignature}revision=state.revision;frame.hidden=false;document.getElementById('empty').hidden=true;openPage()}}catch{document.getElementById('status').textContent='Preview disconnected. Restart the preview command to reconnect.'}finally{setTimeout(update,1000)}}update();
</script></body></html>'''
