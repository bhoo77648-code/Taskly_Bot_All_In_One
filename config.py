import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip()
ADMIN_ID = int(os.getenv('ADMIN_ID', '0') or 0)

# Payment address requested by the owner.
PAYMENT_WALLET_ADDRESS = os.getenv(
    'PAYMENT_WALLET_ADDRESS',
    '0xBE280149a80b1c7300d7Cd3a2F813f6aFD0845aB'
).strip()
PAYMENT_ASSET = 'USDT'
PAYMENT_NETWORK = 'BEP20'
# BSC USDT representation used for BEP20 transfers (18 decimals).
USDT_CONTRACT = os.getenv(
    'USDT_CONTRACT',
    '0x55d398326f99059fF775485246999027B3197955'
).strip()
USDT_DECIMALS = 18
BSC_RPC_URL = os.getenv('BSC_RPC_URL', 'https://bsc-dataseed.binance.org').strip()
PAYMENT_CONFIRMATIONS = int(os.getenv('PAYMENT_CONFIRMATIONS', '3') or 3)

DB_NAME = os.getenv('DB_NAME', 'taskly.sqlite3').strip()
MAX_CHANNELS_PER_USER = 10
MIN_WITHDRAW = 2.0
REFERRAL_RATE = 0.10
NETWORKS = ['YouTube', 'Instagram', 'TikTok', 'Telegram', 'Facebook', 'X']
DEFAULT_SUBSCRIBER_PRICE = 0.02
MIN_SUBSCRIBER_PRICE = 0.005
MAX_SUBSCRIBER_PRICE = 1.00
MIN_SUBSCRIBER_QTY = 10
MAX_SUBSCRIBER_QTY = 100000
