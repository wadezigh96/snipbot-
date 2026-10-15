"""
ERC-8004 Agent Registration for BNB Chain (Set and Earn)

Usage:
    python -m agent.register

Gasless on BSC Testnet & Mainnet via MegaFuel paymaster.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from agent.config import get_settings

STATE_FILE = Path(__file__).resolve().parent.parent / "agent_state.json"


def main() -> None:
    settings = get_settings()

    try:
        from bnbagent import ERC8004Agent, EVMWalletProvider, AgentEndpoint
    except ImportError:
        print("ERROR: bnbagent belum terinstall.")
        print("Jalankan: pip install bnbagent")
        sys.exit(1)

    # Wallet
    if not settings.wallet_password and not settings.private_key:
        print("ERROR: Set WALLET_PASSWORD atau PRIVATE_KEY di .env")
        sys.exit(1)

    print(f"Network : {settings.network}")
    print(f"Agent   : {settings.agent_name}")
    print()

    wallet = EVMWalletProvider(
        password=settings.wallet_password,
        private_key=settings.private_key,
    )

    sdk = ERC8004Agent(
        network=settings.network,
        wallet_provider=wallet,
        debug=True,
    )

    print(f"Wallet  : {sdk.wallet_address}")
    print(f"Registry: {sdk.contract_address}")
    print()

    # Build agent URI / card
    agent_uri = sdk.generate_agent_uri(
        name=settings.agent_name,
        description=settings.agent_description,
        endpoints=[
            AgentEndpoint(
                name="web",
                endpoint=settings.agent_endpoint,
                version="0.1.0",
            ),
            # Bisa ditambah A2A / MCP nanti
            # AgentEndpoint(name="A2A", endpoint="https://...", version="0.3.0"),
        ],
    )

    print("Agent card generated.")
    print()

    # Register
    print("Registering agent on-chain (gasless via MegaFuel)...")
    result = sdk.register_agent(
        agent_uri=agent_uri,
        metadata=[
            {"key": "category", "value": "trading"},
            {"key": "subcategory", "value": "meme-sniper"},
            {"key": "platforms", "value": "four.meme,flap"},
            {"key": "chain", "value": "bnb"},
            {"key": "version", "value": "0.1.0"},
        ],
    )

    agent_id = result.get("agentId")
    tx_hash = result.get("transactionHash")

    print()
    print("=" * 50)
    print(f"✓ Agent registered!")
    print(f"  Agent ID : {agent_id}")
    print(f"  TX       : {tx_hash}")
    if settings.is_mainnet:
        print(f"  Explorer : https://bscscan.com/tx/{tx_hash}")
    else:
        print(f"  Explorer : https://testnet.bscscan.com/tx/{tx_hash}")
    print("=" * 50)

    # Save state
    state = {
        "agent_id": agent_id,
        "agent_uri": agent_uri,
        "wallet": sdk.wallet_address,
        "network": settings.network,
        "tx_hash": tx_hash,
        "registry": sdk.contract_address,
    }
    STATE_FILE.write_text(json.dumps(state, indent=2))
    print(f"\nState saved → {STATE_FILE}")
    print("\nNext steps:")
    print("1. Pastikan agent endpoint hidup & responsive")
    print("2. List agent di salah satu marketplace shortlist Set and Earn")
    print("3. Jalankan: python -m agent.main")


if __name__ == "__main__":
    main()
