import abc
import os

from collections import namedtuple

from multiprocessing import Process, Queue
from queue import Empty

from fabric import Connection, Config
from paramiko import AuthenticationException

Result = namedtuple('Result', ['return_code', 'stdout', 'stderr'])


class RemoteExecutor(object):
    __metaclass__ = abc.ABCMeta

    def execute(self, host: str, action: str, user: str = None, as_sudo=False, **kwargs):
        rtn = self._execute_on_host(host, action, user=user, as_sudo=as_sudo, **kwargs)
        return rtn

    @abc.abstractmethod
    def _execute_on_host(self, host: str, action: str, user: str = None, as_sudo=False) -> str:
        raise NotImplementedError('users must define _execute_on_host to use this base class')


class FabricExecutor(RemoteExecutor):
    @staticmethod
    def _multiprocess_execute_on_host(q, host, action, config, user=None, as_sudo=False, connect_kwargs=None):
        with Connection(host, config=config, user=user, connect_kwargs=connect_kwargs) as c:
            if as_sudo:
                rtn = c.sudo(action)
            else:
                rtn = c.run(action)

            q.put(Result(rtn.return_code, rtn.stdout, rtn.stderr))
            # import time
            # time.sleep(12)

    config = None

    def __init__(self, ssh_config_file=None):
        self.config = FabricExecutor._create_config(ssh_config_file=ssh_config_file)
        pass

    # @staticmethod
    # def _format_rtn(rtn):
    #     return str(rtn)

    @staticmethod
    def _create_config(ssh_config_file=None):
        if ssh_config_file:
            FabricExecutor._is_readable_file(ssh_config_file, 'ssh_config')
        return Config(runtime_ssh_path=ssh_config_file)

    @staticmethod
    def _is_readable_file(path, file_kind):
        if not isinstance(path, str):
            raise ValueError("path to file must be a string")

        if os.access(path, os.R_OK):
            if os.path.isfile(path):
                return
            else:
                raise OSError("Path is not to a file -- '%s'" % str(path))
        else:
            raise OSError("Unable to access the file (not readable) -- %s -- '%s'" % (file_kind, path))

    @staticmethod
    def _collect_connect_kwargs(identity_file):
        connect_kwargs = {}

        if identity_file:
            FabricExecutor._is_readable_file(identity_file, 'identity_file')
            connect_kwargs['key_filename'] = identity_file

        if not connect_kwargs:
            connect_kwargs = None

        return connect_kwargs

    def _execute_on_host(self, host: str, action: str, user: str = None, as_sudo=False, identity_file=None,
                         timeout=10) -> str:
        connect_kwargs = self._collect_connect_kwargs(identity_file)

        p = None
        q = Queue()
        try:
            # Running execution in a subprocess - Did this to avoid errors in paramiko clean up.
            p = Process(target=FabricExecutor._multiprocess_execute_on_host,
                        args=(q, host, action, self.config),
                        kwargs={'user': user, "as_sudo": as_sudo, "connect_kwargs": connect_kwargs})
            p.start()
            p.join(timeout=timeout)
            if p.is_alive():
                raise Exception("Remote execution has exceeded timeout")
            rtn = q.get(timeout=0)
        except AuthenticationException as e:
            raise e
        except Empty:
            raise Exception("Remote execution did not provide results")
        finally:
            if p:
                p.terminate()

        return rtn
