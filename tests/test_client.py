import unittest
from unittest.mock import patch

from voice_input.client import build_stt


class _FakeSTTClient:
    def auth_headers(self, _backend):
        return {"Authorization": "Bearer test-token"}


class STTClientTests(unittest.TestCase):
    def test_profile_backend_headers_are_sent_with_auth(self):
        fake_client = _FakeSTTClient()
        with patch("voice_input.client.nl.stt", return_value=fake_client):
            client = build_stt(profile="gigaam", config={"profiles": {}})

        headers = client.auth_headers(
            {"headers": {"X-STT-Runtime": "stt-gigaam"}}
        )
        self.assertEqual(headers["Authorization"], "Bearer test-token")
        self.assertEqual(headers["X-STT-Runtime"], "stt-gigaam")


if __name__ == "__main__":
    unittest.main()
