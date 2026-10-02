"""Preview rebuilds and HTTP boundaries, without invoking local build tools."""

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from preview import Preview, handler_for, source_signature


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.source = self.directory / "theme"
        self.source.mkdir()
        (self.source / "theme.json").write_text('{"name":"Example"}')
        self.preview = Preview(self.source, self.directory, "/s/fixture", "renderer", "checker", "")

    def renderer(self, args, **_kwargs):
        output = Path(args[args.index("--output") + 1])
        output.mkdir()
        (output / "home.html").write_text("<h1>Example</h1>")
        (output / "__asset").mkdir()
        (output / "__asset" / "theme.css").write_text("body { color: black; }")
        (output / "manifest.json").write_text(json.dumps({"name":"Example", "pages":[{"title":"Home", "path":"/s/fixture/", "file":"home.html"}]}))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def test_rebuild_preserves_last_snapshot_and_retries_changed_source(self):
        with patch("preview.package") as package, patch("preview.subprocess.run", side_effect=self.renderer) as render:
            self.assertTrue(self.preview.rebuild())
            first = dict(self.preview.snapshot)
            self.assertFalse(self.preview.rebuild())
            self.assertEqual(render.call_count, 1)
            (self.source / "theme.json").write_text("broken")
            package.side_effect = ValueError("Missing section")
            self.assertFalse(self.preview.rebuild())
            self.assertEqual(self.preview.snapshot, first)
            self.assertEqual(self.preview.state()["revision"], 1)
            self.assertEqual(self.preview.state()["error"], "Missing section")
            self.assertFalse(self.preview.rebuild())
            self.assertEqual(package.call_count, 2)
            package.side_effect = None
            (self.source / "theme.json").write_text('{"name":"Fixed"}')
            self.assertTrue(self.preview.rebuild())
            self.assertEqual(self.preview.state()["revision"], 2)
            self.assertEqual(self.preview.state()["error"], "")

    def test_source_watch_ignores_dist_and_credentials_but_rejects_symlinks(self):
        first = source_signature(self.source)
        (self.source / ".env").write_text("must not be read or served")
        (self.source / "dist").mkdir()
        (self.source / "dist" / "theme.zip").write_bytes(b"new output")
        self.assertEqual(source_signature(self.source), first)
        (self.source / "assets").symlink_to(self.directory, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlinks"):
            source_signature(self.source)

    def test_http_serves_only_snapshot_and_blocks_rebinding_and_mutations(self):
        with patch("preview.package"), patch("preview.subprocess.run", side_effect=self.renderer):
            self.preview.rebuild()
        allowed = set()
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(self.preview, allowed))
        port = server.server_address[1]
        allowed.add(f"127.0.0.1:{port}")
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        def request(path, method="GET", headers=None):
            connection = HTTPConnection("127.0.0.1", port, timeout=2)
            connection.request(method, path, headers=headers or {})
            response = connection.getresponse()
            status, data, response_headers = response.status, response.read(), dict(response.getheaders())
            connection.close()
            return status, data, response_headers
        status, body, headers = request("/s/fixture/")
        self.assertEqual(status, 200)
        self.assertIn(b"<h1>Example</h1>", body)
        self.assertIn("form-action 'none'", headers["Content-Security-Policy"])
        self.assertIn("connect-src 'none'", headers["Content-Security-Policy"])
        self.assertIn("sandbox allow-scripts", headers["Content-Security-Policy"])
        self.assertNotIn("allow-same-origin", headers["Content-Security-Policy"])
        self.assertEqual(request("/s/fixture/__asset/theme.css")[0], 200)
        for route in ("/", "/theme.json", "/s/wrong/", "/s/fixture/.env", "/s/fixture/../theme.json", "/s/fixture/%2e%2e/theme.json"):
            self.assertEqual(request(route)[0], 404, route)
        self.assertEqual(request("/s/fixture/", headers={"Host":"attacker.example"})[0], 403)
        self.assertEqual(request("/s/fixture/", "POST")[0], 501)

    def test_snapshot_rejects_renderer_page_outside_output(self):
        def malicious(args, **kwargs):
            result = self.renderer(args, **kwargs)
            output = Path(args[args.index("--output") + 1])
            metadata = json.loads((output / "manifest.json").read_text())
            metadata["pages"][0]["file"] = str(self.source / "theme.json")
            (output / "manifest.json").write_text(json.dumps(metadata))
            return result
        with patch("preview.package"), patch("preview.subprocess.run", side_effect=malicious):
            self.assertFalse(self.preview.rebuild())
        self.assertEqual(self.preview.snapshot, {})
        self.assertIn("invalid page file", self.preview.error)


if __name__ == "__main__":
    unittest.main()
