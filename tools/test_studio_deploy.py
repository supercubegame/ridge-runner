#!/usr/bin/env python3
"""Fast, zero-network gates for archive safety, URL hygiene and serving isolation."""
import io
import stat
import unittest
import zipfile
from studio_remote import safe_members, validate_url, digest, SERVER

def sample(extra=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("index.html", "test")
        z.writestr("index.wasm", b"\0asm")
        z.writestr("index.pck", "game")
        if extra:
            z.writestr(*extra)
    buffer.seek(0)
    return zipfile.ZipFile(buffer)

class Gate(unittest.TestCase):
    def test_valid_archive(self):
        with sample() as z:
            self.assertEqual(len(safe_members(z)), 3)
    def test_traversal(self):
        with sample(("../outside", "bad")) as z, self.assertRaises(ValueError):
            safe_members(z)
    def test_absolute(self):
        with sample(("/tmp/outside", "bad")) as z, self.assertRaises(ValueError):
            safe_members(z)
    def test_hidden(self):
        with sample((".ssh/key", "sentinel-private-key")) as z, self.assertRaises(ValueError):
            safe_members(z)
    def test_symlink(self):
        entry = zipfile.ZipInfo("escape")
        entry.create_system = 3
        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
        with sample((entry, "/etc/passwd")) as z, self.assertRaises(ValueError):
            safe_members(z)
    def test_duplicates(self):
        with sample(("index.html", "second")) as z, self.assertRaises(ValueError):
            safe_members(z)
    def test_missing_game(self):
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w") as z:
            z.writestr("index.html", "not-a-game")
        b.seek(0)
        with zipfile.ZipFile(b) as z, self.assertRaises(ValueError):
            safe_members(z)
    def test_safe_url(self):
        self.assertEqual(validate_url("https://example.lightning.ai/"), "https://example.lightning.ai")
    def test_token_url(self):
        with self.assertRaises(ValueError):
            validate_url("https://example.lightning.ai/?token=sentinel-secret")
    def test_impostor_url(self):
        with self.assertRaises(ValueError):
            validate_url("https://lightning.ai.evil.example")
    def test_http_url(self):
        with self.assertRaises(ValueError):
            validate_url("http://example.lightning.ai")
    def test_credentials_url(self):
        with self.assertRaises(ValueError):
            validate_url("https://user:sentinel-secret@example.lightning.ai")
    def test_digest_known_vector(self):
        self.assertEqual(digest(b"abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
    def test_server_compiles(self):
        compile(SERVER, "static-server", "exec")

if __name__ == "__main__":
    unittest.main()
