import unittest
import tempfile

from chaosindy.execute.execute import *

def noop_do_execute(*args, **kwargs):
    return Result(return_code=0, stdout='devin\n', stderr='')


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
        executor._do_execute_on_host = noop_do_execute
        with tempfile.NamedTemporaryFile(mode='w') as f:
            f.write("")
            f.flush()
            rtn = executor.execute('18.228.29.163',
                             'echo "devin"',
                             user='ubuntu',
                             identity_file=f.name)
            self.assertEqual(rtn.return_code, 0)

    def test_ssh_config(self):
        ssh_config = """Host 18.228.29.163
  User ubuntu
  IdentityFile /tmp/QA-Pool.pem"""
        with tempfile.NamedTemporaryFile(mode='w') as f:
            f.write(ssh_config)
            f.flush()

            executor = FabricExecutor(ssh_config_file=f.name)
            executor._do_execute_on_host = noop_do_execute
            rtn = executor.execute('18.228.29.163', 'echo "devin"')
            self.assertEqual(rtn.return_code, 0)

    @unittest.skip("Works against a real server that may not exists")
    def test_not_unit_test(self):
        ssh_config = """Host 18.228.29.163
  User ubuntu
  IdentityFile /home/devin/temp/B6/Evernym-QA-New/sa-east-1-sao-paulo/Evernym-QA-Pool.pem"""
        with tempfile.NamedTemporaryFile(mode='w') as f:
            f.write(ssh_config)
            f.flush()

            executor = FabricExecutor(ssh_config_file=f.name)
            executor.execute('18.228.29.163', 'echo "devin"', as_sudo=True)

    @unittest.skip("Works against a real server that may not exists")
    def test_not_unit_test2(self):
        ssh_config = """Host 18.228.29.163
  User ubuntu
  IdentityFile /home/devin/temp/B6/Evernym-QA-New/sa-east-1-sao-paulo/Evernym-QA-Pool.pem"""
        with tempfile.NamedTemporaryFile(mode='w') as f:
            f.write(ssh_config)
            f.flush()

            executor = FabricExecutor(ssh_config_file=f.name)
            executor.execute_all(['18.228.29.163', '18.228.29.163'], 'echo "devin"', as_sudo=False)
