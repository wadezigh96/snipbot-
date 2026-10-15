"""Real buy/sell for four.meme + Flap."""
from __future__ import annotations

from typing import Any

from web3 import Web3
from eth_account import Account

from agent.config import Settings
from agent.contracts import (
    TOKEN_MANAGER2,
    TOKEN_MANAGER2_ABI,
    TOKEN_MANAGER_HELPER3,
    HELPER3_ABI,
    FLAP_PORTAL,
    FLAP_PORTAL_ABI,
    ERC20_ABI,
)
from agent.utils.logger import setup_logger

log = setup_logger("trader")


class Trader:
    def __init__(self, settings: Settings, w3: Web3, account: Account):
        self.s = settings
        self.w3 = w3
        self.account = account
        self.address = account.address

    async def buy(self, token: dict[str, Any], size_bnb: float) -> str | None:
        platform = token.get("platform", "")
        if platform == "four.meme":
            return await self._buy_fourmeme(token, size_bnb)
        if platform == "flap":
            return await self._buy_flap(token, size_bnb)
        log.warning("Unknown platform %s", platform)
        return None

    async def sell(self, token: dict[str, Any], amount_tokens: int) -> str | None:
        platform = token.get("platform", "")
        if platform == "four.meme":
            return await self._sell_fourmeme(token, amount_tokens)
        if platform == "flap":
            return await self._sell_flap(token, amount_tokens)
        return None

    # ---------- four.meme ----------
    async def _buy_fourmeme(self, token: dict, size_bnb: float) -> str | None:
        token_addr = Web3.to_checksum_address(token["address"])
        funds = self.w3.to_wei(size_bnb, "ether")

        helper = self.w3.eth.contract(
            address=Web3.to_checksum_address(TOKEN_MANAGER_HELPER3),
            abi=HELPER3_ABI,
        )
        try:
            quote = helper.functions.tryBuy(token_addr, 0, funds).call()
            # estimatedAmount = quote[2]
            min_amount = int(quote[2] * (10_000 - self.s.slippage_bps) / 10_000)
            amount_msg_value = quote[5] or funds
        except Exception as e:
            log.warning("tryBuy failed %s: %s — fallback min_amount=0", token.get("symbol"), e)
            min_amount = 0
            amount_msg_value = funds

        mgr = self.w3.eth.contract(
            address=Web3.to_checksum_address(TOKEN_MANAGER2),
            abi=TOKEN_MANAGER2_ABI,
        )
        tx = mgr.functions.buyTokenAMAP(token_addr, funds, min_amount).build_transaction({
            "from": self.address,
            "value": amount_msg_value,
            "gas": 450_000,
            "gasPrice": self.w3.to_wei(self.s.gas_price_gwei, "gwei"),
            "nonce": self.w3.eth.get_transaction_count(self.address),
            "chainId": self.s.chain_id,
        })
        return self._send(tx)

    async def _sell_fourmeme(self, token: dict, amount: int) -> str | None:
        token_addr = Web3.to_checksum_address(token["address"])
        # approve first
        erc20 = self.w3.eth.contract(address=token_addr, abi=ERC20_ABI)
        approve_tx = erc20.functions.approve(
            Web3.to_checksum_address(TOKEN_MANAGER2), amount
        ).build_transaction({
            "from": self.address,
            "gas": 80_000,
            "gasPrice": self.w3.to_wei(self.s.gas_price_gwei, "gwei"),
            "nonce": self.w3.eth.get_transaction_count(self.address),
            "chainId": self.s.chain_id,
        })
        self._send(approve_tx)

        mgr = self.w3.eth.contract(
            address=Web3.to_checksum_address(TOKEN_MANAGER2),
            abi=TOKEN_MANAGER2_ABI,
        )
        tx = mgr.functions.sellToken(token_addr, amount).build_transaction({
            "from": self.address,
            "gas": 350_000,
            "gasPrice": self.w3.to_wei(self.s.gas_price_gwei, "gwei"),
            "nonce": self.w3.eth.get_transaction_count(self.address),
            "chainId": self.s.chain_id,
        })
        return self._send(tx)

    # ---------- Flap ----------
    async def _buy_flap(self, token: dict, size_bnb: float) -> str | None:
        token_addr = Web3.to_checksum_address(token["address"])
        amount_in = self.w3.to_wei(size_bnb, "ether")

        portal = self.w3.eth.contract(
            address=Web3.to_checksum_address(FLAP_PORTAL),
            abi=FLAP_PORTAL_ABI,
        )
        # quote
        try:
            quoted = portal.functions.quoteExactInput({
                "inputToken": "0x0000000000000000000000000000000000000000",
                "outputToken": token_addr,
                "inputAmount": amount_in,
            }).call()
            min_out = int(quoted * (10_000 - self.s.slippage_bps) / 10_000)
        except Exception as e:
            log.warning("Flap quote fail: %s", e)
            min_out = 0

        tx = portal.functions.swapExactInput({
            "inputToken": "0x0000000000000000000000000000000000000000",
            "outputToken": token_addr,
            "inputAmount": amount_in,
            "minOutputAmount": min_out,
            "permitData": b"",
        }).build_transaction({
            "from": self.address,
            "value": amount_in,
            "gas": 500_000,
            "gasPrice": self.w3.to_wei(self.s.gas_price_gwei, "gwei"),
            "nonce": self.w3.eth.get_transaction_count(self.address),
            "chainId": self.s.chain_id,
        })
        return self._send(tx)

    async def _sell_flap(self, token: dict, amount: int) -> str | None:
        token_addr = Web3.to_checksum_address(token["address"])
        # approve portal
        erc20 = self.w3.eth.contract(address=token_addr, abi=ERC20_ABI)
        approve_tx = erc20.functions.approve(
            Web3.to_checksum_address(FLAP_PORTAL), amount
        ).build_transaction({
            "from": self.address,
            "gas": 80_000,
            "gasPrice": self.w3.to_wei(self.s.gas_price_gwei, "gwei"),
            "nonce": self.w3.eth.get_transaction_count(self.address),
            "chainId": self.s.chain_id,
        })
        self._send(approve_tx)

        portal = self.w3.eth.contract(
            address=Web3.to_checksum_address(FLAP_PORTAL),
            abi=FLAP_PORTAL_ABI,
        )
        try:
            quoted = portal.functions.quoteExactInput({
                "inputToken": token_addr,
                "outputToken": "0x0000000000000000000000000000000000000000",
                "inputAmount": amount,
            }).call()
            min_out = int(quoted * (10_000 - self.s.slippage_bps) / 10_000)
        except Exception:
            min_out = 0

        tx = portal.functions.swapExactInput({
            "inputToken": token_addr,
            "outputToken": "0x0000000000000000000000000000000000000000",
            "inputAmount": amount,
            "minOutputAmount": min_out,
            "permitData": b"",
        }).build_transaction({
            "from": self.address,
            "value": 0,
            "gas": 450_000,
            "gasPrice": self.w3.to_wei(self.s.gas_price_gwei, "gwei"),
            "nonce": self.w3.eth.get_transaction_count(self.address),
            "chainId": self.s.chain_id,
        })
        return self._send(tx)

    def _send(self, tx: dict) -> str | None:
        try:
            signed = self.account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            h = tx_hash.hex()
            log.info("TX sent: %s", h)
            return h
        except Exception as e:
            log.error("Send failed: %s", e)
            return None
