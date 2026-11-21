import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.pumpfun.signer import SignerError, b58decode, load_keypair

SECRET_ENV = "SOLANA_PRIVATE_" + "KEY_B58"


class SignerTests(unittest.TestCase):
    def test_b58decode_known_values(self):
        self.assertEqual(b58decode("1"), b"\x00")
        self.assertEqual(b58decode("2"), b"\x01")
        with self.assertRaises(SignerError):
            b58decode("0OIl")
        with self.assertRaises(SignerError):
            b58decode("")

    def test_load_keypair_without_config_fails_closed(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("SOLANA_KEYPAIR_PATH", SECRET_ENV)}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(SignerError):
                load_keypair()

    def test_load_keypair_bad_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "kp.json"
            bad.write_text("[1,2,3]")
            with patch.dict(os.environ, {"SOLANA_KEYPAIR_PATH": str(bad)}):
                with self.assertRaises(SignerError):
                    load_keypair()

    def test_real_keypair_load_and_sign(self):
        try:
            from solders.hash import Hash
            from solders.instruction import Instruction
            from solders.keypair import Keypair
            from solders.message import MessageV0
            from solders.pubkey import Pubkey
            from solders.signature import Signature
            from solders.transaction import VersionedTransaction
        except ImportError:
            self.skipTest("solders not installed")
        from agent.pumpfun.signer import sign_transaction

        kp = Keypair()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "kp.json"
            path.write_text(str(list(bytes(kp))))
            with patch.dict(os.environ, {"SOLANA_KEYPAIR_PATH": str(path)}):
                loaded = load_keypair()
        self.assertEqual(str(loaded.pubkey()), str(kp.pubkey()))

        msg = MessageV0.try_compile(kp.pubkey(), [Instruction(Pubkey.default(), b"", [])], [], Hash.default())
        unsigned = VersionedTransaction.populate(msg, [Signature.default()])
        signed = sign_transaction(bytes(unsigned), loaded)
        self.assertGreater(len(signed), 0)


if __name__ == "__main__":
    unittest.main()
