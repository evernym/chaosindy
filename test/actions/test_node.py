import os.path as path
import pytest

from chaosindy.actions.node import get_aliases


def test_get_aliases():
    genesis_file = path.join(path.dirname(__file__), 'pool_transactions_genesis')
    rtn = get_aliases(genesis_file)
    assert "Node1" in rtn