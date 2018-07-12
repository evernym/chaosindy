import logging
import tempfile
import pytest

from chaosindy.execute.execute import *
from test import patch


def noop_do_execute(*args, **kwargs):
    args[0].put(Result(return_code=0, stdout='devin\n', stderr=''))

def parallel_noop_do_execute(*args, **kwargs):
    with open('/tmp/corin.txt', 'a') as f:
        f.write("In parallel_noop_do_execute...")
        f.write("Writing ParallelResul to results queue...")
        args[0].put(ParallelResult(args[1], return_code=0, stdout='corin\n', stderr=''))
        f.write("Wrote ParallelResul to results queue...")


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

def test_simple_parallel_fabric_test(caplog):
    caplog.set_level(logging.DEBUG)
    executor = ParallelFabricExecutor()
    with tempfile.NamedTemporaryFile(mode='w') as f:
        f.write("")
        f.flush()
        # TODO: mock _parallel_execute_on_host to return a ParallelResult
        #       (4 tuple) for each host.
        #
        # I have tried to patch _parallel_execute_on_host with
        # parallel_noop_do_execute with _parallel_execute_on_host decordated with
        # and without @staticmethod. No change in behavior. All Processes spawned
        # call the ParallelFabricExecutor.__init__ and use an un-patched
        # instance. Additional mocking must be done to get this right. Until then
        # _parallel_execute_on_host will return a static ParallelResult if the
        # 'action' is "pytest".
        #
        # Perhaps mocking Process or Pool in the multiprocess package will be
        # required to get this working properly?
        #
        #with patch(ParallelFabricExecutor, '_parallel_execute_on_host',
        #           parallel_noop_do_execute):
        #    rtn = executor.execute(['Node1', 'Node2'],
        #                           'echo "corin"',
        #                           user='ubuntu',
        #                           identity_file=f.name)
        #    for key in rtn.keys():
        #        assert rtn[key]['return_code'] == 0
        #        assert rtn[key]['stdout'] == 'corin\n'
        rtn = executor.execute(['Node1', 'Node2'],
                                'pytest',
                                user='ubuntu',
                                identity_file=f.name)
        for key in rtn.keys():
            assert rtn[key]['return_code'] == 0
            assert rtn[key]['stdout'] == 'corin\n'


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
