import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agent.pumpfun.rpc import verify_mint


MINT = "So11111111111111111111111111111111111111112"


class FakeResponse:
    def __init__(self, status=200, body=None, json_error=None):
        self.status = status
        self.body = body
        self.json_error = json_error

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def json(self, content_type=None):
        if self.json_error:
            raise self.json_error
        return self.body


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def post(self, *args, **kwargs):
        if self.error:
            raise self.error
        return self.response


class FakeAiohttp:
    def __init__(self, response=None, error=None):
        self.ClientTimeout = lambda **kwargs: None
        self.ClientSession = lambda **kwargs: FakeSession(self.response, self.error)
        self.response = response
        self.error = error


class VerifyMintRpcFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_endpoint_returns_unknown_without_network(self):
        with patch.dict("os.environ", {}, clear=True):
            result = await verify_mint(MINT, rpc_url="")
        self.assertEqual(result.status, "UNKNOWN")
        self.assertEqual(result.reason, "solana_rpc_not_configured")

    async def test_non_https_endpoint_returns_unknown(self):
        result = await verify_mint(MINT, rpc_url="http://localhost:8899")
        self.assertEqual(result.status, "UNKNOWN")
        self.assertEqual(result.reason, "solana_rpc_endpoint_must_use_https")

    async def test_http_error_returns_unknown(self):
        fake = FakeAiohttp(response=FakeResponse(status=429, body={}))
        with patch.dict(sys.modules, {"aiohttp": fake}):
            result = await verify_mint(MINT, rpc_url="https://rpc.example")
        self.assertEqual(result.status, "UNKNOWN")
        self.assertEqual(result.reason, "solana_rpc_http_status_429")

    async def test_rpc_error_returns_unknown(self):
        fake = FakeAiohttp(response=FakeResponse(body={"jsonrpc": "2.0", "error": {"code": -32000}}))
        with patch.dict(sys.modules, {"aiohttp": fake}):
            result = await verify_mint(MINT, rpc_url="https://rpc.example")
        self.assertEqual(result.status, "UNKNOWN")
        self.assertEqual(result.reason, "solana_rpc_error_or_invalid_response")

    async def test_malformed_json_returns_unknown(self):
        fake = FakeAiohttp(response=FakeResponse(json_error=ValueError("bad json")))
        with patch.dict(sys.modules, {"aiohttp": fake}):
            result = await verify_mint(MINT, rpc_url="https://rpc.example")
        self.assertEqual(result.status, "UNKNOWN")
        self.assertEqual(result.reason, "solana_rpc_request_failed")

    async def test_network_exception_returns_unknown_without_leaking_details(self):
        fake = FakeAiohttp(error=RuntimeError("private endpoint detail"))
        with patch.dict(sys.modules, {"aiohttp": fake}):
            result = await verify_mint(MINT, rpc_url="https://rpc.example")
        self.assertEqual(result.status, "UNKNOWN")
        self.assertEqual(result.reason, "solana_rpc_request_failed")
        self.assertNotIn("private endpoint detail", result.reason)

    async def test_null_account_value_returns_unknown(self):
        fake = FakeAiohttp(response=FakeResponse(body={"jsonrpc": "2.0", "result": {"value": None}}))
        with patch.dict(sys.modules, {"aiohttp": fake}):
            result = await verify_mint(MINT, rpc_url="https://rpc.example")
        self.assertEqual(result.status, "UNKNOWN")
        self.assertEqual(result.reason, "mint_account_missing")


if __name__ == "__main__":
    unittest.main()
