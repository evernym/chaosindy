import abc
import os

import sys
from fabric import Connection


class RemoteExecutor(object):
    __metaclass__ = abc.ABCMeta

    def execute(self, host: str, action: str):
        rtn = self._execute_on_host(host, action)
        print(rtn)
        pass

    @abc.abstractmethod
    def _execute_on_host(self, host: str, action: str) -> str:
        raise NotImplementedError('users must define __str__ to use this base class')


class FabricExecutor(RemoteExecutor):
    pem_files = None

    def __init__(self, pem_dir=None):
        self.pem_files = FabricExecutor._find_pem_files(pem_dir)

    @staticmethod
    def _format_rtn(rtn):
        return str(rtn)

    @staticmethod
    def _find_pem_files(d):
        rtn = []

        if not os.path.exists(d):
            print("Unable to pem directory", file=sys.stderr)
            return None

        d = os.path.abspath(d)

        for root, dirs, files in os.walk(d):
            def is_pem_file(rel_path):
                path = os.path.join(root, rel_path)
                try:
                    with open(path, 'r') as f:
                        head = f.read()
                        if head.strip().startswith("-----BEGIN"):
                            if 'sao' in root:
                                return True
                except:
                    pass
                return False

            files = list(filter(is_pem_file, files))
            for file in files:
                rtn.append(os.path.join(root, file))

        return rtn

    def _execute_on_host(self, host: str, action: str) -> str:
        connect_kwargs = {}
        if self.pem_files:
            connect_kwargs['key_filename'] = self.pem_files

        if not connect_kwargs:
            connect_kwargs = None
        rtn = Connection(host, user='ubuntu', connect_kwargs=connect_kwargs).sudo(action)

        return FabricExecutor._format_rtn(rtn)

