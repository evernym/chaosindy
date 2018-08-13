import json, random
from chaosindy.common import *
from chaosindy.execute.execute import FabricExecutor
from chaosindy.probes.validator_info import detect_primary
from chaosindy.actions.node import start_by_strategy, stop_by_strategy
from logzero import logger
from time import sleep


def get_primary(genesis_file, ssh_config_file="~/.ssh/config",
                compile_stats=True):
    """
    Return the alias of the primary from the 'primaries' state file.

    Arguments:
      genesis_file - path to the pool genesis transaction file
    Keyword Arguments (optional):
      ssh_config_file - SSH config file. Defaults to ~/.ssh/config.
      compile_stats - Set to True to create/recreate the 'primaries' state file.
                      Set to False if the last computed "current_primary" in the
                      'primaries' state file is sufficient. get_primary MUST be
                      called at least once with compile_stats=True before
                      calling it with compile_stats=False. Otherwise, the
                      'primaries' state file will not exist, resulting in a
                      stacktrace. By design (in context to chaos experiments),
                      the stacktrace (File Not Found) tells you your experiment
                      is not written correctly.
    """
    primary = None
    if compile_stats:
        detect_primary(genesis_file, ssh_config_file=ssh_config_file)

    output_dir = get_chaos_temp_dir()
    with open("{}/primaries".format(output_dir), 'r') as primaries:
        primary_dict = json.load(primaries)
    primary = primary_dict.get("current_primary", None)

    return primary


def stop_primary(genesis_file, stop_strategy=StopStrategy.SERVICE.value,
                 ssh_config_file="~/.ssh/config"):
    """
    Detect and stop the node playing the role of 'primary'
    Store the name/alias of the primary in a 'stopped_primary' file (JSON doc)
    within the experiment's chaos temp dir.

    start_stopped_primary_after_view_change may be called after calling
    stop_primary if the desired result is to start the old primary after a view
    change has completed.

    start_stopped_primary may be called after calling stop_primary if the
    desired result is to start the old primary without considering the state of
    a viewchange.

    Arguments:
      genesis_file - path to the pool genesis transaction file
    Keyword Arguments (optional):
      stop_strategy - How should the primary be stopped? See StopStrategy in
                      chaosindy.common for options.
      ssh_config_file - SSH config file. Defaults to ~/.ssh/config.
    """
    primary = get_primary(genesis_file, compile_stats=True,
                          ssh_config_file=ssh_config_file)
    if primary:
        output_dir = get_chaos_temp_dir()
        stopped_primary = {
            'stopped_primary': primary
        }

        details = stop_by_strategy(genesis_file, primary, stop_strategy,
                                   ssh_config_file=ssh_config_file)
        if not details:
            message = """Failed to stop primary node %s by strategy %d"""
            logger.error(message, primary, stop_strategy)
            return False

        stopped_primary['stopped_primary_details'] = details
        with open("{}/stopped_primary".format(output_dir), 'w') as f:
            f.write(json.dumps(stopped_primary))
        return True
    return False


def start_stopped_primary_after_view_change(genesis_file,
                                            max_checks_for_primary=6,
                                            sleep_between_checks=10,
                                            start_backup_primaries=True,
                                            ssh_config_file="~/.ssh/config"):
    """
    Start the node stopped by a call to stop_primary. When the primary is
    stopped, the pool will perform a viewchange. This function will not start
    the stopped primary until a completed viewchange is detected.

    stop_primary(...) or stop_f_backup_primaries_before_primary(...) must be
    called before start_stopped_primary_after_view_change. Otherwise the
    stopped_primary state file in the experiment's chaos temp dir will not
    exist.

    By default, if an experiment stops replica nodes (a.k.a. backup primaries),
    the stopped replicas will be started before the stopped primary is started.

    Assumptions:
      - A "stopped_primary" file exists in the experiments chaos temp dir and
        contains a JSON object produced by a call to stop_primary or
        stop_f_backup_primaries_before_primary, which has a stopped_primary
        attribute.
      - If a "stopped_backup_primaries" element exists in the JSON, and the
        start_backup_primaries kwarg is True, the stopped backup primaries
        should be started.

    Arguments:
      genesis_file - path to the pool genesis transaction file
    Keyword Arguments (optional):
      max_checks_for_primary - number of times to call get_primary to check
                               which node is primary.
      sleep_between_checks - number of seconds between calls checks for which
                             node is primary.
      start_backup_primaries - Start stopped replicas before starting stopped
                               primary?
      ssh_config_file - SSH config file. Defaults to ~/.ssh/config.
    """
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
            logger.debug("Check %d of %d if view change is complete", tries,
                         max_checks_for_primary)
            logger.debug("Former primary: %s", stopped_primary)
            logger.debug("Current primary: %s", current_primary)
            if current_primary and stopped_primary != current_primary:
                logger.debug("View change detected!")
                break;
            else:
                logger.debug("View change not yet complete. Sleeping for {} seconds...".format(sleep_between_checks))
                sleep(sleep_between_checks)
                tries += 1
        # Only start stopped primary and backup primaries if a viewchange
        # completed.
        if tries < max_checks_for_primary:
            # Start backup primaries?
            stopped_backup_primaries = stopped_primary_dict.get(
                'stopped_backup_primaries', None)
            if start_backup_primaries and stopped_backup_primaries:
                for backup_primary in stopped_backup_primaries:
                    started = start_by_strategy(genesis_file, backup_primary,
                        stopped_backup_primaries[backup_primary],
                        ssh_config_file=ssh_config_file)
                    if not started:
                        message = """Failed to start backup primary node %s"""
                        logger.error(message, backup_primary)
                        return False
            # Start stopped primary
            stopped_primary_details = stopped_primary_dict.get(
                'stopped_primary_details', None)
            return start_by_strategy(genesis_file, stopped_primary,
                                     stopped_primary_details,
                                     ssh_config_file=ssh_config_file)
    return True

def start_stopped_primary(genesis_file, start_backup_primaries=True,
                          ssh_config_file="~/.ssh/config"):
    """
    Start the node stopped by a call to stop_primary. When the primary is
    stopped, the pool will perform a viewchange. This function starts the
    stopped_primary even if the viewchange is not complete.

    By default, if an experiment stops replica nodes (a.k.a. backup primaries),
    the stopped replicas will be started before the stopped primary is started.

    Arguments:
      genesis_file - path to the pool genesis transaction file
    Keyword Arguments (optional):
      start_backup_primaries - Start stopped replicas before starting stopped
                               primary?
      ssh_config_file - SSH config file. Defaults to ~/.ssh/config.
    """
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
        stopped_backup_primaries = stopped_primary_dict.get(
            'stopped_backup_primaries', None)
        if stopped_backup_primaries:
            message = """Detected stopped backup primaries %s. Starting backup
                         primaries before starting stopped primary..."""
            for backup_primary in stopped_backup_primaries:
                started = start_by_strategy(genesis_file, backup_primary,
                    stopped_backup_primaries[backup_primary],
                    ssh_config_file=ssh_config_file)
            if not started:
                message = """Failed to start backup primary node %s"""
                logger.error(message, backup_primary)
                return False
        stopped_primary_details = stopped_primary_dict.get(
            'stopped_primary_details', None)
        return start_by_strategy(genesis_file, primary, stopped_primary_details,
                                 ssh_config_file=ssh_config_file)
    return False


def stop_f_backup_primaries_before_primary(genesis_file, f=None,
                                           stop_strategy=StopStrategy.SERVICE.value,
                                           ssh_config_file="~/.ssh/config"):
    """
    Stop exactly a certain number of backup primaries. Defaults to cluster's f
    value or number of replicas, whichever is less.
    TODO: Add selection_strategy? selection_strategy - How to select which <f>
          backup primaries to stop. Options defined by SelectionStrategy in
          chaosindy.common
    TODO: Move to a chaosindy.actions.replica.py?
    TODO: Change state file from stopped_replicas to stopped_primary? If so,
          must change logic to read the file into a dict (default empty dict),
          add/update the dict, and write it out to disk. Overwriting the file
          will not work. Perhaps the common module can be enhanced to support
          get_state, set_state abstractions?

    Arguments:
      genesis_file - path to the pool genesis transaction file
    Keyword Arguments (optional):
      f - This is typically the number of nodes that can fail w/o losing
          consensus and can be found in validator-info. It is exposed as a
          parameter as a means for experimentation.
      stop_strategy - How should backup primaries and the primary be stopped?
                      See StopStrategy in chaosindy.common for options.
      ssh_config_file - SSH config file. Defaults to ~/.ssh/config.
    """
    primary = get_primary(genesis_file, compile_stats=True,
                          ssh_config_file=ssh_config_file)
    if primary:
        output_dir = get_chaos_temp_dir()
        with open("{}/{}-validator-info".format(output_dir, primary), 'r') as vif:
            validator_info = json.load(vif)
        # Stop up to f backup primaries
        # Set f if not defined
        if not f:
            # TODO: determine if f_value is always less than Count_of_replicas.
            f = min(validator_info['Node_info']['Count_of_replicas'],
                    validator_info['Pool_info']['f_value'])

        backup_primaries = {}
        # No backup primaries are stopped when f == 1
        i = 1
        if f > 1:
            # Starting at 1 and iterating up to, but not inclding f ensures we
            # do not fall out of concensus by shutting down too many nodes.
            node_info = validator_info['Node_info']
            replica_status = node_info['Replicas_status']
            for i in range(1, f):
                replica = replicas_status["{}:{}".format(primary, i)]['Primary']
                replica = replica.split(":")[0]
                details = stop_by_strategy(genesis_file, replica, stop_strategy,
                    ssh_config_file=ssh_config_file)
                backup_primaries[replica] = details
        # Get the next expected primary
        next_primary = replicas_status["{}:{}".format(primary, i+1)]['Primary']
        next_primary = next_primary.split(":")[0]

        # Stop the primary
        primary_details = stop_by_strategy(genesis_file, primary, stop_strategy,
            ssh_config_file=ssh_config_file)

        primary_data = {
            'stopped_primary': primary,
            'stopped_primary_details': primary_details,
            'stopped_backup_primaries': backup_primaries,
            'next_primary': next_primary
        }
        with open("{}/stopped_primary".format(output_dir), 'w') as f:
            f.write(json.dumps(primary_data))
        return True
    return False


def stop_n_backup_primaries(genesis_file, number_of_nodes=None,
                            selection_strategy=SelectionStrategy.FORWARD.value,
                            stop_strategy=StopStrategy.SERVICE.value,
                            ssh_config_file="~/.ssh/config"):
    """
    Stop a least one or more backup primaries (replicas)
    TODO: Move to a chaosindy.actions.replica.py?
    TODO: Change state file from stopped_replicas to stopped_primary? If so,
          must change logic to read the file into a dict (default empty dict),
          add/update the dict, and write it out to disk. Overwriting the file
          will not work. Perhaps the common module can be enhanced to support
          get_state, set_state abstractions?

    Assumptions:
      - A pool of at least 4 nodes

    Arguments:
      genesis_file - path to the pool genesis transaction file
    Keyword Arguments (optional):
      number_of_nodes - How many backup replicas to stop. Must be greater than 1
                        and no more than the number of replicas reported by
                        validator info.
      selection_strategy - How to select which <number_of_nodes>backup
                           primaries to stop. Options defined by
                           SelectionStrategy in chaosindy.common
      stop_strategy - How to "stop" backup primaries. Options defined by
                      StopStrategy in chaosindy.common
      ssh_config_file - SSH config file. Defaults to ~/.ssh/config.
    """

    # Variable substitution in chaostoolkit appears to only support strings.
    # When variables are not strings, they will need to be converted/cast.
    if number_of_nodes:
        number_of_nodes = int(number_of_nodes)
    if selection_strategy:
        selection_strategy = int(selection_strategy)

    if number_of_nodes <= 0:
        message = """number_of_nodes must be > 0. number_of_nodes is {}"""
        logger.error(message.format(number_of_nodes))
        return False

    if not SelectionStrategy.has_value(selection_strategy):
        message = """Invalid selection strategy.
                     chaosindy.common.SelectionStrategy does not contain value
                     {}"""
        logger.error(message.format(selection_strategy))
        return False

    if not StopStrategy.has_value(stop_strategy):
        message = """Invalid stop strategy.
                     chaosindy.common.StopStrategy does not contain value
                     {}"""
        logger.error(message.format(stop_strategy))
        return False

    # Get replica information from the primary's validator info
    primary = get_primary(genesis_file, compile_stats=True,
                          ssh_config_file=ssh_config_file)
    if primary:
        output_dir = get_chaos_temp_dir()
        with open("{}/{}-validator-info".format(output_dir, primary), 'r') as vif:
            validator_info = json.load(vif)
        # Stop up to n-1 backup primaries
        # Set n if not defined or >= node's reported replica count
        replica_count = validator_info['Node_info']['Count_of_replicas']
        if not number_of_nodes or (number_of_nodes >= replica_count):
            number_of_nodes = (replica_count - 1)

        stopped_backup_primaries = {}
        # Determine the nodes to stop based on the SelectionStrategy
        nodes_to_stop = list(range(1, replica_count))
        if selection_strategy == SelectionStrategy.RANDOM.value:
            nodes_to_stop_random = []
            # Use a copy of the list of nodes to stop so randomly selected nodes
            # do not get randomly selected more than once.
            nodes_to_stop_copy = nodes_to_stop.copy()
            for i in range(number_of_nodes):
                random_node = random.choice(nodes_to_stop_copy)
                nodes_to_stop_random.append(random_node)
                # Remove the random_node so it doesn't get selected again.
                nodes_to_stop_copy.remove(random_node)
            nodes_to_stop = nodes_to_stop_random
        elif selection_strategy == SelectionStrategy.REVERSE.value:
            nodes_to_stop = list(reversed(nodes_to_stop))[0:number_of_nodes]
        elif selection_strategy == SelectionStrategy.FORWARD.value:
            nodes_to_stop = nodes_to_stop[0:number_of_nodes]

        node_info = validator_info['Node_info']
        replica_status = node_info['Replicas_status']
        for i in nodes_to_stop:
            replica = replica_status["{}:{}".format(primary, i)]['Primary']
            replica = replica.split(":")[0]
            details = stop_by_strategy(genesis_file, replica, stop_strategy,
                ssh_config_file=ssh_config_file)
            if not details:
                return False
            stopped_backup_primaries[replica] = details

        primary_data = {
            'stopped_backup_primaries': stopped_backup_primaries
        }
        with open("{}/stopped_replicas".format(output_dir), 'w') as f:
            f.write(json.dumps(primary_data))
        return True
    return False

def start_stopped_backup_primaries(genesis_file,
                                   ssh_config_file="~/.ssh/config"):
    """
    Start the replicas stopped by a call to stop_n_backup_primaries.

    stop_n_backup_primaries must be called before
    start_stopped_backup_primaries. Otherwise the stopped_replicas state
    file in the experiment's chaos temp dir will not exist.
    TODO: Move to a chaosindy.actions.replica.py?
    TODO: Change state file from stopped_replicas to stopped_primary? If so,
          must change logic to read the file into a dict (default empty dict),
          add/update the dict, and write it out to disk. Overwriting the file
          will not work. Perhaps the common module can be enhanced to support
          get_state, set_state abstractions?

    Assumptions:
      - A "stopped_replicas" file exists in the experiments chaos temp
        dir and contains a JSON object produced by a call to
        stop_n_backup_primaries, which has a stopped_backup_primaries attribute.
      - A "stopped_backup_primaries" element exists in the JSON

    Arguments:
      genesis_file - path to the pool genesis transaction file
    Keyword Arguments (optional):
      ssh_config_file - SSH config file. Defaults to ~/.ssh/config.
    """
    output_dir = get_chaos_temp_dir()
    stopped_primary_dict = {}
    stopped_replicas_file = "{}/stopped_replicas".format(output_dir)
    try:
        with open(stopped_replicas_file, 'r') as stopped_primary:
            stopped_primary_dict = json.load(stopped_primary)
    except FileNotFoundError as e:
        message = """%s does not exist. Must call stop_n_backup_primaries before'
                     calling start_stopped_backup_primaries"""
        logger.error(message, stopped_replicas_file)
        logger.exception(e)
        return False

    stopped_backup_primaries = stopped_primary_dict.get('stopped_backup_primaries', None)
    if not stopped_backup_primaries:
        message ="""Missing stopped_backup_primaries element in
                    stopped_replicas state file {}"""
        logger.error(message.format(stopped_replicas_file))
        return False

    for backup_primary in stopped_backup_primaries.keys():
        succeeded = start_by_strategy(genesis_file, backup_primary,
            stopped_backup_primaries[backup_primary],
            ssh_config_file=ssh_config_file)
        if not succeeded:
            return False
    return True
