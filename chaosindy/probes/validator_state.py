import json
import argparse
import sys

from chaosindy.common import *
from chaosindy.ledger_interaction import get_validator_state
from chaosindy.helpers import run
from logzero import logger


def get_current_validator_state(genesis_file,
                                seed=DEFAULT_CHAOS_SEED,
                                pool_name=DEFAULT_CHAOS_POOL,
                                wallet_name=DEFAULT_CHAOS_WALLET_NAME,
                                wallet_key=DEFAULT_CHAOS_WALLET_KEY,
                                timeout=DEFAULT_CHAOS_GET_VALIDATOR_INFO_TIMEOUT):
    logger.debug("seed: %s genesis_file: %s pool_name: %s wallet_name: %s timeout: %s", seed, genesis_file, pool_name, wallet_name, timeout)
    return run(get_validator_state, genesis_file=genesis_file, seed=seed,
               pool_name=pool_name, wallet_name=wallet_name,
               wallet_key=wallet_key, timeout=int(timeout))

def get_current_validator_list(genesis_file,
                               seed=DEFAULT_CHAOS_SEED,
                               pool_name=DEFAULT_CHAOS_POOL,
                               wallet_name=DEFAULT_CHAOS_WALLET_NAME,
                               wallet_key=DEFAULT_CHAOS_WALLET_KEY,
                               timeout=DEFAULT_CHAOS_GET_VALIDATOR_INFO_TIMEOUT):
    output_dir = get_chaos_temp_dir()
    validator_nodes = []

    # Get the current state of each node's "services" list
    validator_state = {}
    try:
        get_current_validator_state(genesis_file=genesis_file, seed=seed,
                                    pool_name=pool_name,
                                    wallet_name=wallet_name,
                                    wallet_key=wallet_key, timeout=timeout)
        with open("{}/validator-state".format(output_dir), 'r') as vs:
            validator_state = json.load(vs)

        # Traverse the list of aliases in the order defined by the genesis file
        # and add the alias to the validator_nodes list if and only if it is
        # currently participating as a validator node (it's services is set to
        # 'VALIDATOR').
        aliases = get_aliases(genesis_file)

        # Get the list of current validator nodes
        for alias in aliases:
            if alias in validator_state:
                if 'VALIDATOR' in validator_state[alias]['services']:
                    validator_nodes.append(alias)
    except Exception as e:
        logger.error("Failed to get current list of validator nodes.")
        logger.exception(e)
        pass

    return validator_nodes


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("seed",
        help="A Trust Anchor or Steward seed")
    parser.add_argument("genesis_file",
        help="A pool genesis transaction file")
    parser.add_argument("timeout",
        help="timeout")

    args = parser.parse_args()

    # Require at least two arguments
    if len(sys.argv) < 3:
        parser.print_help(sys.stderr)
        sys.exit(1)

    result = run(get_validator_state, seed=args.seed,
                 genesis_file=args.genesis_file, timeout=int(args.timeout))
