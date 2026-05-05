"""
The Control Panel for the Finalto Risk Management dashboard simulator.

This is where all the parameters are defined so you can configure the system to operate the way you need.
"""

# --- Instruments ---
# Forex pairs and one commodity (XAU/USD = Gold)
INSTRUMENTS = {
    "EURUSD": 1.0850,   # starting mid price
    "GBPUSD": 1.2700,
    "USDJPY": 149.50,
    "EURGBP": 0.8550,
    "XAUUSD": 2330.00,
}

# --- Clients ---
# Mock broker clients sending orders to Finalto
CLIENTS = [
    "ViltrumFinance",
    "CadmusFX",
    "ImmortalMarkets",
    "JosephTrading",
    "Covenant Capital",
]

# --- Spread configuration ---
# Spread as a fraction of the mid price
# 0.0001 = 1 pip spread on most pairs
SPREAD = {
    "EURUSD": 0.0001,
    "GBPUSD": 0.0001,
    "USDJPY": 0.01,
    "EURGBP": 0.0001,
    "XAUUSD": 0.50,
}

# --- Trade size configuration ---
# Random trade sizes in units
MIN_TRADE_SIZE = 10_000
MAX_TRADE_SIZE = 100_000
TRADE_SIZE_STEP = 10_000   # sizes will be multiples of this

# --- Timing configuration ---
PRICE_UPDATE_INTERVAL = 1.0      # seconds between price updates
TRADE_INTERVAL_MIN = 5.0         # minimum seconds between client trades
TRADE_INTERVAL_MAX = 15.0        # maximum seconds between client trades
DASHBOARD_UPDATE_INTERVAL = 1000 # milliseconds between dashboard refreshes

# --- Random walk configuration ---
# Controls how much prices move each tick
# Larger value = more volatile prices
VOLATILITY = {
    "EURUSD": 0.0003,
    "GBPUSD": 0.0004,
    "USDJPY": 0.05,
    "EURGBP": 0.0002,
    "XAUUSD": 1.00,
}

# --- Server configuration ---
WEBSOCKET_HOST = "localhost"
WEBSOCKET_PORT = 8765
DASHBOARD_PORT = 8050

# --- History configuration ---
# How many data points to keep for charts
MAX_HISTORY_POINTS = 300  # 5 minutes at 1 update per second