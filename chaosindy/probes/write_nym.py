import argparse
import sys

from chaosindy.ledger_interaction import write_nym_and_check
from chaosindy.helpers import run
from logzero import logger


def write_nym(seed, genesis_file, pool_name=None, my_wallet_name=None,
              their_wallet_name=None, timeout='60'):
    logger.debug("seed: %s genesis_file: %s pool_name: %s my_wallet_name: %s their_wallet_name: %s timeout: %s", seed, genesis_file, pool_name, my_wallet_name, their_wallet_name, timeout)
    return run(write_nym_and_check, seed=seed, pool_name=pool_name,
               my_wallet_name=my_wallet_name,
               their_wallet_name=their_wallet_name, genesis_file=genesis_file,
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

    run(write_nym_and_check, seed=args.seed, genesis_file=args.genesis_file,
        timeout=int(args.timeout))
