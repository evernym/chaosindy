from enum import Enum
class ValidatorInfoSource(Enum):
    NODE = 1
    CLI = 2

DEFAULT_CHAOS_LOAD_COMMAND="python3 /home/ubuntu/indy-node/scripts/performance/perf_processes.py -c 20 -n 10 -k nym -g /home/ubuntu/pool_transactions_genesis"
DEFAULT_CHAOS_LOAD_TIMEOUT=60
DEFAULT_CHAOS_DID="V4SGRU86Z58d6TV7PBUe6f"
DEFAULT_CHAOS_SEED="000000000000000000000000Trustee1"
DEFAULT_CHAOS_WALLET_NAME="chaosindy"
DEFAULT_CHAOS_WALLET_KEY="chaosindy"
DEFAULT_CHAOS_POOL="chaosindy"
DEFAULT_CHAOS_GET_VALIDATOR_INFO_TIMEOUT=10
DEFAULT_CHAOS_SSH_CONFIG_FILE="~/.ssh/config"
DEFAULT_VALIDATOR_INFO_SOURCE=ValidatorInfoSource.NODE
