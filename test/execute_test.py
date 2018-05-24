import unittest

from chaosindy.execute.execute import *


class ExecuteTests(unittest.TestCase):
    def test_noop(self):
        pass

    def test_simple_fabric_test(self):
        executor = FabricExecutor(pem_dir='/home/devin/temp/B6/Evernym-QA-New/')
        executor.execute('18.228.29.163', 'echo "devin"')