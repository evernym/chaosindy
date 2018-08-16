import json
import shutil
import tempfile
from enum import Enum
from logzero import logger
from os import makedirs
from os.path import expanduser
from psutil import Process, NoSuchProcess

def get_chaos_temp_dir():
    # Get current process info
    myp = Process()
    subprocess_pid = myp.pid
    chaos_pid = None
    # Walk all the way up the process tree
    while(1):
        #  Break when we find the 'chaos' process
        if myp.name() == 'chaos':
            logger.debug("Found 'chaos' process")
            chaos_pid = myp.pid
            break
        try:
            myp = Process(myp.ppid())
            logger.debug("myp.name=%s", myp.name())
        except NoSuchProcess as e:
            logger.info("Did not find chaos pid before traversing all the way to the top of the process tree! Defaulting to %s", subprocess_pid)
            logger.exception(e)
            chaos_pid = subprocess_pid
            break

    logger.debug("subprocess pid: %s chaos pid: %s", subprocess_pid, chaos_pid)
    tempdir_path = "{}/chaosindy.{}".format(tempfile.gettempdir(), chaos_pid)
    tempdir = makedirs(tempdir_path, exist_ok=True)
    logger.debug("tempdir: %s", tempdir_path)
    return tempdir_path

def remove_chaos_temp_dir(cleanup=True):
    temp_dir = get_chaos_temp_dir()
    if cleanup:
        logger.debug("Recursively deleting %s", temp_dir)
        try:
            shutil.rmtree(temp_dir)
        except Exception as e:
            logger.error("Failed to recursively delete the contents of %s",
                         temp_dir)
            logger.exception(e)
            return False
    else:
        logger.info("Skip removal of %s.", temp_dir)
    return True

def get_info_by_node_name(genesis_file, node, path=None):
    aliases = []
    # Open genesis_file and load all aliases into an array
    with open(expanduser(genesis_file), 'r') as genesisfile:
        for line in genesisfile:
            line_json = json.loads(line)
            alias = line_json['txn']['data']['data']['alias']
            if (alias == node):
                if not path:
                    return line_json['txn']['data']['data']
                else:
                    filters = path.split(".")
                    return_json = line_json
                    for f in filters:
                        return_json = return_json[f]
                    return return_json
    return None


def get_aliases(genesis_file):
    aliases = []
    # Open genesis_file and load all aliases into an array
    with open(expanduser(genesis_file), 'r') as genesisfile:
        for line in genesisfile:
            line_json = json.loads(line)
            alias = line_json['txn']['data']['data']['alias']
            aliases.append(alias)
    return aliases

class ValidatorInfoSource(Enum):
    NODE = 1 # validator-info script executed on each node
    CLI = 2 # `ledger get-validator-info` executed via indy-cli
    SDK = 3 # Not Yet Implemented - Use Indy SDK to get validator info

    @classmethod
    def has_value(cls, value):
        return any(value == item.value for item in cls)

# Actions and Probes may be written to select items/nodes on which to act/probe
# The following enum allows actions and probes to be written to operate on
# a set of items/nodes in a certain number of ways.
# Example: If there is an ordered set of nodes ['Node1', 'Node2', 'Node3'] and
#          two of them should be stopped (indy-node service stopped or node
#          port blocked), a FORWARD strategy would stop Node1, followed by Node2.
#          A REVERSE strategy would stop Node3 followed by Node2. The RANDOM
#          strategy will pick a node at random, stop it, remove it from
#          consideration on the next selection and then repeat the process one
#          more time.
class SelectionStrategy(Enum):
    FORWARD = 1
    REVERSE = 2
    RANDOM = 3

    @classmethod
    def has_value(cls, value):
        return any(value == item.value for item in cls)

class StopStrategy(Enum):
    #"stop" indy-node service
    SERVICE = 1
    # "stop/block" inbound messages from clients and other nodes
    PORT = 2
    # "stop" participating in consensus
    DEMOTE = 3
    # "stop/kill" indy-node service
    KILL = 4

    @classmethod
    def has_value(cls, value):
        return any(value == item.value for item in cls)

# Please keep defaults in lexically acending order by name
DEFAULT_CHAOS_DID="V4SGRU86Z58d6TV7PBUe6f"
DEFAULT_CHAOS_GET_VALIDATOR_INFO_TIMEOUT=20
DEFAULT_CHAOS_LEDGER_TRANSACTION_TIMEOUT=20
DEFAULT_CHAOS_LOAD_COMMAND="python3 /home/ubuntu/indy-node/scripts/performance/perf_processes.py -c 20 -n 10 -k nym -g /home/ubuntu/pool_transactions_genesis"
DEFAULT_CHAOS_LOAD_TIMEOUT=60
DEFAULT_CHAOS_NODE_SERVICES="VALIDATOR"
DEFAULT_CHAOS_PAUSE=60
DEFAULT_CHAOS_POOL="chaosindy"
DEFAULT_CHAOS_TRUSTEE_SEED="000000000000000000000000Trustee1"
DEFAULT_CHAOS_STEWARD_SEED="000000000000000000000000Steward1"
DEFAULT_CHAOS_SEED=DEFAULT_CHAOS_TRUSTEE_SEED
DEFAULT_CHAOS_SSH_CONFIG_FILE="~/.ssh/config"
DEFAULT_CHAOS_VALIDATOR_INFO_SOURCE=ValidatorInfoSource.NODE.value
DEFAULT_CHAOS_WALLET_NAME="chaosindy"
DEFAULT_CHAOS_MY_WALLET_NAME=DEFAULT_CHAOS_WALLET_NAME
DEFAULT_CHAOS_THEIR_WALLET_NAME="their_"+DEFAULT_CHAOS_WALLET_NAME
DEFAULT_CHAOS_WALLET_KEY="chaosindy"
DEFAULT_CHAOS_GENESIS_FILE="/home/ubuntu/pool_transactions_genesis"
