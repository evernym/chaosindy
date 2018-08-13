import argparse
import sys

from chaosindy.ledger_interaction import get_validator_state
from chaosindy.helpers import run
from logzero import logger


def get_current_validator_state(seed, genesis_file, pool_name=None,
                               wallet_name=None, timeout='60'):
    logger.debug("seed: %s genesis_file: %s pool_name: %s wallet_name: %s timeout: %s", seed, genesis_file, pool_name, wallet_name, timeout)
    return run(get_validator_state, seed=seed, pool_name=pool_name,
               wallet_name=wallet_name, genesis_file=genesis_file,
               timeout=int(timeout))


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
