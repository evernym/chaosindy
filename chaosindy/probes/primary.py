import json
from chaosindy.execute.execute import FabricExecutor
from chaosindy.common import *
from chaosindy.probes.node import node_ports_are_reachable
from chaosindy.probes.validator_info import detect_mode
from chaosindy.actions.primary import get_primary
from logzero import logger
from time import sleep

def primary_and_replicas_are_reachable(genesis_file,
                                       ssh_config_file="~/.ssh/config",
                                       timeout="5"):
    '''
    Is the primary and all replicas reachable?

    Arguments:
      genesis_file - path to the pool genesis transaction file
    Keyword Arguments (optional):
      ssh_config_file - SSH config file. Defaults to ~/.ssh/config.
      compile_stats - create a 'current_primary' attribute when writing the
                      'primaries' state file and return the name/alias of the
                      primary when calling get_primary?
    '''
    primary = get_primary(genesis_file, compile_stats=True,
                          ssh_config_file=ssh_config_file)
    if primary:
        output_dir = get_chaos_temp_dir()
        with open("{}/{}-validator-info".format(output_dir, primary), 'r') as vif:
            validator_info = json.load(vif)
        n = validator_info['Node_info']['Count_of_replicas']

        logger.debug("Check if client and node ports are reachable for primary %s", primary)
        if not node_ports_are_reachable(genesis_file, primary):
            return False

        for i in range(1, n):
            replica = validator_info['Node_info']['Replicas_status']["{}:{}".format(primary, i)]['Primary'].split(":")[0]
            logger.debug("Check if client and node ports are reachable for replica %s", replica)
            if not node_ports_are_reachable(genesis_file, replica):
                return False
        return True
    return False


def demoted_backup_primaries_are_excluded(genesis_file, 
                                          ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
    """
    Probe that checks if the primary is still trying to reach demoted nodes.

    Arguments:
      genesis_file - path to the pool genesis transaction file
    Keyword Arguments (optional):
      ssh_config_file - SSH config file. Defaults to ~/.ssh/config.
    """
    output_dir = get_chaos_temp_dir()
    primary = get_primary(genesis_file, compile_stats=True,
                          ssh_config_file=ssh_config_file)
    validator_info = {}
    if primary:
        with open("{}/{}-validator-info".format(output_dir, primary), 'r') as vif:
            validator_info = json.load(vif)
    reachable_nodes = validator_info['Pool_info']['Reachable_nodes']

    stopped_replicas_file = "{}/stopped_replicas".format(output_dir)
    stopped_replicas_dict = {}
    try:
        with open(stopped_replicas_file, 'r') as stopped_replicas:
            stopped_replicas_dict = json.load(stopped_replicas)
    except FileNotFoundError as e:
        message = "%s does not exist. Must call stop_n_backup_primaries " \
                  " before calling demoted_backup_primaries_are_excluded"
        logger.error(message, stopped_replicas_file)
        logger.exception(e)
        return False

    if 'stopped_backup_primaries' in stopped_replicas_dict:
        should_not_be_in_reachable_list = []
        for alias in stopped_replicas_dict['stopped_backup_primaries'].keys():
            if alias in reachable_nodes:
                should_no_be_in_reachable_list.append(alias)
        if should_not_be_in_reachable_list:
            logger.error("Primary is trying to reach demoted nodes: %s",
                         " ".join(should_not_be_in_reachable_list))
            return False
        return True
    return False
