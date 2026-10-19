import base64
import unittest

from agent.pumpfun.rpc import TOKEN_2022_PROGRAM, TOKEN_PROGRAM, parse_mint_account


MINT = "So11111111111111111111111111111111111111112"


def mint_bytes(*, mint_authority=0, freeze_authority=0, initialized=1, decimals=6, size=82):
    data = bytearray(size)
    data[0:4] = int(mint_authority).to_bytes(4, "little")
    data[44] = decimals
    data[45] = initialized
    data[46:50] = int(freeze_authority).to_bytes(4, "little")
    return bytes(data)


class SolanaMintCheckTests(unittest.TestCase):
    def account(self, data, owner=TOKEN_PROGRAM):
        return {"owner": owner, "data": [base64.b64encode(data).decode(), "base64"]}

    def test_parses_initialized_mint_without_authorities(self):
        check = parse_mint_account(MINT, self.account(mint_bytes()))
        self.assertEqual(check.status, "VERIFIED")
        self.assertEqual(check.decimals, 6)
        self.assertFalse(check.mint_authority_present)
        self.assertFalse(check.freeze_authority_present)

    def test_flags_mint_and_freeze_authorities(self):
        check = parse_mint_account(
            MINT, self.account(mint_bytes(mint_authority=1, freeze_authority=1))
        )
        self.assertEqual(check.status, "VERIFIED")
        self.assertTrue(check.mint_authority_present)
        self.assertTrue(check.freeze_authority_present)

    def test_token_2022_base_layout_without_extensions_can_be_parsed(self):
        check = parse_mint_account(
            MINT, self.account(mint_bytes(), owner=TOKEN_2022_PROGRAM)
        )
        self.assertEqual(check.status, "VERIFIED")

    def test_token_2022_extensions_remain_unknown_until_parsed(self):
        check = parse_mint_account(
            MINT, self.account(mint_bytes(size=90), owner=TOKEN_2022_PROGRAM)
        )
        self.assertEqual(check.status, "UNKNOWN")
        self.assertEqual(check.reason, "token_2022_extensions_not_parsed")
        self.assertIsNone(check.mint_authority_present)
        self.assertIsNone(check.freeze_authority_present)

    def test_rejects_uninitialized_mint(self):
        check = parse_mint_account(MINT, self.account(mint_bytes(initialized=0)))
        self.assertEqual(check.status, "REJECT")
        self.assertEqual(check.reason, "mint_not_initialized")

    def test_rejects_unsupported_owner(self):
        check = parse_mint_account(
            MINT, self.account(mint_bytes(), owner="11111111111111111111111111111111")
        )
        self.assertEqual(check.status, "REJECT")

    def test_rejects_short_data(self):
        check = parse_mint_account(MINT, self.account(b"short"))
        self.assertEqual(check.status, "REJECT")

    def test_rejects_invalid_address(self):
        self.assertEqual(parse_mint_account("bad", {}).status, "UNKNOWN")

    def test_missing_mint_account_remains_unknown(self):
        check = parse_mint_account(MINT, None)
        self.assertEqual(check.status, "UNKNOWN")
        self.assertEqual(check.reason, "mint_account_missing")
        self.assertIsNone(check.mint_authority_present)
        self.assertIsNone(check.freeze_authority_present)

    def test_rejects_invalid_authority_option_flags(self):
        data = bytearray(mint_bytes())
        data[0:4] = (2).to_bytes(4, "little")
        check = parse_mint_account(MINT, self.account(bytes(data)))
        self.assertEqual(check.status, "REJECT")
        self.assertEqual(check.reason, "mint_authority_option_invalid")


if __name__ == "__main__":
    unittest.main()
