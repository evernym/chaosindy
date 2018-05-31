import abc
import os

from collections import namedtuple

from fabric import Connection, Config, SerialGroup, Result
from paramiko import AuthenticationException

Result = namedtuple('Result', ['return_code', 'stdout', 'stderr'])


class RemoteExecutor(object):
    __metaclass__ = abc.ABCMeta

    def execute(self, host: str, action: str, user: str=None, as_sudo=False, **kwargs):
        rtn = self._execute_on_host(host, action, user=user, as_sudo=as_sudo, **kwargs)
        return rtn

    def execute_all(self, hosts: list, action: str, user: str=None, as_sudo=False, **kwargs):
        rtn = self._execute_on_all_hosts(hosts, action, user=user, as_sudo=as_sudo, **kwargs)
        return rtn

    @abc.abstractmethod
    def _execute_on_host(self, host: str, action: str, user: str=None, as_sudo=False) -> str:
        raise NotImplementedError('users must define _execute_on_host to use this base class')

    @abc.abstractmethod
    def _execute_on_all_hosts(self, host: str, action: str, user: str=None, as_sudo=False) -> str:
        raise NotImplementedError('users must define _execute_on_all_hosts to use this base class')


class FabricExecutor(RemoteExecutor):

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

    def _collect_connect_kwargs(self, identity_file):
        connect_kwargs = {}

        if identity_file:
            FabricExecutor._is_readable_file(identity_file, 'identity_file')
            connect_kwargs['key_filename'] = identity_file

        if not connect_kwargs:
            connect_kwargs = None

        return connect_kwargs

    def _execute_on_host(self, host: str, action: str, user: str=None, as_sudo=False, identity_file=None) -> str:
        connect_kwargs = self._collect_connect_kwargs(identity_file)

        try:
            rtn = self._do_execute_on_host(host, action, user=user, as_sudo=as_sudo, connect_kwargs= connect_kwargs)
        except AuthenticationException as e:
            raise e

        return rtn

    def _execute_on_all_hosts(self, hosts: list, action: str, user: str = None, as_sudo=False, identity_file=None) -> str:
        connect_kwargs = self._collect_connect_kwargs(identity_file)

        try:
            rtn = self._do_execute_on_group(hosts, action, user=user, as_sudo=as_sudo, connect_kwargs= connect_kwargs)
        except AuthenticationException as e:
            raise e

        return rtn

    def _do_execute_on_host(self, host, action, user=None, as_sudo=False, connect_kwargs=None):
        c = Connection(host, config=self.config, user=user, connect_kwargs=connect_kwargs)
        if as_sudo:
            rtn = c.sudo(action)
        else:
            rtn = c.run(action)
        return Result(rtn.return_code, rtn.stdout, rtn.stderr)

    def _do_execute_on_group(self, hosts: list, action, user=None, as_sudo=False, connect_kwargs=None):
        conn = []
        for host in hosts:
            conn.append(Connection(host, config=self.config, user=user, connect_kwargs=connect_kwargs))
        g = SerialGroup.from_connections(conn)
        if as_sudo:
            raise NotImplementedError("Not implemented for group commands (blame fabric) -- try adding sudo to command")
            # results = g.sudo(action)
        else:
            results = g.run(action)

        rtn = {}
        for connection, result in results.items():
            rtn[connection] = Result(result.return_code, result.stdout, result.stderr)

        return rtn

