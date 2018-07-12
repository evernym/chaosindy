import json
from chaosindy.execute.execute import FabricExecutor
from chaosindy.probes.validator_info import get_chaos_temp_dir, detect_primary
from chaosindy.actions.node import stop_by_node_name, start_by_node_name, start_all_but_by_node_name
from time import sleep

def get_primary(genesis_file, ssh_config_file="~/.ssh/config", compile_stats=True):
    primary = None
    if compile_stats:
        detect_primary(genesis_file, ssh_config_file=ssh_config_file)

    output_dir = get_chaos_temp_dir()
    with open("{}/primaries".format(output_dir), 'r') as primaries:
        primary_dict = json.load(primaries)
    primary = primary_dict.get("current_primary", None)

    return primary

def stop_primary(genesis_file, ssh_config_file="~/.ssh/config", compile_stats=True):
    '''
    Detect and stop the node playing the role of 'primary'
    Store the name/alias of the primary in a 'stopped_primary' file (JSON doc)
    within the experiment's chaos temp dir.

    start_stopped_primary_after_view_change may be called after calling
    stop_primary if the desired result is to start the old primary after a view
    change has completed.

    start_stopped_primary may be called after calling stop_primary if the desired
    result is to start the old primary without considering the state of a
    viewchange.

    Arguments:
      genesis_file - path to the pool genesis transaction file
    Keyword Arguments (optional):
      ssh_config_file - SSH config file. Defaults to ~/.ssh/config.
      compile_stats - create a 'current_primary' attribute when writing the
                      'primaries' state file and return the name/alias of the
                      primary when calling get_primary?
    '''
    primary = get_primary(genesis_file, compile_stats=compile_stats,
                          ssh_config_file=ssh_config_file)
    if primary:
        output_dir = get_chaos_temp_dir()
        stopped_primary = {'stopped_primary': primary}
        with open("{}/stopped_primary".format(output_dir), 'w') as f:
            f.write(json.dumps(stopped_primary))
        return stop_by_node_name(primary, ssh_config_file=ssh_config_file)
    return False

def start_stopped_primary_after_view_change(genesis_file,
                                            max_checks_for_primary=6,
                                            sleep_between_checks=10,
                                            ssh_config_file="~/.ssh/config"):
    '''
    Start the node stopped by a call to stop_primary. When the primary is stopped,
    the pool will perform a viewchange. This function will not start the
    stopped_primary until a completed viewchange is detected.

    stop_primary(...) must be called before
    start_stopped_primary_after_view_change. Otherwise the stopped_primary state
    file in the experiment's chaos temp dir will not exist.

    Assumptions:
      - A "stopped_primary" file exists in the experiments chaos temp dir and
        contains a JSON object produced by a call to get_primary, which has a
        stopped_primary attribute.

    Arguments:
      genesis_file - path to the pool genesis transaction file
    Keyword Arguments (optional):
      max_checks_for_primary - number of times to call get_primary to check which
                               node is primary.
      sleep_between_checks - number of seconds between calls checks for which
                             node is primary.
      ssh_config_file - SSH config file. Defaults to ~/.ssh/config.
    '''
    output_dir = get_chaos_temp_dir()
    stopped_primary_dict = {}
    stopped_primary_file = "{}/stopped_primary".format(output_dir)
    try:
        with open(stopped_primary_file, 'r') as stopped_primary:
            stopped_primary_dict = json.load(stopped_primary)
    except FileNotFoundError as e:
        message = """%s does not exist. Must call stop_primary before calling
                     start_stopped_primary_after_view_change"""
        logger.error(message, stopped_primary_file)
        logger.exception(e)
        return False
    stopped_primary = stopped_primary_dict.get('stopped_primary', None)
    if stopped_primary:
        # Wait until view change is complete. When the primary is not the
        # stopped_primary a viewchange has progressed far enough to achive
        # consensus.
        tries = 0
        while tries < max_checks_for_primary:
            current_primary = get_primary(genesis_file,
                                          ssh_config_file=ssh_config_file,
                                          compile_stats=True)
            if stopped_primary != current_primary:
                break;
            else:
                sleep(sleep_between_checks)
                tries += 1
        if tries < max_checks_for_primary:
            return start_by_node_name(stopped_primary,
                                      ssh_config_file=ssh_config_file)
    return False

def start_stopped_primary(genesis_file, ssh_config_file="~/.ssh/config"):
    '''
    Start the node stopped by a call to stop_primary. When the primary is stopped,
    the pool will perform a viewchange. This function starts the stopped_primary
    even if the viewchange is not complete.

    Arguments:
      genesis_file - path to the pool genesis transaction file
    Keyword Arguments (optional):
      ssh_config_file - SSH config file. Defaults to ~/.ssh/config.
    '''
    output_dir = get_chaos_temp_dir()
    stopped_primary_dict = {}
    stopped_primary_file = "{}/stopped_primary".format(output_dir)
    try:
        with open(stopped_primary_file, 'r') as stopped_primary:
            stopped_primary_dict = json.load(stopped_primary)
    except FileNotFoundError as e:
        message = """%s does not exist. Must call stop_primary before calling
                     start_stopped_primary"""
        logger.error(message, stopped_primary_file)
        logger.exception(e)
        return False
    primary = stopped_primary_dict.get('stopped_primary', None)
    if primary:
        return start_by_node_name(primary, ssh_config_file=ssh_config_file)
    return False

def start_all_but_primary(genesis_file, ssh_config_file="~/.ssh/config", compile_stats=False):
    primary = get_primary(genesis_file, compile_stats=compile_stats,
                          ssh_config_file=ssh_config_file)
    if primary:
        return start_all_but_by_node_name(primary, genesis_file=genesis_file, ssh_config_file=ssh_config_file)
    return False
