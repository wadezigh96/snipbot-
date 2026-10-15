from __future__ import annotations

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Wallet
    private_key: str | None = None
    wallet_password: str | None = None

    # Network
    network: str = "bsc-testnet"  # bsc-testnet | bsc
    rpc_url: str | None = None

    # Agent identity
    agent_name: str = "SnipBot-BNB"
    agent_description: str = (
        "Fully autonomous meme coin sniper & portfolio manager on BNB Chain. "
        "Targets new listings on four.meme and Flap with anti-rug filters "
        "(LP burn, holder concentration, volume)."
    )
    agent_endpoint: str = "https://example.com/status"

    # Risk
    max_trade_pct: float = 0.04          # 3-5%
    max_total_exposure: float = 0.25
    min_volume_usd: float = 8000
    max_volume_usd: float = 15000
    min_liquidity_usd: float = 3000

    # Trading
    slippage_bps: int = 300
    gas_price_gwei: float = 3.0

    @property
    def is_mainnet(self) -> bool:
        return self.network in ("bsc", "bsc-mainnet", "mainnet")

    @property
    def chain_id(self) -> int:
        return 56 if self.is_mainnet else 97


def get_settings() -> Settings:
    return Settings()
