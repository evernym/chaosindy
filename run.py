#!/usr/bin/env python3

import sys
import os
import argparse
import logging
import datetime
import dateutil
import time
import tempfile
import subprocess
import atexit
import shutil
import json
import socket

# TODO: add the following to the install/config README:
#
# Setup aws configuration
# Create ~/.aws/credentials
#[default]
#aws_access_key_id = YOUR_ACCESS_KEY
#aws_secret_access_key = YOUR_SECRET_KEY
# Create ~/.aws/config
#[default]
#region=us-west-2
# https://boto3.amazonaws.com/v1/documentation/api/latest/guide/quickstart.html
import boto3

from io import StringIO

logger = logging.getLogger(__name__)

# Command-line Argument Parsing
def str2bool(v):
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError(
            'Boolean value (yes, no, true, false, y, n, 1, or 0) expected.')


LOG_LEVEL_HELP = """Logging level.
                      [LOG-LEVEL]: notset, debug, info, warning, error, critical
                      Default: info"""
levels = {
    'notset': logging.NOTSET,
    'debug': logging.DEBUG,
    'info': logging.INFO,
    'warning': logging.WARNING,
    'error': logging.ERROR,
    'critical': logging.CRITICAL
}


def log_level(v):
    if v.lower() in levels.keys():
        return levels[v.lower()]
    else:
        raise argparse.ArgumentTypeError(
            'Expected one of the following: {}.'.format(
                 ', '.join(levels.keys())))

def experiment_dict(v):
    common_msg = "Invalid experiment dictionary."
    experiments = {}
    try:
        experiments = json.loads(v)
    except Exception as e:
        raise argparse.ArgumentTypeError('{} Reason: {}'.format(common_msg,
                                                                e))

    de = default_experiments()
    invalid_experiments = []
    for experiment in experiments:
        if experiment not in de:
            invalid_experiments.append(experiment)

    if invalid_experiments:
        message = "{} The following experiments do " \
                  "not exist: {}".format(common_msg, invalid_experiments)
        raise argparse.ArgumentTypeError(message)
    return experiments


def experiment_exclude_list(v):
    experiments = v.split(',')
    de = default_experiments()
    invalid_experiments = []
    for experiment in experiments:
        if experiment not in de:
             invalid_experiments.append(experiment)

    if invalid_experiments:
        message = "Invalid exclude list. The following experiments do " \
                  "not exist: {}".format(invalid_experiments)
        raise argparse.ArgumentTypeError(message)
    return experiments


def program_args():
    parser = argparse.ArgumentParser()

    parser.add_argument('pool', help='The pool against which to run the ' \
                        'experiment(s). A directory with this name must exist' \
                        ' in the user\'s home directory that contains the ' \
                        ' following files (or at least symlinks to them):' \
                        ' 1. \'pool_transactions_genesis\'' \
                        ' 2. \'clients\' - Comma separated list of clients.' \
                        ' 3. \'ssh_config\' - One entry for each client and' \
                        ' node. See \'man ssh_config\' for details.' \
                        ' 4. PEM file(s). Use the optional pool-config-dir ' \
                        'argument if the directory containing these files is ' \
                        'located elsewhere on the client.')

    parser.add_argument('--job-id', help='The job ID. This will typically be ' \
                        'the Jenkins \'BUILD_TAG\'.', default=None)

    parser.add_argument('--pool-config-dir', help='The location of the ' \
                        'directory on the client that contains pool ' \
                        'configuration files. See \'pool\' argument help for ' \
                        'details. Default: user\'s home directory.',
                        default='~')

    parser.add_argument('--s3bucket', help='The name of the S3 bucket in ' \
                        ' which to store experiment output (succeed or fail).'\
                        ' At minimum, the client designated by the \'client\' '\
                        'argument must be configured to upload files to S3. ' \
                        'Default: None', nargs='?', const=None, default=None)

    parser.add_argument('--experiments', type=experiment_dict, help='A JSON ' \
                        'document/string enumerating the experiments to run ' \
                        'and the parameters to pass to each experiment. ' \
                        'Omitting this option, or using the default results ' \
                        'in all experiments begin run with their default ' \
                        'parameters. Example: --experiments=' \
                        '\'{"force-view-change": {"execution-count" : 10, ' \
                        '"write-nym-timeout: 20}}\' will run the ' \
                        'run-force-view-change script and override the ' \
                        'default execution-count (1) and write-nym-timeout ' \
                        '(60 seconds). See the -h output for each ' \
                        'scripts/run-* script for possible parameters. ' \
                        'Default: None', default=None)

    parser.add_argument('--exclude', type=experiment_exclude_list, help='A ' \
                        'comma separated list of experiments to exclude. ' \
                        'Default: None', default=None)

    parser.add_argument('-c', '--cleanup', type=str2bool, help='Each call to ' \
                        'this script creates a temporary directory. Each ' \
                        'experiment executed by this script creates a ' \
                        'directory in the temporary directory. Each ' \
                        'experiment\'s directory will contain the results of ' \
                        'the experiment. These results are uploaded to an S3 ' \
                        'bucket if the bucket name is provided (see ' \
                        '--s3bucket argument). Should this temporary ' \
                        'directory be deleted when this script exits? ' \
                        'Default: Y Options (case insensitive): y, yes, true,' \
                        ' 1, n, no, false, 0', nargs='?', const='Y',
                        default='Y')

    parser.add_argument('-t', '--test', action='store_true',
                        default=False, help='Runs unit tests and exits.')

    parser.add_argument('-l', '--log-level', type=log_level, nargs='?',
                        const=logging.INFO, default=logging.INFO,
                        help=LOG_LEVEL_HELP)

    return parser


def parse_args(argv=None, parser=program_args()):
    return parser.parse_args(args=argv)


# Clean up anything that is created by this script
def clean_up(job_dir):
    logger.info("Deleting job dir %s...", job_dir)


def init(args):
    # Log to stdout
    # TODO: decide if logging to stdout is permanent
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(args.log_level)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    logger.setLevel(args.log_level)
    logger.debug("Initializing...")
    logger.debug("args: %s", args)


def create_job_dir(build_tag):
    # Get ISO 8601 formatted datetime and create a job dirname
    job_dirname = "{}-{}".format(build_tag, datetime.datetime.now().isoformat())
    #job_dir_path = tempfile.TemporaryDirectory(prefix=job_dirname) 
    job_dir_path = tempfile.mkdtemp(prefix=job_dirname) 
    logger.debug("Temporary Job Dir: {}".format(job_dir_path))
    return job_dir_path


def get_scripts_dir():
    script_path = os.path.dirname(os.path.realpath(__file__))
    scripts_dir = os.path.join(script_path, "scripts")
    return scripts_dir


def reset_pool(pool):
    # TODO: Add functions to chaosindy repo/module to reset pool
    logger.debug("Resetting pool %s...", pool)


def capture_node_state(pool, job_dir):
    # TODO: Add functions to chaosindy repo/module to capture node state
    logger.debug("Capturing node state (nscapture archives) for pool %s and "\
                 "storing results in %s...", pool, job_dir)


def run_experiment(pool, job_dir, experiment, parameters):
    # Each experiment run by each job gets it's own directory.
    # Create experiment directory within the job_dir
    experiment_dir_path = os.path.join(job_dir, experiment)
    try:
        logger.error("Creating experiment directory " \
                     "{}".format(experiment_dir_path))
        os.mkdir(experiment_dir_path)
    except Exception as e:
        logger.error("Failed to create experiment " \
                     "directory {}".format(experiment_dir_path))
    logger.debug("Created directory {} for" \
                 " experiment {}".format(experiment_dir_path, experiment))
    scripts_dir = get_scripts_dir()
    experiment_script = os.path.join(scripts_dir, "run-{}".format(experiment))
    logger.debug("Running experiment {} with parameters {} and placing " \
                 "results in {}".format(experiment_script, parameters.keys(),
                 job_dir))

    # Build arguments list
    arguments = [experiment_script]
    # Append pool/pool_transaction_genesis with --genesis-file
    arguments.append("--genesis-file")
    arguments.append(os.path.expanduser(os.path.join("~", pool, "pool_transactions_genesis")))
    # Append pool/ssh_config with --ssh-config-file
    arguments.append("--ssh-config-file")
    arguments.append(os.path.expanduser(os.path.join("~", pool, "ssh_config")))
    # Append pool/clients with --load-client-nodes
    clients = []
    with open(os.path.expanduser(os.path.join("~", pool, "clients")), 'r') as clients_file:
        clients = json.load(clients_file)
    arguments.append("--load-client-nodes")
    arguments.append(",".join(clients))
    # TODO: Perform some preflight configuration tests to ensure the given pool
    #       (directory containing pool_transactions_genesis, ssh_config, and
    #       clients files) is configured properly
    #       1. Make sure each alias defined in the pool_transactions_genesis has
    #          an entry in the ssh_config file.
    #       2. Make sure each alias defined in the clients file has an entry in
    #          the ssh_config file.
    #       3. Make sure each entry in the ssh_config file has the following
    #          format:
    #          Host <host>
    #              User <user>
    #              Hostname <IP>
    #              IdentityFile <path to PEM or private key file>
    #       4. Make sure each IdentityFile exists/resolves.
    for k, v in parameters:
        arguments.append(k)
        arguments.append(v)
    # Execute the experiment
    result = subprocess.run(arguments, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, cwd=experiment_dir_path)

    # Check the experiment's return code
    status = "succeeded"
    try:
        result.check_returncode()
        # Experiment ran without failure.
        logger.debug("Chaos experiment %s succeeded.", experiment)
    except subprocess.CalledProcessError:
        # Experiment failed.
        logger.debug("Chaos experiment %s failed with a return code of %d.",
                     experiment, result.returncode)
        # Capture node state for each node in the pool
        capture_node_state(pool, job_dir)
        status = "failed"

    # Write the return code, stdout, and stderr to a "run.out" file in the
    # job_dir. It will be useful during the analyze step.
    result_stdout = result.stdout.decode('utf-8') if result.stdout else None
    result_stderr = result.stderr.decode('utf-8') if result.stderr else None
    result_dict = {
        'returncode': result.returncode,
        'stdout': result_stdout,
        'stderr': result_stderr
    }
    run_out_file = os.path.join(experiment_dir_path, "run.out")
    with open(run_out_file, 'w') as outfile:
        json.dump(result_dict, outfile)

    # Write an entry to the "report" file in the job_dir
    # TODO: Make the report more comprehensive. See run.py TODOs in the
    #       README.md file.
    report_file = os.path.join(job_dir, "report")
    with open(report_file, 'a') as report:
        report.write("{}: {}\n".format(experiment, status))


def default_experiments():
    logger.debug("Getting default experiments...")
    scripts_dir = get_scripts_dir()
    experiments = {}
    for file in os.listdir(scripts_dir):
        if file[0:4] == "run-":
            experiment = file[4:]
            experiments[experiment] = {}
    return experiments


def run_experiments(pool, job_dir, experiments={}, exclude=[]):
    if not experiments:
        experiments = default_experiments()
        logger.debug("Using default set of experiments: %s",
                     ', '.join(list(experiments.keys())))

    # Run each experiment iff it is not explicitly excluded.
    for experiment, parameters in experiments.items():
        if experiment not in exclude:
            parameters_msg = ""
            if parameters:
                parameters_list = ', '.join(list(parameters.keys()))
                parameters_msg = " and overriding default " \
                                 "parameters: {}".format(parameters_list)
            logger.info("Running experiment %s%s", experiment, parameters_msg)
            reset_pool(pool)
            run_experiment(pool, job_dir, experiment, parameters)
        else:
            logger.debug("Skipping {} experiment. Found in" \
                         " exclude list.".format(experiment))


def upload(job_dir):
    # Upload results to S3
    pass


def notify(output_location):
    # TODO: notify interested parties (email, slack, etc.)
    logger.info("Chaos experiment results can be found in %s", output_location)


def process_results(job_dir, s3bucket):
    # TODO: Create Chaos experiments report. What experiments passed and failed
    #       and where is experiment output located?
    logger.debug("Processing experiment results located in {}".format(job_dir))

    # Upload results to S3?
    if s3bucket:
        upload(job_dir)
        notify("S3 Bucket: {}".format(s3bucket))
    else:
        notify("Temporary Job Directory: {}:{}".format(socket.gethostname(),
                                                       job_dir))



def main(args):
    try:
        init(args)
    except Exception:
        logger.error('Unable to initialize script')
        raise

    # Create a <JENKINS BUILD_TAG>-<ISO 8601 datetime> folder in the S3 bucket
    try:
        job_dir = create_job_dir(args.job_id)
    except:
        logger.error('Unable to create job dir')
        raise

    # The cleanup argument is overriden to False if an s3bucket argument is not
    # given. Doing so preserves experiment results.
    if not args.s3bucket and args.cleanup:
        logger.info('An S3 bbucket is not given. Cleanup of the Temporary Job' \
                    ' Dir will be skipped in order to preserve job results.')
        args.cleanup = False

    if args.cleanup:
        logger.info('Clean up will be done on exit.')
        atexit.register(clean_up, job_dir)
    else:
        logger.info('Clean up will NOT be done on exit.')
     
    experiments = {}
    if args.experiments: 
        experiments = args.experiments
    exclude_list = []
    if args.exclude:
        exclude_list = args.exclude
    # Run experiments
    run_experiments(args.pool, job_dir, experiments, exclude_list)
    # Process results
    process_results(job_dir, args.s3bucket)


# **************
# *  UNIT TESTS !!!!! (use -t to run them)
# ***************
def test():
    print("The 'unittest' module is not available!\nUnable to run tests!")
    return 0


try:
    import unittest

    def test(args, module='__main__'):
        t = unittest.main(argv=['chaosindy_test'], module=module, exit=False,
                          verbosity=10)
        return int(not t.result.wasSuccessful())

    class TestRun(unittest.TestCase):
        test_pool = "test_pool1"

        @classmethod
        def setUpClass(cls):
            sys.stderr = StringIO()
            logger.setLevel(sys.maxsize)
            pass

        @classmethod
        def tearDownClass(cls):
            pass

        # TODO: need any static methods?
        #@staticmethod

        def test_arg_log_level(self):
            for k, v in levels.items():
                test_args = parse_args([self.test_pool, '-l', k])
                self.assertEqual(test_args.log_level, v)

            test_args = parse_args([self.test_pool, '-l'])
            self.assertEqual(test_args.log_level, logging.INFO,
                             msg='Invalid const level')
            test_args = parse_args([self.test_pool])
            self.assertEqual(test_args.log_level, logging.INFO,
                             msg='Invalid default level')

        def test_experiments_dict(self):
            # Can't test invalid value(s), because argparse exits with a return
            # code of 2 if experiment_dict (type) raises an exception.
            experiments_dict_sample = {
                'force-view-change': {
                    'execution-count': 3
                }
            }
            test_args = parse_args([self.test_pool, '--experiments',
                                    json.dumps(experiments_dict_sample)])
            self.assertEqual(test_args.experiments, experiments_dict_sample)

        def test_experiment_exclude_list(self):
            # Can't test invalid value(s), because argparse exits with a return
            # code of 2 if experiment_dict (type) raises an exception.
            defaults = default_experiments().keys()
            all_experiments = ','.join(defaults)
            test_args = parse_args([self.test_pool, '--exclude',
                                    all_experiments])
            self.assertEqual(test_args.exclude, list(defaults))

        def test_create_job_dir(self):
            build_tag = "foo"
            delimiter = "-"
            job_dir_path = create_job_dir(build_tag)
            self.assertTrue(os.path.exists(job_dir_path))

            try:
                tokens = job_dir_path.split(delimiter)
                create_datetime = delimiter.join(tokens[1:])
                create_datetime = create_datetime[0:-8]
                create_datetime = dateutil.parser.parse(create_datetime)
            except Exception as error:
                self.fail("Failed to extract and parse ISO 8601 datetime from" \
                          " temporary directory created by create_job_dir.")

            now_datetime = datetime.datetime.now()
            self.assertAlmostEqual(create_datetime, now_datetime,
                                   delta=datetime.timedelta(seconds=5))

        def test_default_experiments(self):
            experiments = default_experiments()
            self.assertEqual(type(experiments), dict)
            for k, v in experiments.items():
                self.assertEqual(type(v), dict)
                self.assertEqual(list(v.keys()), [])

        def test_run_experiments_exclude(self):
            build_tag = "bar"
            pool = "baz"
            job_dir_path = create_job_dir(build_tag)
            experiments = default_experiments()
            exclude_list = list(experiments.keys())
            # Skip all default experiments
            run_experiments(pool, job_dir_path, exclude=exclude_list)
            # Expect an empty temp dir
            if (os.path.exists(job_dir_path) and
                os.path.isdir(job_dir_path)):
                if os.listdir(job_dir_path):
                    self.fail("All experiments should have been " \
                              "skipped. Expected an empty directory, but " \
                              "found a non-empty directory.")
            else:
                self.fail("Job dir {} either does not exist or is not a " \
                          "directory")

        #def test_process_results(self):

except ImportError:
    pass

if __name__ == '__main__':
    arguments = parse_args()

    if arguments.test:
        exit_code = test(arguments)
        sys.exit(exit_code)
    else:
        sys.exit(main(arguments))
