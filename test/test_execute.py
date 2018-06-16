import tempfile
import pytest

from chaosindy.execute.execute import *
from test import patch


def noop_do_execute(*args, **kwargs):
    args[0].put(Result(return_code=0, stdout='devin\n', stderr=''))


def test_verify_identity_file():

    with pytest.raises(ValueError):
        FabricExecutor._is_readable_file(None, "test")

    with pytest.raises(ValueError):
        FabricExecutor._is_readable_file(['/tmp/test/'], "test")

    with pytest.raises(ValueError):
        FabricExecutor._is_readable_file(1, "test")

    with pytest.raises(OSError):
        FabricExecutor._is_readable_file(str(tempfile.gettempdir()), "test")

    with tempfile.NamedTemporaryFile() as f:
        os.chmod(f.name, 0o000)
        with pytest.raises(OSError):
            FabricExecutor._is_readable_file(f.name, "test")

    with tempfile.NamedTemporaryFile() as f:
        FabricExecutor._is_readable_file(f.name, "test")


def test_simple_fabric_test():
    executor = FabricExecutor()
    with tempfile.NamedTemporaryFile(mode='w') as f:
        f.write("")
        f.flush()
        with patch(FabricExecutor, '_multiprocess_execute_on_host', noop_do_execute):
            rtn = executor.execute('Node1',
                                   'echo "devin"',
                                   user='ubuntu',
                                   identity_file=f.name)
            assert rtn.return_code == 0


def test_ssh_config():
    ssh_config = """Host Node1
User ubuntu
IdentityFile /tmp/QA-Pool.pem"""
    with tempfile.NamedTemporaryFile(mode='w') as f:
        f.write(ssh_config)
        f.flush()

        executor = FabricExecutor(ssh_config_file=f.name)
        with patch(FabricExecutor, '_multiprocess_execute_on_host', noop_do_execute):
            rtn = executor.execute('Node1', 'echo "devin"')
            assert rtn.return_code == 0
