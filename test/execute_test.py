import unittest
import tempfile

from chaosindy.execute.execute import *
from test import patch


def noop_do_execute(*args, **kwargs):
    args[0].put(Result(return_code=0, stdout='devin\n', stderr=''))


class ExecuteTests(unittest.TestCase):
    def test_noop(self):
        pass

    def test_verify_identity_file(self):
        with self.assertRaises(ValueError):
            FabricExecutor._is_readable_file(None, "test")

        with self.assertRaises(ValueError):
            FabricExecutor._is_readable_file(['/tmp/test/'], "test")

        with self.assertRaises(ValueError):
            FabricExecutor._is_readable_file(1, "test")

        with self.assertRaises(OSError):
            FabricExecutor._is_readable_file(str(tempfile.gettempdir()), "test")

        with tempfile.NamedTemporaryFile() as f:
            os.chmod(f.name, 0o000)
            with self.assertRaises(OSError):
                FabricExecutor._is_readable_file(f.name, "test")

        with tempfile.NamedTemporaryFile() as f:
            FabricExecutor._is_readable_file(f.name, "test")

    def test_simple_fabric_test(self):
        executor = FabricExecutor()
        with tempfile.NamedTemporaryFile(mode='w') as f:
            f.write("")
            f.flush()
            with patch(FabricExecutor, '_multiprocess_execute_on_host', noop_do_execute):
                rtn = executor.execute('Node1',
                                       'echo "devin"',
                                       user='ubuntu',
                                       identity_file=f.name)
                self.assertEqual(rtn.return_code, 0)

    def test_ssh_config(self):
        ssh_config = """Host Node1
  User ubuntu
  IdentityFile /tmp/QA-Pool.pem"""
        with tempfile.NamedTemporaryFile(mode='w') as f:
            f.write(ssh_config)
            f.flush()

            executor = FabricExecutor(ssh_config_file=f.name)
            with patch(FabricExecutor, '_multiprocess_execute_on_host', noop_do_execute):
                rtn = executor.execute('Node1', 'echo "devin"')
                self.assertEqual(rtn.return_code, 0)

    # @unittest.skip("Works against a real server that may not exists")
    def test_not_unit_test(self):
        ssh_config = """Host Node1
    User ubuntu
    Hostname 18.228.29.163
    IdentityFile /home/devin/temp/B6/Evernym-QA-New/sa-east-1-sao-paulo/Evernym-QA-Pool.pem
Host Node2
    User ubuntu
    Hostname 52.209.71.171
    IdentityFile /home/devin/temp/B6/Evernym-QA-New/eu-west-1-ireland/Evernym-QA-Pool.pem
Host Node3
    User ubuntu
    Hostname 35.178.118.86
    IdentityFile /home/devin/temp/B6/Evernym-QA-New/eu-west-2-london/Evernym-QA-Pool.pem
Host Node4
    User ubuntu
    Hostname 52.78.149.162
    IdentityFile /home/devin/temp/B6/Evernym-QA-New/ap-northeast-2-seoul/Evernym-QA-Pool.pem
Host Node5
    User ubuntu
    Hostname 52.13.205.56
    IdentityFile /home/devin/temp/B6/Evernym-QA-New/us-west-2-oregon/Evernym-QA-Pool.pem
Host Node6
    User ubuntu
    Hostname 54.241.204.174
    IdentityFile /home/devin/temp/B6/Evernym-QA-New/us-west-1-california/Evernym-QA-Pool.pem
Host Node7
    User ubuntu
    Hostname 18.188.154.146
    IdentityFile /home/devin/temp/B6/Evernym-QA-New/us-east-2-ohio/Evernym-QA-Pool.pem
Host Node8
    User ubuntu
    Hostname 35.177.252.115
    IdentityFile /home/devin/temp/B6/Evernym-QA-New/eu-west-2-london/Evernym-QA-Pool.pem
Host Node9
    User ubuntu
    Hostname 52.58.108.102
    IdentityFile /home/devin/temp/B6/Evernym-QA-New/eu-central-1-frankfurt/Evernym-QA-Pool.pem
Host Node10
    User ubuntu
    Hostname 13.125.23.229
    IdentityFile /home/devin/temp/B6/Evernym-QA-New/ap-northeast-2-seoul/Evernym-QA-Pool.pem"""
        with tempfile.NamedTemporaryFile(mode='w') as f:
            f.write(ssh_config)
            f.flush()

            executor = FabricExecutor(ssh_config_file=f.name)
            executor.execute('Node1', 'echo "devin"', as_sudo=True)
            executor.execute('Node2', 'echo "devin"', as_sudo=True)
            executor.execute('Node3', 'echo "devin"', as_sudo=True)
            executor.execute('Node4', 'echo "devin"', as_sudo=True)
            executor.execute('Node5', 'echo "devin"', as_sudo=True)
            executor.execute('Node6', 'echo "devin"', as_sudo=True)
            executor.execute('Node7', 'echo "devin"', as_sudo=True)
            executor.execute('Node8', 'echo "devin"', as_sudo=True)
            executor.execute('Node9', 'echo "devin"', as_sudo=True)
            executor.execute('Node10', 'echo "devin"', as_sudo=True)
            executor.execute('Node1', 'echo "devin"', as_sudo=True)
            executor.execute('Node1', 'echo "devin"', as_sudo=True)
            executor.execute('Node1', 'echo "devin"', as_sudo=True)
            rtn = executor.execute('Node1', 'echo "devin"', as_sudo=True)
            self.assertEqual(rtn.return_code, 0)
