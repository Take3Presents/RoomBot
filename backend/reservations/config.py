import os
from importlib import resources as impresources
import reservations

VERSION = impresources.read_text(reservations, "version")

def env_config(val, default=''):
    key = f"ROOMBAHT_{val.upper()}"
    env_val = os.environ.get(key, '')
    if len(env_val) == 0:
        return default

    return env_val

DEV = env_config('dev', 'false').lower() == 'true'
DEV_MAIL = env_config('dev_mail')
SEND_MAIL = env_config('send_mail', 'false').lower() == 'true'
LOGLEVEL = env_config('loglevel', 'info').upper()

URL_HOST = env_config('host', 'localhost')
URL_PORT = env_config('url_port', '3000')
URL_SCHEMA = env_config('url_schema', 'http')

JWT_KEY = env_config('jwt_key')

SEND_ONBOARDING = env_config('send_onboarding', 'false').lower() == 'true'
ONBOARDING_BATCH = int(env_config('onboarding_batch', '5'))

TEMP_DIR = env_config('tmp', '/tmp')

IGNORE_TRANSACTIONS = env_config('ignore_transactions').split(',')
SWAPS_ENABLED = env_config('swaps_enabled', 'true').lower() == 'true'
GUEST_HOTELS = env_config('guest_hotels', 'Ballys,Nugget').split(',')

FEATURES = env_config('features', '').split(',')

ROOM_COOLDOWN = int(env_config('room_cooldown', '30'))
SWAP_CODE_LIFE = int(env_config('swap_code_life', '3600'))

SP_API_KEY = env_config('sp_api_key')
