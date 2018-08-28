import argparse
import sys

from chaosindy.ledger_interaction import write_nym_and_check
from chaosindy.helpers import run
from logzero import logger

from typing import Union


def write_nym(seed: str, genesis_file: str, pool_name: str = None,
              my_wallet_name: str = None, their_wallet_name: str = None,
              timeout: Union[str,int] = '60') -> None:
    """
    Write a NYM to the ledger.

    Write a NYM to the ledger and confirm/check that it was successfull by
    reading the NYM from the ledger. Not idempotent.

    :param seed: 32 byte string used to generate did, verkey pair. The seed must
        be the seed for a Trustee, Steward, or Trust Anchor.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SEED)
    :type seed: str
    :param pool_name: Pool name
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_POOL)
    :type pool_name: str
    :param my_wallet_name: My wallet name
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_MY_WALLET_NAM)
    :type my_wallet_name: str
    :param my_wallet_key: My wallet key
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_WALLET_KEY)
    :type my_wallet_key: str
    :param their_wallet_name: Their wallet name
        Optional. (Default: chaosindy.common.DEFAULT_THEIR_WALLET_NAME)
    :type their_wallet_name: str
    :param their_wallet_key: Their wallet key
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_WALLET_KEY)
    :type their_wallet_key: str
    :param genesis_file: Relative or absolute path to the pool's genesis
        transaction file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_GENESIS_FILE)
    :type genesis_file: str
    :param cleanup: Delete wallets and pool configuration?
        Optional. (Default: True)
    :type cleanup: bool
    :return: None
    """
    logger.debug("seed: %s genesis_file: %s pool_name: %s my_wallet_name: %s " \
                 "their_wallet_name: %s timeout: %s", seed, genesis_file,
                 pool_name, my_wallet_name, their_wallet_name, timeout)
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
