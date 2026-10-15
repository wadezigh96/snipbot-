"""Contract addresses & minimal ABIs for BNB mainnet."""

# four.meme
TOKEN_MANAGER2 = "0x5c952063c7fc8610FFDB798152D69F0B9550762b"
TOKEN_MANAGER_HELPER3 = "0xF251F83e40a78868FcfA3FA4599Dad6494E46034"

# Flap
FLAP_PORTAL = "0xe2cE6ab80874Fa9Fa2aAE65D277Dd6B8e65C9De0"

# Common
WBNB = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
USDT = "0x55d398326f99059fF775485246999027B3197955"
PCS_ROUTER = "0x10ED43C718714eb63d5aA57B78B54704E256024E"

# Minimal ABIs
TOKEN_MANAGER2_ABI = [
    {
        "name": "buyTokenAMAP",
        "type": "function",
        "stateMutability": "payable",
        "inputs": [
            {"name": "token", "type": "address"},
            {"name": "funds", "type": "uint256"},
            {"name": "minAmount", "type": "uint256"},
        ],
        "outputs": [],
    },
    {
        "name": "sellToken",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "token", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [],
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": False, "name": "creator", "type": "address"},
            {"indexed": False, "name": "token", "type": "address"},
            {"indexed": False, "name": "requestId", "type": "uint256"},
            {"indexed": False, "name": "name", "type": "string"},
            {"indexed": False, "name": "symbol", "type": "string"},
            {"indexed": False, "name": "totalSupply", "type": "uint256"},
            {"indexed": False, "name": "launchTime", "type": "uint256"},
            {"indexed": False, "name": "launchFee", "type": "uint256"},
        ],
        "name": "TokenCreate",
        "type": "event",
    },
]

HELPER3_ABI = [
    {
        "name": "getTokenInfo",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "token", "type": "address"}],
        "outputs": [
            {"name": "version", "type": "uint256"},
            {"name": "tokenManager", "type": "address"},
            {"name": "quote", "type": "address"},
            {"name": "lastPrice", "type": "uint256"},
            {"name": "tradingFeeRate", "type": "uint256"},
            {"name": "minTradingFee", "type": "uint256"},
            {"name": "launchTime", "type": "uint256"},
            {"name": "offers", "type": "uint256"},
            {"name": "maxOffers", "type": "uint256"},
            {"name": "funds", "type": "uint256"},
            {"name": "maxFunds", "type": "uint256"},
            {"name": "liquidityAdded", "type": "bool"},
        ],
    },
    {
        "name": "tryBuy",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "token", "type": "address"},
            {"name": "amount", "type": "uint256"},
            {"name": "funds", "type": "uint256"},
        ],
        "outputs": [
            {"name": "tokenManager", "type": "address"},
            {"name": "quote", "type": "address"},
            {"name": "estimatedAmount", "type": "uint256"},
            {"name": "estimatedCost", "type": "uint256"},
            {"name": "estimatedFee", "type": "uint256"},
            {"name": "amountMsgValue", "type": "uint256"},
            {"name": "amountApproval", "type": "uint256"},
            {"name": "amountFunds", "type": "uint256"},
        ],
    },
]

FLAP_PORTAL_ABI = [
    {
        "name": "swapExactInput",
        "type": "function",
        "stateMutability": "payable",
        "inputs": [
            {
                "name": "params",
                "type": "tuple",
                "components": [
                    {"name": "inputToken", "type": "address"},
                    {"name": "outputToken", "type": "address"},
                    {"name": "inputAmount", "type": "uint256"},
                    {"name": "minOutputAmount", "type": "uint256"},
                    {"name": "permitData", "type": "bytes"},
                ],
            }
        ],
        "outputs": [{"name": "outputAmount", "type": "uint256"}],
    },
    {
        "name": "quoteExactInput",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {
                "name": "params",
                "type": "tuple",
                "components": [
                    {"name": "inputToken", "type": "address"},
                    {"name": "outputToken", "type": "address"},
                    {"name": "inputAmount", "type": "uint256"},
                ],
            }
        ],
        "outputs": [{"name": "outputAmount", "type": "uint256"}],
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": False, "name": "ts", "type": "uint256"},
            {"indexed": True, "name": "creator", "type": "address"},
            {"indexed": False, "name": "nonce", "type": "uint256"},
            {"indexed": False, "name": "token", "type": "address"},
            {"indexed": False, "name": "name", "type": "string"},
            {"indexed": False, "name": "symbol", "type": "string"},
            {"indexed": False, "name": "meta", "type": "string"},
        ],
        "name": "TokenCreated",
        "type": "event",
    },
]

ERC20_ABI = [
    {
        "name": "balanceOf",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "approve",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "name": "decimals",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint8"}],
    },
    {
        "name": "symbol",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "string"}],
    },
]
