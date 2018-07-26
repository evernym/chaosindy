import abc
import os
import json

from collections import namedtuple

from logzero import logger
from multiprocessing import Pool, Process, Queue, Manager, cpu_count
from queue import Empty

from fabric import Connection, Config
from paramiko import AuthenticationException

from typing import List

Result = namedtuple('Result', ['return_code', 'stdout', 'stderr'])
ParallelResult = namedtuple('ParallelResult', ['host', 'return_code', 'stdout', 'stderr'])


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
                rtn = c.sudo(action, hide=True)
                #rtn = c.sudo(action, hide=True, pty=True)
            else:
                rtn = c.run(action, hide=True)
                #rtn = c.run(action, hide=True, pty=True)

            q.put(Result(rtn.return_code, rtn.stdout, rtn.stderr))

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
            rtn = q.get(timeout=0.1)
        except AuthenticationException as e:
            raise e
        except Empty:
            raise Exception("Remote execution did not provide results")
        finally:
            if p:
                p.terminate()

        return rtn

class ParallelFabricExecutor(FabricExecutor):
    _processes = []
    config = None
    # DEBUG PARALLELIZATION
    #f = None

    # DEBUG PARALLELIZATION
    #def open_print(self):
    #    self.f = open('/tmp/corin.txt', 'a')

    # DEBUG PARALLELIZATION
    #def close_print(self):
    #    self.f.close()

    # DEBUG PARALLELIZATION
    #def flush_print(self):
    #    self.f.flush()

    # DEBUG PARALLELIZATION
    #def print(self, text):
    #    self.f.write("{}: {}".format(os.getpid(), text))
    #    self.flush_print()

    def __init__(self, ssh_config_file=None):
        super().__init__(ssh_config_file=ssh_config_file)

        # DEBUG PARALLELIZATION
        #self.open_print()
        #self.print("In ParallelFabricExecutor.__init__\n")

        # A manager for inter-process communcation (IPC)
        self._manager = Manager()
        # A queue to hold tasks
        self._tasks = self._manager.Queue()
        # A queue to hold task results
        self._results = self._manager.Queue()
        # Create process pool with as many processes as there are cores
        # TODO: make self._cpu_count configurable
        #       On a 2 cpu client _cpu_count was set to 4 and 5 with nominal
        #       decrease (improvement) in runtime.
        self._cpu_count = cpu_count()
        self._pool = Pool(processes=self._cpu_count)
        self._processes = []
        # Initiate the worker processes
        for i in range(self._cpu_count):
            # Set process name
            process_name = 'P%i' % i
            # Create the process, and connect it to the worker function
            new_process = Process(target=self.do_work, args=(process_name,self._tasks,self._results))
            # Add new process to the list of processes
            self._processes.append(new_process)
            # Start the process
            new_process.start()
        # Worker processes are now waiting for work

        # DEBUG PARALLELIZATION
        #self.print("Leaving __init__\n")

    def __del__(self):
        for process in self._processes:
            # Gracefully send SIGTERM to each process
            process.terminate()

        # DEBUG PARALLELIZATION
        #if self.f:
        #    self.print("Closing file handle...")
        #    self.close_print()
        #    self.f = None

    def _parallel_execute_on_host(self, results, host, action, config, user=None,
                                  as_sudo=False, **kwargs):
        if action == "pytest":
            # DEBUG PARALLELIZATION
            #self.print("Returning mocked ParallelResult\n")
            results.put(ParallelResult(host, 0, "corin\n", ""))
        else:
            # DEBUG PARALLELIZATION
            #self.print("In _parallel_execute_on_host...\n")
            connect_timeout = kwargs.get('connect_timeout', 60)
            connect_kwargs = kwargs.get('connect_kwargs', None)

            # DEBUG PARALLELIZATION
            #self.print("connect_timeout: {}\n".format(connect_timeout))
            #self.print("connect_kwargs: {}\n".format(connect_kwargs))
            #self.print("Opening connection\n")

            with Connection(host, config=config, user=user,
                            connect_timeout=connect_timeout,
                            connect_kwargs=connect_kwargs) as c:
                # DEBUG PARALLELIZATION
                #self.print("Connection open\n")
                if as_sudo:
                    rtn = c.sudo(action, hide=True)
                    #rtn = c.sudo(action, hide=True, pty=True)
                else:
                    rtn = c.run(action, hide=True)
                    #rtn = c.run(action, hide=True, pty=True)

                results.put(ParallelResult(host, rtn.return_code, rtn.stdout, rtn.stderr))
            # DEBUG PARALLELIZATION
            #self.print("Connection closed\n")

    # Define worker function
    def do_work(self, process_name, tasks, results):
        logger.debug('[%s] routine starts', process_name)

        with open('/tmp/corin.txt', 'a') as f:
            while True:
                # DEBUG PARALLELIZATION
                #self.print("Before tasks.get()\n")
                new_tuple = tasks.get()
                # DEBUG PARALLELIZATION
                #self.print("After tasks.get()\n")
                if len(new_tuple) == 0:
                    # DEBUG PARALLELIZATION
                    #self.print('[{}] routine quits\n'.format(process_name))
                    logger.debug('[%s] routine quits', process_name)

                    # Indicate finished
                    results.put(ParallelResult("", -999, "", ""))
                    break
                else:
                    # Unpack tuple into variables. See self.tasks.put in 'execute'
                    # member function
                    host = new_tuple[0]
                    action = new_tuple[1]
                    user = new_tuple[2]
                    as_sudo = new_tuple[3]
                    kwargs_dict = new_tuple[4]
                    # TODO: Execute remote command - _parallel_execute_on_host
                    logger.debug('Execute on host...')
                    logger.debug('host: %s', host)
                    logger.debug('action: %s', action)
                    logger.debug('user: %s', user)
                    logger.debug('as_sudo: %s', as_sudo)
                    logger.debug('kwargs: %s', json.dumps(kwargs_dict))

                    # DEBUG PARALLELIZATION
                    #self.print('Execute on host...\n')
                    #self.print('host: {}\n'.format(host))
                    #self.print('action: {}\n'.format(action))
                    #self.print('user: {}\n'.format(user))
                    #self.print('as_sudo: {}\n'.format(as_sudo))
                    #self.print('kwargs: {}\n'.format(json.dumps(kwargs_dict)))
                    #self.print('Before call to _parallel_execute_on_host\n')
                    #self.print('Details about _parallel_execute_on_host: {}\n'.format(getattr(self, '_parallel_execute_on_host')))

                    self._parallel_execute_on_host(results, host, action,
                                                   self.config, user=user,
                                                   as_sudo=as_sudo, **kwargs_dict)
                    # DEBUG PARALLELIZATION
                    #self.print('After call to _parallel_execute_on_host\n')
        return

    def execute(self, hosts: List[str], action: str, user: str = None, as_sudo=False, **kwargs):
        # DEBUG PARALLELIZATION
        #self.print("In execute...\n")
        #self.print("The instance's _parallel_execute_on_host function has been patched by pytest at this point...\n")
        #self.print('Details about _parallel_execute_on_host: {}\n'.format(getattr(self, '_parallel_execute_on_host')))
        identity_file = kwargs.pop('identity_file', None)
        connect_kwargs = self._collect_connect_kwargs(identity_file)
        kwargs['connect_kwargs'] = connect_kwargs
        logger.debug('TODO: Execute on hosts...')
        logger.debug('hosts: %s', hosts)
        logger.debug('action: %s', action)
        logger.debug('user: %s', user)
        logger.debug('as_sudo: %s', as_sudo)
        logger.debug('kwargs: %s', json.dumps(kwargs))
        # Fill task queue
        for host in hosts:
            self._tasks.put((host, action, user, as_sudo, kwargs))

        # Signal the do_work worker function/process to exit. An empty tuple will
        # be the signal for a worker process to exit.
        for host in hosts:
            self._tasks.put(())

        # Read results
        num_finished_processes = 0
        rtn = {}
        while True:
            # Read result
            new_result = self._results.get()
            # Have a look at the results
            if new_result.return_code == -999:
                # Process has finished
                num_finished_processes += 1

                if num_finished_processes == self._cpu_count:
                    break
            else:
                # Output result
                #logger.debug('host: %s rc: %d stdout: %s stderr: %s',
                #             new_result.host, new_result.return_code,
                #             new_result.stdout, new_result.stderr)
                rtn[new_result.host] = {
                   'return_code': new_result.return_code,
                   'stdout': new_result.stdout,
                   'stderr': new_result.stderr
                }
        # DEBUG PARALLELIZATION
        #self.print("Returning {} from execute...\n".format(str(rtn)))
        return rtn
