import contextlib
import copy
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid

import import_example as example


SAMPLE = Path(example.__file__).with_name("example.json")


class ImportExampleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.session = self.directory / "session"
        self.session.write_text("test-human-session\n")
        self.session.chmod(0o600)
        self.plan = example.build_plan(SAMPLE)

    def receipt(self, completed=False):
        return {"id": self.plan["import_id"], "declaration": self.plan["declaration"],
                "completed": completed, "next_batch": 5 if completed else 0,
                "chain_sha256": self.plan["declaration"]["plan_sha256"] if completed else "0" * 64,
                "source_verified": completed, "report_received": completed}

    @contextlib.contextmanager
    def server(self, responder):
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def handle_request(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                requests.append((self.command, self.path, body, dict(self.headers)))
                status, value = responder(self.command, self.path)
                data = value if isinstance(value, bytes) else example.encoded(value)
                self.send_response(status)
                self.send_header("Location", "/redirect-target")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_PUT = do_POST = handle_request

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}", requests
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def responder(self, method, path):
        if path == "/api/v1/context":
            return 200, {"organization_id": "example-community"}
        if "/batches/" in path:
            return 202, self.receipt()
        return 200, self.receipt(path.endswith("/complete"))

    def test_sample_mapping_and_exact_chain(self):
        self.assertEqual(self.plan["counts"]["members"], 2)
        self.assertEqual(self.plan["counts"]["contents"], 1)
        self.assertEqual(self.plan["counts"]["comments"], 1)
        self.assertEqual([kind for kind, body in self.plan["batches"]],
                         ["source", "members", "stage-content", "publish-content", "report"])
        self.assertEqual(self.plan["declaration"]["batch_count"], 5)
        self.assertEqual(self.plan["batches"][2][1], self.plan["batches"][3][1])
        original = SAMPLE.read_bytes()
        self.assertEqual(self.plan["batches"][0][1], original)
        members = json.loads(self.plan["batches"][1][1])
        content = json.loads(self.plan["batches"][2][1])[0]
        self.assertEqual(members["accounts"], [])
        self.assertEqual(content["content"]["authorship"]["member_id"], members["members"][0]["id"])
        self.assertEqual(content["comments"][0]["sequence"], 1)
        self.assertEqual(content["content"]["engagement"], {"views": 0})
        self.assertIn("**next steps**", content["content"]["body"])
        chain = "0" * 64
        for kind, body in self.plan["batches"]:
            body_digest = hashlib.sha256(body).hexdigest()
            chain = hashlib.sha256((chain + ":" + kind + ":" + body_digest).encode()).hexdigest()
        self.assertEqual(chain, self.plan["declaration"]["plan_sha256"])
        report = json.loads(self.plan["batches"][-1][1])
        self.assertEqual(report["source_snapshot_sha256"], hashlib.sha256(original).hexdigest())
        self.assertEqual(report["counts"], self.plan["counts"])
        self.assertEqual(len(report["counts"]), 9)
        self.assertEqual(self.plan["declaration"]["source_size"], len(original))

    def test_deterministic_ids_and_unchanged_source(self):
        original = SAMPLE.read_bytes()
        self.assertEqual(self.plan, example.build_plan(SAMPLE))
        self.assertEqual(original, SAMPLE.read_bytes())
        identity = example.canonical_id("org", "run", "member", "source")
        self.assertEqual(uuid.UUID(identity).version, 5)
        for arguments in (("other", "run", "member", "source"), ("org", "other", "member", "source"),
                          ("org", "run", "comment", "source"), ("org", "run", "member", "other")):
            self.assertNotEqual(identity, example.canonical_id(*arguments))
        source = self.directory / "copy.json"
        source.write_bytes(original + b"\n")
        changed = example.build_plan(source)
        self.assertEqual(changed["batches"][0][1], original + b"\n")
        self.assertNotEqual(changed["declaration"]["plan_sha256"], self.plan["declaration"]["plan_sha256"])

    def test_invalid_sources_never_use_network(self):
        document = json.loads(SAMPLE.read_bytes())
        invalid = []
        for key, value in (("visibility", "private"), ("author_id", "absent"),
                           ("created_at", "2021-02-30T09:00:00Z"), ("roles", [])):
            changed = copy.deepcopy(document)
            changed["posts"][0][key] = value
            invalid.append(example.encoded(changed))
        changed = copy.deepcopy(document)
        changed["members"].append(changed["members"][0])
        invalid.append(example.encoded(changed))
        changed = copy.deepcopy(document)
        changed["posts"][0]["comments"][0]["created_at"] = "2020-01-01T00:00:00Z"
        invalid.append(example.encoded(changed))
        invalid.extend([b'{"members":[],"members":[],"posts":[]}', b"[]", b"{", b"\xff",
                        b" " * (example.MAX_SOURCE + 1), b'{"members":NaN,"posts":[]}'])
        source = self.directory / "bad.json"
        with patch.object(example, "request") as request:
            for data in invalid:
                with self.subTest(data=data[:50]):
                    source.write_bytes(data)
                    with contextlib.redirect_stderr(io.StringIO()):
                        self.assertEqual(example.main(["--source", str(source), "--apply", "--origin",
                                                       "http://localhost", "--organization", "example-community",
                                                       "--session-file", str(self.session)]), 1)
            request.assert_not_called()

    def test_offline_default_and_apply_required_arguments(self):
        with patch.object(example, "request") as request, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(example.main([]), 0)
            self.assertIn("Offline preview", output.getvalue())
            self.assertEqual(example.main(["--origin", "https://unused.example",
                                           "--session-file", "/missing"]), 0)
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                example.main(["--apply"])
            request.assert_not_called()

    def test_apply_order_and_exact_bodies(self):
        with self.server(self.responder) as (origin, requests), contextlib.redirect_stderr(io.StringIO()):
            self.assertTrue(example.apply_plan(self.plan, origin, self.session)["completed"])
        self.assertEqual(len(requests), 8)
        self.assertEqual(requests[0][:2], ("GET", "/api/v1/context"))
        self.assertNotIn("Authorization", requests[0][3])
        self.assertEqual(json.loads(requests[1][2]), self.plan["declaration"])
        for sequence, (kind, body) in enumerate(self.plan["batches"]):
            sent = requests[sequence + 2]
            self.assertTrue(sent[1].endswith(f"/batches/{sequence}/{kind}"))
            self.assertEqual(sent[2], body)
            self.assertEqual(sent[3]["Authorization"], "Bearer test-human-session")
        self.assertEqual(requests[-1][0], "POST")

    def test_organization_mismatch_never_writes(self):
        with self.server(lambda method, path: (200, {"organization_id": "other"})) as (origin, requests):
            with self.assertRaisesRegex(ValueError, "Organization mismatch"):
                example.apply_plan(self.plan, origin, self.session)
        self.assertEqual([request[0] for request in requests], ["GET"])

    def test_errors_and_redirects_never_retry_or_leak(self):
        for status in (401, 403, 302, 307, 500):
            def responder(method, path):
                return self.responder(method, path) if method == "GET" else (status, b"SECRET response body")
            with self.subTest(status=status), self.server(responder) as (origin, requests):
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(ValueError) as error:
                    example.apply_plan(self.plan, origin, self.session)
                self.assertNotIn("SECRET", str(error.exception))
                self.assertNotIn("test-human-session", str(error.exception))
                self.assertIn("PUT /api/v1/imports/fictional-messages-v1", str(error.exception))
            self.assertEqual(len(requests), 2)

    def test_completed_begin_short_circuits(self):
        def responder(method, path):
            return self.responder(method, path) if method == "GET" else (200, self.receipt(True))
        with self.server(responder) as (origin, requests), contextlib.redirect_stderr(io.StringIO()):
            example.apply_plan(self.plan, origin, self.session)
        self.assertEqual(len(requests), 2)

    def test_completion_receipt_is_strict(self):
        for key, value in (("completed", False), ("completed", 1), ("completed", "true"),
                           ("source_verified", 1), ("report_received", False), ("next_batch", 4),
                           ("chain_sha256", "wrong"), ("id", "other"), ("declaration", {})):
            receipt = self.receipt(True)
            receipt[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                example.check_receipt(receipt, self.plan, True)
        def responder(method, path):
            return (200, {"completed": False}) if path.endswith("/complete") else self.responder(method, path)
        with self.server(responder) as (origin, requests), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(ValueError):
                example.apply_plan(self.plan, origin, self.session)
        self.assertEqual(len(requests), 8)

    def test_origin_and_private_session_validation(self):
        for origin in ("https://example.com/path", "https://user:password@example.com", "https://example.com?",
                       "https://example.com#", "http://127.0.0.2", "http://localhost.evil", "http://[::2]",
                       "ftp://localhost", "https://example.com:bad", "https://example.com\n"):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                example.validate_origin(origin)
        for origin in ("https://example.com", "http://localhost:8080", "http://127.0.0.1", "http://[::1]:8080"):
            example.validate_origin(origin)
        self.assertEqual(example.read_session(self.session), "test-human-session")
        self.session.chmod(0o644)
        with self.assertRaises(ValueError):
            example.read_session(self.session)
        self.session.chmod(0o600)
        link = self.directory / "link"
        link.symlink_to(self.session)
        with self.assertRaises(OSError):
            example.read_session(link)

    def test_response_size_and_connection_failure(self):
        with self.server(lambda method, path: (200, b" " * (example.MAX_RESPONSE + 1))) as (origin, requests):
            with self.assertRaisesRegex(ValueError, "64 KiB"):
                example.apply_plan(self.plan, origin, self.session)
        with patch.object(example.http.client.HTTPConnection, "request", side_effect=OSError("SECRET")) as call:
            with self.assertRaisesRegex(ValueError, "stopped without retry"):
                example.request(example.validate_origin("http://localhost"), "GET", "/api/v1/context")
            self.assertEqual(call.call_count, 1)


if __name__ == "__main__":
    unittest.main()
