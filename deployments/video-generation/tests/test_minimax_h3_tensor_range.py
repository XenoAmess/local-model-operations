"""Protect small tensor downloads from accidental full-checkpoint transfers or corrupt writes."""

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("h3_download", ROOT / "tools/download_minimax_h3.py")
DOWNLOAD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DOWNLOAD)


class Response:
    def __init__(self, data, start, status=206):
        self.status_code = status
        self.headers = {"Content-Range": f"bytes {start}-{start + len(data) - 1}/1000000"}
        self.raw = io.BytesIO(data)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TensorRangeTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = bytes(1025 * 8 * 4)
        self.header = json.dumps({"adaln_t_table": {
            "dtype": "F32", "shape": [1025, 8], "data_offsets": [0, len(self.data)]
        }}).encode()
        self.entry = {"repository": "example/model", "file": "checkpoint.safetensors", "revision": "pinned",
                      "tensor": "adaln_t_table", "destination": "sharp/lms_curve.bin",
                      "sha256": hashlib.sha256(self.data).hexdigest()}

    def responses(self):
        return [Response(struct.pack("<Q", len(self.header)), 0), Response(self.header, 8),
                Response(self.data, 8 + len(self.header))]

    def test_verified_ranges_create_only_the_small_tensor(self):
        with patch("requests.get", side_effect=self.responses()) as get:
            DOWNLOAD.fetch_tensor_range(self.entry, self.root)
        self.assertEqual((self.root / self.entry["destination"]).read_bytes(), self.data)
        self.assertEqual(get.call_count, 3)
        self.assertTrue(all(call.kwargs["stream"] for call in get.call_args_list))

    def test_full_checkpoint_response_is_rejected_without_reading(self):
        response = Response(b"must not read this full checkpoint", 0, status=200)
        with patch("requests.get", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "refusing full checkpoint"):
                DOWNLOAD.fetch_tensor_range(self.entry, self.root)
        self.assertEqual(response.raw.tell(), 0)
        self.assertFalse((self.root / self.entry["destination"]).exists())

    def test_wrong_range_offset_is_rejected(self):
        with patch("requests.get", return_value=Response(b"12345678", 99)):
            with self.assertRaisesRegex(RuntimeError, "Unexpected byte range"):
                DOWNLOAD.fetch_tensor_range(self.entry, self.root)

    def test_corrupt_tensor_is_not_committed(self):
        self.entry["sha256"] = "f" * 64
        with patch("requests.get", side_effect=self.responses()):
            with self.assertRaisesRegex(RuntimeError, "SHA-256 mismatch"):
                DOWNLOAD.fetch_tensor_range(self.entry, self.root)
        self.assertFalse((self.root / self.entry["destination"]).exists())

    def test_existing_verified_tensor_uses_no_network(self):
        target = self.root / self.entry["destination"]
        target.parent.mkdir(parents=True)
        target.write_bytes(self.data)
        with patch("requests.get") as get:
            DOWNLOAD.fetch_tensor_range(self.entry, self.root)
        get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
