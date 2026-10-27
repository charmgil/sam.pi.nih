"""HTTP Range resume of PheWeb downloads (samkit.steps.pheweb.fetch) against a local server."""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from samkit.steps import pheweb

PAYLOAD = os.urandom(3 * (1 << 20) + 12345)


class Handler(BaseHTTPRequestHandler):
    etag = '"v1"'
    ranges = True
    cut_once_at: int | None = None  # drop the connection once after this many body bytes
    requests_seen: list = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        n = len(PAYLOAD)
        rng, if_range = self.headers.get("Range"), self.headers.get("If-Range")
        type(self).requests_seen.append(rng)
        start = 0
        if rng and self.ranges and (if_range is None or if_range == self.etag):
            start = int(rng.split("=")[1].rstrip("-"))
            if start >= n:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{n}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{n - 1}/{n}")
        else:
            self.send_response(200)
        self.send_header("Content-Length", str(n - start))
        self.send_header("ETag", self.etag)
        self.end_headers()
        body = PAYLOAD[start:]
        cut = type(self).cut_once_at
        if cut is not None:
            type(self).cut_once_at = None
            self.wfile.write(body[:cut])
            self.wfile.flush()
            self.close_connection = True
            self.connection.shutdown(2)
            return
        self.wfile.write(body)


class Log:
    def __init__(self):
        self.lines = []

    def info(self, msg):
        self.lines.append(msg)


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setattr(pheweb.time, "sleep", lambda s: None)
    Handler.etag, Handler.ranges, Handler.cut_once_at, Handler.requests_seen = '"v1"', True, None, []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/download/X"
    srv.shutdown()


def _partial(tmp_path, url, nbytes, validator='"v1"'):
    part = tmp_path / "x.tsv.gz.part"
    part.write_bytes(PAYLOAD[:nbytes])
    state = {"url": url, "total": len(PAYLOAD), "validator": validator}
    (tmp_path / "x.tsv.gz.part.json").write_text(json.dumps(state))
    return part


def test_resumes_partial_file(server, tmp_path):
    part = _partial(tmp_path, server, 1 << 20)
    got, resumed = pheweb.fetch(server, part, Log())
    assert resumed and got == len(PAYLOAD) and part.read_bytes() == PAYLOAD
    assert Handler.requests_seen == [f"bytes={1 << 20}-"]
    assert not (tmp_path / "x.tsv.gz.part.json").exists()


def test_changed_remote_file_restarts(server, tmp_path):
    part = _partial(tmp_path, server, 1 << 20, validator='"old"')
    got, resumed = pheweb.fetch(server, part, Log())  # If-Range mismatch -> server sends 200
    assert not resumed and part.read_bytes() == PAYLOAD


def test_dropped_connection_is_resumed(server, tmp_path):
    Handler.cut_once_at = 1_500_000
    part = tmp_path / "x.tsv.gz.part"
    got, resumed = pheweb.fetch(server, part, Log())
    assert resumed and part.read_bytes() == PAYLOAD
    assert Handler.requests_seen[0] is None and Handler.requests_seen[1].startswith("bytes=")


def test_no_range_support_starts_over(server, tmp_path):
    Handler.ranges = False
    part = _partial(tmp_path, server, 1 << 20)
    got, resumed = pheweb.fetch(server, part, Log())
    assert not resumed and part.read_bytes() == PAYLOAD


def test_partial_without_state_is_not_trusted(server, tmp_path):
    part = tmp_path / "x.tsv.gz.part"
    part.write_bytes(b"garbage from an older version")
    pheweb.fetch(server, part, Log())
    assert part.read_bytes() == PAYLOAD and Handler.requests_seen == [None]
