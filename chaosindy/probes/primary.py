import json
from chaosindy.execute.execute import FabricExecutor
from chaosindy.common import *
from chaosindy.probes.node import node_ports_are_reachable
from chaosindy.probes.validator_info import detect_mode
from chaosindy.actions.node import get_primary
from logzero import logger
from time import sleep

def primary_and_replicas_are_reachable(genesis_file: str,
    ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Is the primary and all replicas reachable?

    :param genesis_file: The relative or absolute path to the genesis
        transaction file.
        Required.
    :type ssh_config_file: str
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
    """
    primary = get_primary(genesis_file, compile_stats=True,
                          ssh_config_file=ssh_config_file)
    if primary:
        output_dir = get_chaos_temp_dir()
        vif = "{}/{}-validator-info".format(output_dir, primary)
        with open(vif, 'r') as vifh:
            validator_info = json.load(vifh)
        n = validator_info['Node_info']['Count_of_replicas']

        logger.debug("Check if client and node ports are reachable for " \
                     "primary %s", primary)
        if not node_ports_are_reachable(genesis_file, primary):
            return False

        for i in range(1, n):
            replica_status = validator_info['Node_info']['Replicas_status']
            primary = replica_status["{}:{}".format(primary, i)]['Primary']
            replica = primary.split(":")[0]
            logger.debug("Check if client and node ports are reachable for " \
                         "replica %s", replica)
            if not node_ports_are_reachable(genesis_file, replica):
                return False
        return True
    return False


def demoted_backup_primaries_are_excluded(genesis_file: str,
    ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Check if the primary is still trying to reach demoted nodes.

    :param genesis_file: The relative or absolute path to the genesis
        transaction file.
        Required.
    :type ssh_config_file: str
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
    """
    output_dir = get_chaos_temp_dir()
    primary = get_primary(genesis_file, compile_stats=True,
                          ssh_config_file=ssh_config_file)
    validator_info = {}
    if primary:
        vif = "{}/{}-validator-info".format(output_dir, primary)
        with open(vif, 'r') as vifh:
            validator_info = json.load(vifh)
    reachable_nodes = validator_info['Pool_info']['Reachable_nodes']

    stopped_nodes_file = "{}/stopped_nodes".format(output_dir)
    stopped_nodes_dict = {}
    try:
        with open(stopped_nodes_file, 'r') as stopped_nodes:
            stopped_nodes_dict = json.load(stopped_nodes)
    except FileNotFoundError as e:
        message = "%s does not exist. Must call stop_n_nodes " \
                  " before calling demoted_backup_primaries_are_excluded"
        logger.error(message, stopped_nodes_file)
        logger.exception(e)
        return False

    if 'stopped_backup_primaries' in stopped_nodes_dict:
        should_not_be_in_reachable_list = []
        for alias in stopped_nodes_dict['stopped_backup_primaries'].keys():
            if alias in reachable_nodes:
                should_no_be_in_reachable_list.append(alias)
        if should_not_be_in_reachable_list:
            logger.error("Primary is trying to reach demoted nodes: %s",
                         " ".join(should_not_be_in_reachable_list))
            return False
        return True
    return False
