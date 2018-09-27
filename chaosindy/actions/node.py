import os
import json
import random
import subprocess
import time
from chaosindy.common import *
from chaosindy.execute.execute import FabricExecutor, ParallelFabricExecutor
from chaosindy.probes.validator_info import get_validator_info, detect_primary
from chaosindy.probes.validator_state import get_current_validator_list
from logzero import logger
from multiprocessing import Pool
from os.path import expanduser, join
from time import sleep
from typing import Union, List, Dict

def generate_load(client: str, command: str = DEFAULT_CHAOS_LOAD_COMMAND,
                  timeout: Union[str,int] = DEFAULT_CHAOS_LOAD_TIMEOUT,
                  ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Generate load on the ledger from a single client.

    Returns True if the command runs to completion without error. Otherwise,
    returns False.

    :param client: The client's alias/hostname from which to generate load.
        Required.
    :type client: str
    :param command: The load command to execute from the given client.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_LOAD_COMMAND)
    :type command: str
    :param timeout: How long the command may execute before timing out.
        Optional. (Default: chaosindy.common.DEFAULT_LOAD_TIMEOUT)
    :type timeout: str or int
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
    """
    message = """Generating load from client %s using command >%s< and timeout
                 >%s seconds<"""
    logger.info(message, client, command, timeout)
    executor = FabricExecutor(ssh_config_file=expanduser(ssh_config_file))
    result = executor.execute(client, command, as_sudo=True,
                              timeout=int(timeout))
    if result.return_code != 0:
        logger.error("Failed to generate load from client %s", client)
        return False
    return True


def generate_load_parallel(clients = List[str],
    command: str = DEFAULT_CHAOS_LOAD_COMMAND,
    timeout: Union[str,int] = DEFAULT_CHAOS_LOAD_TIMEOUT,
    ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Generate load on the ledger from one or more clients in parallel.

    :param clients: A list of client aliases/hostnames from which to generate
        load. Required.
    :type clients: List[str]
    :param command: The load command to execute from the given client(s). To get
        this right, first try to execute the command that generates load on each
        client to ensure the load script is found/reachable and accepts the
        parameters/options you are passing to it.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_LOAD_COMMAND)
    :type command: str
    :param timeout: How long the command may execute before timing out.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_LOAD_TIMEOUT)
    :type timeout: Union[str,int]
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
    """
    message = """Generating load from clients %s using command >%s< and timeout
                 >%s seconds<"""
    logger.info(message, clients, command, timeout)
    try:
        client_list = json.loads(clients)
    except Exception as e:
        message = """Failed to parse JSON clients list. The list of clients on
                     which to generate load, must be a valid JSON list of node
                     aliases found in your ssh config file %s"""
        logger.error(message, ssh_config_file)
        logger.exception(e)
        return False
    ssh_config_file=expanduser(ssh_config_file)
    executor = ParallelFabricExecutor(ssh_config_file=ssh_config_file)
    result = executor.execute(client_list, command, as_sudo=True,
                              timeout=int(timeout))

    logger.debug("result: %s", json.dumps(result))
    for client in client_list:
        if result[client]['return_code'] != 0:
            logger.error("Failed to generate load from client %s", client)
            return False
    return True


def apply_iptables_rule_by_node_name(node: str, rule: str,
    ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Apply an iptables rule on a node.

    :param node: The node's alias/hostname. Required.
    :type node: str
    :param rule: The iptables rule. Required.
    :type rule: str
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
    """
    logger.debug("applying iptables rule >%s< on node: %s", rule, node)
    executor = FabricExecutor(ssh_config_file=expanduser(ssh_config_file))

    ## 1. Apply iptables rule
    try:
        result = executor.execute(node, "iptables {}".format(rule),
                                  as_sudo=True)
        if result.return_code != 0:
            logger.error("Failed to apply iptables rule >%s< on node %s", rule,
                         node)
            return False
    except Exception as e:
        logger.exception(e)
        raise e

    return True


def block_port_by_node_name(node: str, port: str,
    ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Block a port on a node.

    :param node: The node's alias/hostname. Required.
    :type node: str
    :param port: The port or port range to block. A port range is formatted
        <from port>:<to port>. Required.
    :type port: str
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
    """
    logger.debug("block node %s on port %s", node, port)
    ## 1. Block a port or port range using a firewall
    if ":" in port:
        rule = "-A INPUT -p tcp --match multiport --dports {} -j" \
               " DROP".format(port)
    else:
        rule = "-A INPUT -p tcp --destination-port {} -j DROP".format(port)
    return apply_iptables_rule_by_node_name(node, rule, ssh_config_file)


def unblock_port_by_node_name(node: str, port: str, best_effort: bool = False,
    ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Unblock a port on a node.

    :param node: The node's alias/hostname. Required.
    :type node: str
    :param port: The port or port range to block. A port range is formatted
        <from port>:<to port>. Required.
    :type port: str
    :param best_effort: Do NOT fail if the operation fails? (Default: False)
    :type best_effort: bool
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
    """
    logger.debug("unblock node %s on port %s", node, port)
    do_not_fail = ""
    if best_effort:
       do_not_fail = " || true"

    ## 1. Unblock a port or port range using a firewall
    if ":" in port:
        rule = "-D INPUT -p tcp --match multiport --dports {} -j" \
               " DROP{}".format(port, do_not_fail)
    else:
        rule = "-D INPUT -p tcp --destination-port {} -j" \
               " DROP{}".format(port, do_not_fail)

    try:
        return apply_iptables_rule_by_node_name(node, rule, ssh_config_file)
    except Exception as e:
        logger.exception(e)
        raise e

    return True


def indy_node_is_stopped(node: str, timeout: Union[str,int] = 30,
    ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Check if indy-node and indy-node-control services are stopped.

    :param node: The node alias. Required.
    :type node: str
    :param timeout: Timeout waiting for status response.
        Optional. (Default: 30 seconds)
    :type timeout: Union[str, int]
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
    """
    # TODO: Decide if `systemctl is-active indy-node` is sufficient. Until then
    #       assume that absense of a pid is more definitive.
    logger.debug("Ensure indy-node/indy-node-control is stopped...")
    command = "ps -ef | grep 'start_indy_node\|start_node_control_tool'"\
              " | grep -v grep | awk '{print $2}' | wc -l"
    executor = FabricExecutor(ssh_config_file=expanduser(ssh_config_file))
    result = executor.execute(node,
                              command,
                              timeout=int(timeout), as_sudo=True)
    if result.return_code == 0 and result.stdout.strip() == "0":
       return True
    return False


def stop_by_node_name(node: str, gracefully: bool = True, force: bool = True,
    timeout: Union[str,int] = 30,
    ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Stop indy-node service by node name/alias

    The following combinations of 'gracefully' and 'force' flags should be
    considered:
    gracefully: True  force: False - Only stop indy-node using systemctl
    gracefully: False force: True  - Kill the indy-node process. Do not allow it
                                     to gracefully shutdown.
    gracefully: True  force: True  - First try to stop indy node using systemctl
                                     and kill -9 the process if and only if
                                     systemctl fails to stop the process
                                     gracefully.

    :param node: The node name/alias. Required.
    :type node: str
    :param gracefully: Use systemctl to stop the services?
    :type gracefully: bool
    :param force: kill -9 (SIGKILL) the services?
    :type force: bool
    :param timeout: Timeout waiting for service to stop.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_LOAD_COMMAND)
    :type timeout: Union[str,int]
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
    """
    logger.debug("stop node: %s", node)
    executor = FabricExecutor(ssh_config_file=expanduser(ssh_config_file))

    # Do not allow both gracefully and force to be set to False
    if not gracefully and not force:
        logger.info("Invalid gracefully/force flag options. Setting both to " \
                    "False is effectively a no-op.")
        return False

    if gracefully:
        logger.debug("Attempting to stop indy-node service gracefully...")
        # 1. Stop the node by alias name
        result = executor.execute(node,
                                  "systemctl stop indy-node indy-node-control",
                                  timeout=int(timeout), as_sudo=True)
        if result.return_code != 0:
            logger.error("Failed to stop %s using systemctl", node)
            if not force:
                return False
        else:
            # systemctl does not wait for the unit to stop. It issues a signal
            # and moves on. The indy-node service has been observed to take up
            # to a minute to stop. Ensure both indy-node and indy-node-control
            # pids do not exist. Try up to 10 times with a 6 second sleep in
            # between tries.
            tries = 0
            while True:
                logger.debug("Ensuring node services are stopped: try %d...",
                             tries)
                if tries == 10 or indy_node_is_stopped(node, timeout=timeout,
                    ssh_config_file=ssh_config_file) or tries == 10:
                    break
                tries += 1
                sleep(6)
            if tries < 10:
                logger.debug("Node services guaranteed to be stopped.")
                return True
            else:
                logger.debug("Node services are still running.")
                return False

    if force:
        logger.debug("Attempting to stop indy-node service forcefully...")
        # 1. Stop the node by alias name
        kill_command = "kill -9 $(ps -ef |" \
                       " grep 'start_indy_node\|start_node_control_tool' |" \
                       " grep -v grep | awk '{print $2}' | xargs)"
        result = executor.execute(node, kill_command, timeout=int(timeout),
                                  as_sudo=True)
        if result.return_code != 0:
            logger.error("Failed to forcefully stop %s using kill -9", node)
            return False

    return True


def start_by_node_name(node: str,
    ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Start indy-node service by node name/alias

    :param node: The node name/alias. Required.
    :type node: str
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
    """
    logger.debug("start node: %s", node)
    executor = FabricExecutor(ssh_config_file=expanduser(ssh_config_file))

    # Start the node by alias name
    result = executor.execute(node, "systemctl start indy-node", as_sudo=True)
    if result.return_code != 0:
        logger.error("Failed to start %s", node)
        return False

    return True


def start_nodes(aliases: List[str] = [],
                ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Start indy-node service on a list of nodes.

    :param aliases: A list of nodes. Required.
    :type aliases: List[str]
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
    """
    # Start all nodes listed in aliases list
    count = len(aliases)
    tried_to_start = 0
    are_alive = 0
    for alias in aliases:
        logger.debug("alias to start: %s", alias)
        if start_by_node_name(alias, ssh_config_file):
            are_alive += 1
        tried_to_start += 1

    logger.debug("are_alive: %s -- count: %s -- tried_to_start: %s -- " \
                 "len-aliases: %s", are_alive, count, tried_to_start,
                 len(aliases))
    if are_alive != int(count):
        return False

    return True


def stop_nodes(aliases: List[str] = [],
               ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Stop indy-node service on a list of nodes.

    :param aliases: A list of nodes. Required.
    :type aliases: List[str]
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
    """
    # Start all nodes listed in aliases list
    count = len(aliases)
    tried_to_stop = 0
    are_alive = 0
    for alias in aliases:
        logger.debug("alias to stop: %s", alias)
        if stop_by_node_name(alias, ssh_config_file):
            are_alive += 1
        tried_to_stop += 1

    logger.debug("are_alive: %s -- count: %s -- tried_to_stop: %s -- " \
                 "len-aliases: %s", are_alive, count, tried_to_stop,
                 len(aliases))

    if are_alive != int(count):
        return False

    return True


def all_nodes_up(genesis_file: str,
                 ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Ensure indy-node service is running on all nodes in the genesis file.

    :param genesis_file: The relative or absolute path to a genesis file.
    :type genesis_file: str
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
    """
    logger.debug("genesis_file: %s -- ssh_config_file: %s", genesis_file,
                 ssh_config_file)
    # 1. Get all node aliases
    aliases = get_aliases(genesis_file)
    logger.debug(aliases)

    # 2. Start all nodes.
    return start_nodes(aliases, ssh_config_file)


def unblock_node_port_all_nodes(genesis_file: str, best_effort: bool = True,
    ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Unblock indy-node port on all nodes.

    :param genesis_file: The relative or absolute path to a genesis file.
    :type genesis_file: str
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
    """
    logger.debug("genesis_file: %s", genesis_file)
    # 1. Get all node aliases
    aliases = get_aliases(genesis_file)
    logger.debug(aliases)

    for node in aliases:
        logger.debug("node: %s -- genesis_file: %s", node, genesis_file)
        node_info = get_info_by_node_name(genesis_file, node)
        try:
            unblock_port_by_node_name(node, str(node_info['node_port']),
                                      ssh_config_file)
        except Exception as e:
            logger.exception(e)
            if not best_effort:
                return False

    return True


def get_random_nodes(genesis_file: str, count: Union[str,int]) -> List[str]:
    """
    Randomly select and return a unique set of nodes.

    If the caller requests more nodes than are defined in the genesis file, a
    complete list will be returned in random order. It is up to the caller to
    check if the returned list contains the number of nodes requested.

    Nodes are removed from consideration once they have been selected. Doing so
    ensures a unique set of random nodes.

    TODO: decide if a (int, List) tuple would be a more desireable return type

    :param genesis_file: The relative or absolute path to a genesis file.
        Required
    :type genesis_file: str
    :param count: How many nodes to randomly select from the genesis file.
        Required
    :type count: Union[str,int]
    :return: List[str]
    """
    logger.debug("genesis_file: %s -- count: %s", genesis_file, count)
    # 1. Get all node aliases
    aliases = get_aliases(genesis_file)
    logger.debug(aliases)

    # 2. Get 'count' nodes.
    tried_to_get = 0
    selected = []
    number_of_aliases = len(aliases)
    while len(selected) < int(count) and tried_to_get < number_of_aliases:
        node = random.choice(aliases)
        aliases.remove(node)
        selected.append(node)
        tried_to_get += 1

    logger.debug("selected: %s, count: %s, len-aliases: %s", len(selected),
                 count, number_of_aliases)
    return selected


def block_node_port_random(genesis_file: str, count: Union[str,int],
    ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Block the indy-node port on a random set of nodes.

    If the caller requests more nodes than are defined in the genesis file, all
    nodes will be blocked in random order.

    State file "block_node_port_random" located in the chaos temp dir (see
    get_chaos_temp_dir for details) is shared with the following functions
    block_node_port_random
    unblock_node_port_random
    unblocked_nodes_are_caught_up

    Because the aforementioned functions share a state file, they are intended
    to be used together. The typical workflow would be:

    1. Block the node port on some nodes (block_node_port_random)
    2. Optionally do something while node ports are blocked (i.e. generate load)
    3. Unblock node port on the set of nodes selected in step 1 above.
    4. Optionally do something while nodes are catching up.
    5. Check if nodes unblocked in step 3 above are caught up.

    :param genesis_file: The relative or absolute path to a genesis file.
        Required.
    :type genesis_file: str
    :param count: The number of nodes
    :type count: Union[str,int]
    :param ssh_config_file: The relative or absolute path to the
        ssh_config_file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
    """
    # TODO: Use the traffic shaper tool Kelly is using.
    # http://www.uponmyshoulder.com/blog/2013/simulating-bad-network-conditions-on-linux/
    selected = get_random_nodes(genesis_file, count)
    output_dir = get_chaos_temp_dir()
    blocked = 0
    tried_to_block = 0
    blocked_ports = {}
    for node in selected:
        logger.debug("node alias to block: %s", node)
        node_info = get_info_by_node_name(genesis_file, node)
        node_port = node_info['node_port']
        if block_port_by_node_name(node, str(node_port), ssh_config_file):
            blocked_ports[node] = node_port
            blocked += 1
        tried_to_block += 1

    logger.debug("blocked: %s -- count: %s -- tried_to_block: %s -- " \
                 "len-aliases: %s", blocked, count, tried_to_block,
                 len(selected))

    # Write out the block_node_port_random file to the temp output_dir created
    # for this experiment
    with open(join(output_dir, "block_node_port_random"), "w") as f:
        f.write(json.dumps(blocked_ports))

    if blocked < int(count):
        return False

    return True


def unblocked_nodes_are_caught_up(genesis_file: str,
    transactions: Union[str,int] = None,
    pause_before_synced_check: Union[str,int] = None, best_effort: bool = True,
    did: str = DEFAULT_CHAOS_DID, seed: str = DEFAULT_CHAOS_SEED,
    wallet_name: str = DEFAULT_CHAOS_WALLET_NAME,
    wallet_key: str = DEFAULT_CHAOS_WALLET_KEY, pool: str = DEFAULT_CHAOS_POOL,
    ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Check if unblocked nodes have completed catchup.

    State file "block_node_port_random" located in the chaos temp dir (see
    get_chaos_temp_dir for details) is shared with the following functions
    block_node_port_random
    unblock_node_port_random
    unblocked_nodes_are_caught_up

    Because the aforementioned functions share a state file, they are intended
    to be used together. The typical/suggested workflow would be:

    1. Block the node port on some nodes (block_node_port_random)
    2. Optionally do something while node ports are blocked (i.e. generate load)
    3. Unblock node port on the set of nodes selected in step 1 above.
    4. Optionally do something while nodes are catching up.
    5. Check if nodes unblocked in step 3 above are caught up.

    :param genesis_file: The relative or absolute path to a genesis file.
        Required.
    :type genesis_file: str
    :param transactions: Expected number of transactions on the domain ledger
        after catchup has completed.
        Optional. (Default: None)
    :type transactions: Union[str,int]
    :param pause_before_synced_check: Seconds to pause before checking if a node
        is synced.
        Optional. (Default: None)
    :type pause_before_synced_check: Union[str,int]
    :param best_effort: Check if unblocked nodes are caught up without failing.
        For example, do not fail if the block_node_port_random state file does
        not exist.
        Optional. (Default: True)
    :type best_effort: bool
    :param did: A steward or trustee DID. A did OR a seed is required, but not
        both. The did will be used if both are given. Needed to get validator
        info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_DID)
    :type did: str
    :param seed : A steward or trustee seed. A did OR a seed is required, but
        not both. The did will be used if both are given. Needed to get
        validator info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SEED)
    :type seed: str
    :param wallet_name: The name of the wallet to use when getting validator
        info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_WALLET_NAME)
    :type wallet_name: str
    :param wallet_key: The key to use when opening the wallet designated by
        wallet_name.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_WALLET_KEY)
    :type wallet_key: str
    :param pool: The pool to connect to when getting validator info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_POOL)
    :type pool: str
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
    """
    # TODO: Use the traffic shaper tool Kelly is using.
    # http://www.uponmyshoulder.com/blog/2013/simulating-bad-network-conditions-on-linux/
    #
    # This function assumes that block_node_port_random has been called and a
    # "block_node_port_random" file has been created in a temporary directory
    # created using rules defined by get_chaos_temp_dir()
    output_dir = get_chaos_temp_dir()
    blocked_ports = {}
    try:
        with open(join(output_dir, "block_node_port_random"), "r") as f:
            blocked_ports = json.load(f)
    except Exception as e:
        # Do not fail on exceptions like FileNotFoundError if best_effort is
        # True
        if best_effort:
            return True
        else:
            raise e

    selected = blocked_ports.keys()

    # Only check if resurrected nodes are caught up if both a pause and number
    # of transactions are given.
    if pause_before_synced_check and transactions:
        logger.debug("Pausing %s seconds before checking if unblocked nodes " \
                     "are synced...", pause_before_synced_check)
        # TODO: Use a count down timer? May be nice for those who are running
        #       experiments manually.
        sleep(int(pause_before_synced_check))
        logger.debug("Checking if unblocked nodes are synced and report %s " \
                     "transactions...", transactions)
        return nodes_are_caught_up(selected, genesis_file, transactions,
                                   did=did, seed=seed, wallet_name=wallet_name,
                                   wallet_key=wallet_key, pool=pool,
                                   ssh_config_file=ssh_config_file)
    return True


def unblock_node_port_random(genesis_file: str,
    transactions: Union[str,int] = None,
    pause_before_synced_check: Union[str,int] = None, best_effort: bool = True,
    did: str = DEFAULT_CHAOS_DID, seed: str = DEFAULT_CHAOS_SEED,
    wallet_name: str = DEFAULT_CHAOS_WALLET_NAME,
    wallet_key: str = DEFAULT_CHAOS_WALLET_KEY, pool: str = DEFAULT_CHAOS_POOL,
    ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Unblock nodes randomly selected by calling block_node_port_random

    State file "block_node_port_random" located in the chaos temp dir (see
    get_chaos_temp_dir for details) is shared with the following functions
    block_node_port_random
    unblock_node_port_random
    unblocked_nodes_are_caught_up

    Because the aforementioned functions share a state file, they are intended
    to be used together. The typical/suggested workflow would be:

    1. Block the node port on some nodes (block_node_port_random)
    2. Optionally do something while node ports are blocked (i.e. generate load)
    3. Unblock node port on the set of nodes selected in step 1 above.
    4. Optionally do something while nodes are catching up.
    5. Check if nodes unblocked in step 3 above are caught up.

    :param genesis_file: The relative or absolute path to a genesis file.
        Required.
    :type genesis_file: str
    :param transactions: Expected number of transactions on the domain ledger
        after catchup has completed.
        Optional. (Default: None)
    :type transactions: Union[str,int]
    :param pause_before_synced_check: Seconds to pause before checking if a node
        is synced.
        Optional. (Default: None)
    :type pause_before_synced_check: Union[str,int]
    :param best_effort: Attempt to unblock ports blocked when calling
        block_node_port_random. Do not fail if the block_node_port_random state
        file does not exist, if an error/exception is encountered while
        unblocking a node port on any of the nodes, or if fewer than expected
        nodes were unblocked.
        Optional. (Default: True)
    :type best_effort: bool
    :param did: A steward or trustee DID. A did OR a seed is required, but not
        both. The did will be used if both are given. Needed to get validator
        info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_DID)
    :type did: str
    :param seed : A steward or trustee seed. A did OR a seed is required, but
        not both. The did will be used if both are given. Needed to get
        validator info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SEED)
    :type seed: str
    :param wallet_name: The name of the wallet to use when getting validator
        info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_WALLET_NAME)
    :type wallet_name: str
    :param wallet_key: The key to use when opening the wallet designated by
        wallet_name.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_WALLET_KEY)
    :type wallet_key: str
    :param pool: The pool to connect to when getting validator info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_POOL)
    :type pool: str
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
    """

    # TODO: Use the traffic shaper tool Kelly is using.
    # http://www.uponmyshoulder.com/blog/2013/simulating-bad-network-conditions-on-linux/
    #
    # This function assumes that block_node_port_random has been called and a
    # "block_node_port_random" file has been created in a temporary directory
    # created using rules defined by get_chaos_temp_dir()
    output_dir = get_chaos_temp_dir()
    blocked_ports = {}
    try:
        with open(join(output_dir, "block_node_port_random"), "r") as f:
            blocked_ports = json.load(f)
    except Exception as e:
        # Do not fail on exceptions like FileNotFoundError if best_effort is
        # True
        if best_effort:
            return True
        else:
            raise e

    selected = blocked_ports.keys()
    unblocked = 0
    tried_to_unblock = 0
    # Keep track of nodes/ports that could not be unblocked either by the
    # experiment's method or rollback segments and write it back to
    # block_node_port_random in the experiement's temp directory
    still_blocked_ports = {}
    for node in selected:
        logger.debug("node alias to unblock: %s", node)
        try:
            if unblock_port_by_node_name(node, str(blocked_ports[node]),
                                         ssh_config_file):
                unblocked += 1
            else:
                still_blocked_ports[node] = blocked_ports[node]
        except Exception as e:
            if best_effort:
                pass
        tried_to_unblock += 1

    logger.debug("unblocked: %s -- tried_to_unblock: %s -- len-aliases: %s",
                 unblocked, tried_to_unblock, len(selected))
    if not best_effort and unblocked < len(selected):
        return False

    # Only check if resurrected nodes are caught up if both a pause and number
    # of transactions are given.
    if pause_before_synced_check and transactions:
        logger.debug("Pausing %s seconds before checking if unblocked nodes " \
                     "are synced...", pause_before_synced_check)
        # TODO: Use a count down timer? May be nice for those who are running
        #       experiments manually.
        sleep(int(pause_before_synced_check))
        logger.debug("Checking if unblocked nodes are synced and report %s " \
                     "transactions...", transactions)
        return unblocked_nodes_are_caught_up(genesis_file, transactions, did,
                                             seed, wallet_name, wallet_key,
                                             pool, ssh_config_file)
    return True


def kill_random_nodes(genesis_file: str, count = Union[str,int],
    ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Randomly select and kill the indy-node process on a given number of nodes.

    State file "nodes_random" located in the chaos temp dir (see
    get_chaos_temp_dir for details) is shared with the following functions
    kill_random_nodes
    ressurect_random_nodes
    nodes_are_caught_up

    Because the aforementioned functions share a state file, they are intended
    to be used together. The typical/suggested workflow would be:

    1. Randomly select and kill the indy-node process on a given number of nodes
       (kill_random_nodes)
    2. Optionally do something while nodes are dead (i.e. generate load)
    3. Resurrect the set of nodes selected in step 1 above.
    4. Optionally do something while nodes are catching up.
    5. Check if nodes resurrected in step 3 above are caught up.
       (nodes_are_caught_up)

    :param genesis_file: The relative or absolute path to a genesis file.
        Required.
    :type genesis_file: str
    :param count: The number of nodes to kill. If the count exceeds the number
        of nodes defined in the genesis file, all nodes will be killed.
        Required.
    :type count: Union[str,int]
    :param pause_before_synced_check: Seconds to pause before checking if a node
        is synced.
        Optional. (Default: None)
    :type pause_before_synced_check: Union[str,int]
    :param best_effort: Attempt to unblock ports blocked when calling
        block_node_port_random. Do not fail if the block_node_port_random state
        file does not exist, if an error/exception is encountered while
        unblocking a node port on any of the nodes, or if fewer than expected
        nodes were unblocked.
        Optional. (Default: True)
    :type best_effort: bool
    :param did: A steward or trustee DID. A did OR a seed is required, but not
        both. The did will be used if both are given. Needed to get validator
        info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_DID)
    :type did: str
    :param seed : A steward or trustee seed. A did OR a seed is required, but
        not both. The did will be used if both are given. Needed to get
        validator info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SEED)
    :type seed: str
    :param wallet_name: The name of the wallet to use when getting validator
        info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_WALLET_NAME)
    :type wallet_name: str
    :param wallet_key: The key to use when opening the wallet designated by
        wallet_name.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_WALLET_KEY)
    :type wallet_key: str
    :param pool: The pool to connect to when getting validator info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_POOL)
    :type pool: str
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
    """
    selected = get_random_nodes(genesis_file, count)
    tried_to_kill = 0
    are_dead = 0
    number_of_aliases = len(selected)
    for node in selected:
        logger.debug("node alias to kill: %s", node)
        if stop_by_node_name(node, ssh_config_file):
            are_dead += 1
        tried_to_kill += 1

    logger.debug("are_dead: %s -- count: %s -- tried_to_kill: %s -- " \
                 "len-aliases: %s", are_dead, count, tried_to_kill,
                 number_of_aliases)
    if are_dead < int(count):
        return False

    output_dir = get_chaos_temp_dir()
    # Write out the killed nodes list to the temp output_dir created for this
    # experiment
    with open(join(output_dir, "nodes_random"), "w") as f:
        f.write(json.dumps(selected))

    return True


def resurrect_random_nodes(genesis_file: str,
    transactions: Union[str,int] = None,
    pause_before_synced_check: Union[str,int] = None, best_effort: bool = True,
    did: str = DEFAULT_CHAOS_DID, seed: str = DEFAULT_CHAOS_SEED,
    wallet_name: str = DEFAULT_CHAOS_WALLET_NAME,
    wallet_key: str = DEFAULT_CHAOS_WALLET_KEY, pool: str = DEFAULT_CHAOS_POOL,
    ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Start the indy-node process on nodes that were killed by calling
    kill_random_nodes.

    State file "nodes_random" located in the chaos temp dir (see
    get_chaos_temp_dir for details) is shared with the following functions
    kill_random_nodes
    ressurect_random_nodes
    nodes_are_caught_up

    Because the aforementioned functions share a state file, they are intended
    to be used together. The typical/suggested workflow would be:

    1. Randomly select and kill the indy-node process on a given number of nodes
       (kill_random_nodes)
    2. Optionally do something while nodes are dead (i.e. generate load)
    3. Resurrect the set of nodes selected in step 1 above.
    4. Optionally do something while nodes are catching up.
    5. Check if nodes resurrected in step 3 above are caught up.
       (nodes_are_caught_up)

    :param genesis_file: The relative or absolute path to a genesis file.
        Required.
    :type genesis_file: str
    :param transactions: Expected number of transactions on the domain ledger
        after catchup has completed.
        Optional. (Default: None)
    :type transactions: Union[str,int]
    :param pause_before_synced_check: Seconds to pause before checking if a node
        is synced.
        Optional. (Default: None)
    :type pause_before_synced_check: Union[str,int]
    :param best_effort: Attempt to unblock ports blocked when calling
        block_node_port_random. Do not fail if the block_node_port_random state
        file does not exist, if an error/exception is encountered while
        unblocking a node port on any of the nodes, or if fewer than expected
        nodes were unblocked.
        Optional. (Default: True)
    :type best_effort: bool
    :param did: A steward or trustee DID. A did OR a seed is required, but not
        both. The did will be used if both are given. Needed to get validator
        info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_DID)
    :type did: str
    :param seed : A steward or trustee seed. A did OR a seed is required, but
        not both. The did will be used if both are given. Needed to get
        validator info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SEED)
    :type seed: str
    :param wallet_name: The name of the wallet to use when getting validator
        info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_WALLET_NAME)
    :type wallet_name: str
    :param wallet_key: The key to use when opening the wallet designated by
        wallet_name.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_WALLET_KEY)
    :type wallet_key: str
    :param pool: The pool to connect to when getting validator info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_POOL)
    :type pool: str
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
    """
    # This function assumes that kill_random_nodes has been called and a
    # "nodes_random" file has been created in a temporary directory
    # created using rules defined by get_chaos_temp_dir()
    output_dir = get_chaos_temp_dir()
    selected = []
    try:
        with open(join(output_dir, "nodes_random"), "r") as f:
            selected = json.load(f)
    except Exception as e:
        # Do not fail on exceptions like FileNotFoundError if best_effort is
        # True
        if best_effort:
            return True
        else:
            raise e

    resurrected = 0
    tried_to_resurrect = 0
    # Keep track of nodes/ports that could not be resurrected either by the
    # experiment's method or rollback segments and write it back to
    # nodes_random in the experiement's temp directory
    still_killed_nodes = []
    for node in selected:
        logger.debug("node alias to resurrect: %s", node)
        try:
            if start_by_node_name(node, ssh_config_file):
                resurrected += 1
            else:
                still_killed_nodes.append(node)
        except Exception as e:
            if best_effort:
                pass
        tried_to_resurrect += 1

    logger.debug("resurrected: %s -- tried_to_resurrect: %s -- len-aliases: %s",
                 resurrected, tried_to_resurrect, len(selected))
    if not best_effort and resurrected < len(selected):
        return False

    # Write out the killed nodes list file to the temp output_dir created
    # for this experiment. Doing so allows resurrect_random_nodes to be called
    # in the rollback segment of an experiment w/o causing problems
    with open(join(output_dir, "nodes_random"), "w") as f:
        f.write(json.dumps(still_killed_nodes))

    # Only check if resurrected nodes are caught up if both a pause and number
    # of transactions are given.
    if pause_before_synced_check and transactions:
        logger.debug("Pausing %s seconds before checking if resurrected nodes" \
                     " are synced...", pause_before_synced_check)
        # TODO: Use a count down timer? May be nice for those who are running
        #       experiments manually.
        sleep(int(pause_before_synced_check))
        logger.debug("Checking if resurrected nodes are synced and report %s " \
                     "transactions...", transactions)
        return nodes_are_caught_up(selected, genesis_file, transactions,
                                   did=did, seed=seed, wallet_name=wallet_name,
                                   wallet_key=wallet_key, pool=pool,
                                   ssh_config_file=ssh_config_file)
    return True


def nodes_are_caught_up(nodes: List[str], genesis_file: str,
    transactions: Union[str,int] = None, did: str = DEFAULT_CHAOS_DID,
    seed: str = DEFAULT_CHAOS_SEED,
    wallet_name: str = DEFAULT_CHAOS_WALLET_NAME,
    wallet_key: str = DEFAULT_CHAOS_WALLET_KEY, pool: str = DEFAULT_CHAOS_POOL,
    ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Check if nodes resurrected by calling resurrect_random_nodes are caught up.

    State file "nodes_random" located in the chaos temp dir (see
    get_chaos_temp_dir for details) is shared with the following functions
    kill_random_nodes
    ressurect_random_nodes
    nodes_are_caught_up

    Because the aforementioned functions share a state file, they are intended
    to be used together. The typical/suggested workflow would be:

    1. Randomly select and kill the indy-node process on a given number of nodes
       (kill_random_nodes)
    2. Optionally do something while nodes are dead (i.e. generate load)
    3. Resurrect the set of nodes selected in step 1 above.
    4. Optionally do something while nodes are catching up.
    5. Check if nodes resurrected in step 3 above are caught up.
       (nodes_are_caught_up)

    :param nodes: The list of node names/aliases to check
    :type nodes: List[str]
    :param genesis_file: The relative or absolute path to a genesis file.
        Required.
    :type genesis_file: str
    :param transactions: Expected number of transactions on the domain ledger
        after catchup has completed.
        Optional. (Default: None)
    :type transactions: Union[str,int]
    :param did: A steward or trustee DID. A did OR a seed is required, but not
        both. The did will be used if both are given. Needed to get validator
        info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_DID)
    :type did: str
    :param seed : A steward or trustee seed. A did OR a seed is required, but
        not both. The did will be used if both are given. Needed to get
        validator info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SEED)
    :type seed: str
    :param wallet_name: The name of the wallet to use when getting validator
        info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_WALLET_NAME)
    :type wallet_name: str
    :param wallet_key: The key to use when opening the wallet designated by
        wallet_name.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_WALLET_KEY)
    :type wallet_key: str
    :param pool: The pool to connect to when getting validator info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_POOL)
    :type pool: str
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
    """
    # TODO: add support for all ledgers, not just domain ledger.
    #
    # This function assumes that kill_random_nodes has been called and a
    # "nodes_random" file has been created in a temporary directory
    # created using rules defined by get_chaos_temp_dir()
    # 1. Get validator info from all nodes
    get_validator_info(genesis_file, did=did, seed=seed,
                       wallet_name=wallet_name, wallet_key=wallet_key,
                       pool=pool, ssh_config_file=ssh_config_file)
    output_dir = get_chaos_temp_dir()

    matching = []
    not_matching = {}
    for alias in nodes:
        logger.debug("Checking if node %s has %s catchup transactions", alias,
                     transactions)
        validator_info = join(output_dir, "{}-validator-info".format(alias))
        try:
            with open(validator_info, 'r') as f:
                node_info = json.load(f)

            # Get the number of transactions added during catchup
            txns_in_catchup = None
            # Get the catchup status
            catchup_status = None
            if 'data' in node_info:
                # Shorten things to less than 80 characters per line
                data_node_info = node_info['data']['Node_info']
                catchup_status = data_node_info['Catchup_status']
                txns_in_catchup = catchup_status['Number_txns_in_catchup']
            else:
                # Shorten things to less than 80 characters per line
                catchup_status = node_info['Node_info']['Catchup_status']
                txns_in_catchup = catchup_status['Number_txns_in_catchup']
            # Get the number of catchup transactions
            catchup_transactions = txns_in_catchup['1']
            # Get the domain ledger status
            ledger_status = catchup_status['Ledger_statuses']['1']
        except FileNotFoundError:
            logger.info("Setting number of catchup transactions to Unknown " \
                        "for alias {}".format(alias))
            catchup_transactions = "Unknown"
            logger.info("Setting ledger status to Unknown for alias {}".format(
                        alias))
            ledger_status = "Unknown"
        except Exception as e:
            logger.error("Failed to load validator info for alias %s", alias)
            logger.exception(e)
            return False

        logger.info("%s's ledger status in catchup is %s", alias, ledger_status)
        logger.info("%s's number of transactions in catchup is %s", alias,
                    catchup_transactions)

        transaction_counts = transactions.split(" to ")
        transaction_counts_len = len(transaction_counts)
        if (ledger_status == 'synced' and
               catchup_transactions >= int(transaction_counts[0]) and
               catchup_transactions <= int(transaction_counts[-1])):
            matching.append(alias)
        else:
            not_matching[alias] = catchup_transactions

    if len(not_matching.keys()) != 0:
        for node in not_matching.keys():
            logger.error("Node %s failed to catchup. Reported %s " \
                         "transactions. Should have been %s", node,
                         str(catchup_transactions), transactions)
            logger.info("%s's number of transactions in catchup is %s", alias,
                        catchup_transactions)
        return False

    return True


def ensure_nodes_up(genesis_file: str, count = Union[str,int],
    ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Ensure at least a given number of nodes are up.

    True is returned if at least 'count' number of nodes are started. Otherwise,
    False is returned. For example, if the count is greater than the number of
    nodes defined in the genesis file, ensure_nodes_up will return False.

    :param genesis_file: The relative or absolute path to a genesis file.
        Required.
    :type genesis_file: str
    :param count: Number of nodes on which to ensure the indy-node service is
        running.
        Required.
    :type count: Union[str,int]
    :return: bool
    """
    logger.debug("genesis_file: %s -- count: %s -- ssh_config_file: %s",
                 genesis_file, count, ssh_config_file)
    # 1. Get all node aliases
    aliases = get_aliases(genesis_file)
    logger.debug(aliases)

    executor = FabricExecutor(ssh_config_file=expanduser(ssh_config_file))

    # 2. Start 'count' nodes. It is okay to count a node if the service is
    #    already alive/started
    tried_to_start = 0
    are_alive = 0
    number_of_aliases = len(aliases)
    while are_alive < int(count) and tried_to_start < number_of_aliases:
        node = random.choice(aliases)
        aliases.remove(node)
        logger.debug("node alias to start: %s", node)
        if start_node(node, ssh_config_file):
            are_alive += 1
        tried_to_start += 1

    logger.debug("are_alive: %s -- count: %s -- tried_to_start: %s -- " \
                 "len-aliases: %s", are_alive, count, tried_to_start,
                 number_of_aliases)
    if are_alive < int(count):
        return False

    return True


def set_node_services_from_cli(genesis_file: str, alias: str, alias_did: str,
    did: str = DEFAULT_CHAOS_DID, seed: str = DEFAULT_CHAOS_SEED,
    services: str = DEFAULT_CHAOS_NODE_SERVICES,
    wallet_name: str = DEFAULT_CHAOS_WALLET_NAME,
    wallet_key: str = DEFAULT_CHAOS_WALLET_KEY, pool: str = DEFAULT_CHAOS_POOL,
    timeout: Union[str,int] = DEFAULT_CHAOS_LEDGER_TRANSACTION_TIMEOUT,
    ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Set a node's 'services' attribute using indy-cli

    :param genesis_file: The relative or absolute path to a genesis file.
        Required.
    :type genesis_file: str
    :param alias: The node name/alias for which to set the 'services' attribute
    :type alias: str
    :param alias_did: The 'dest' did associated with the alias/node
        Required.
    :type did: str
    :param did: A steward or trustee DID. A did OR a seed is required, but not
        both. The did will be used if both are given. Needed to get validator
        info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_DID)
    :type did: str
    :param seed : A steward or trustee seed. A did OR a seed is required, but
        not both. The did will be used if both are given. Needed to get
        validator info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SEED)
    :type seed: str
    :param services: One of the following: "VALIDATOR", "OBSERVER", ""
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_NODE_SERVICES)
    :type services: str
    :param wallet_name: The name of the wallet to use when getting validator
        info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_WALLET_NAME)
    :type wallet_name: str
    :param wallet_key: The key to use when opening the wallet designated by
        wallet_name.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_WALLET_KEY)
    :type wallet_key: str
    :param pool: The pool to connect to when getting validator info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_POOL)
    :type pool: str
    :param timeout: How long indy-cli can take to perform the operation before
        timing out.
        Optional.
        (Default: chaosindy.common.DEFAULT_CHAOS_LEDGER_TRANSACTION_TIMEOUT)
    :type timeout: Union[str,int]
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
    """

    # TODO: Decide if this should be a send_node_transaction abstraction instead
    #       of specifically for changing a nodes "services" attribute.
    '''
     The following steps are required to configure the client node where
     indy-cli will be used to a node
     (i.e. common.StopStrategy.DEMOTE is used in experiment):

     1. Install indy-cli
        `$ apt-get install indy-cli`
     2. Start indy-cli
        `$ indy-cli`
        `indy>`
     3. Create pool
        NOTE: Pool name will be a parameter for the experiments that need
              to demote a node
        `indy> pool create pool1 gen_txn_file=/home/ubuntu/pool_transactions_genesis`
     4. Create wallet
        NOTE: Wallet name and optional key will be parameters for the
              experiments that need to demote a node
        `indy> wallet create wallet1 key=key1`
     5. Open wallet created in the previous step
        `indy> wallet open wallet1 key=key1`
        `wallet(wallet1):indy>`
     6. Create did with a Trustee seed
        NOTE: did will be a parameter for the experiments that need to demote
              a node. Only Trustees and Stewards can demote a node.
        `wallet(wallet1):indy> did new seed=000000000000000000000000Trustee1`
     7. Open pool created in previous step
        `wallet(wallet1):indy> pool connect pool1`
        `pool(pool1):wallet(wallet1):indy>`
     8. Verify the did created with the Trustee seed can retrieve validator info.
        Validator info is only available to Trustees and Stewards. A test to see
        if you can get validator info effectively tests if the wallet you just
        set up will be adequate to demote/promote a node.
        `pool(pool1):wallet(wallet1):indy> did use V4SGRU86Z58d6TV7PBUe6f`
        `pool(pool1):wallet(wallet1):did(V4S...e6f):indy>`
        `pool(pool1):wallet(wallet1):did(V4S...e6f):indy> ledger get-validator-info`
     To simplify the call to this function, perform a best-effort creation of
     pool, wallet, and did. Doing so eliminates the need to manually set them
     up prior to running experiments. Just pass the appropriate parameters to
     the experiment via the environment and they will be created the first time
     the experiment is run. All subsequent runs will generate a warning/error
     stating they already exist. Not a problem, because we are ignoring the
     error/warning. Note that indy-cli exists with a return code of 0 even if
     one of the commands in the file passed as a parameter fails.
    '''
    output_dir = get_chaos_temp_dir()

    # Pool creation
    indy_cli_command_batch = join(output_dir, "indy-cli-create-pool.in")
    with open(indy_cli_command_batch, "w") as f:
        f.write("pool create {} gen_txn_file={}\n".format(pool, genesis_file))
        f.write("exit")
    create_pool = subprocess.check_output(["indy-cli", indy_cli_command_batch],
        stderr=subprocess.STDOUT, shell=False)

    # Wallet creation
    indy_cli_command_batch = join(output_dir, "indy-cli-create-wallet.in")
    with open(indy_cli_command_batch, "w") as f:
        if wallet_key:
          f.write("wallet create {} key={}\n".format(wallet_name, wallet_key))
        else:
          f.write("wallet create {} key\n".format(wallet_name))
        f.write("exit")
    create_wallet = subprocess.check_output(
        ["indy-cli", indy_cli_command_batch], stderr=subprocess.STDOUT,
        shell=False)

    # DID creation
    if seed:
        indy_cli_command_batch = join(output_dir, "indy-cli-create-did.in")
        with open(indy_cli_command_batch, "w") as f:
            if wallet_key:
              f.write("wallet open {} key={}\n".format(wallet_name, wallet_key))
            else:
              f.write("wallet open {} key\n".format(wallet_name))
            f.write("did new seed={}\n".format(seed))
            f.write("exit")
        create_did = subprocess.check_output(
            ["indy-cli", indy_cli_command_batch], stderr=subprocess.STDOUT,
            shell=False)

    # Get the node's DID from the genesis transaction file. The DID can be found
    # in the txn.data.dest attribute where txn.data.data.alias == alias passed
    # in.
    indy_cli_command_batch = join(output_dir, "indy-cli-set-node-services.in")
    with open(indy_cli_command_batch, "w") as f:
        if wallet_key:
          f.write("wallet open {} key={}\n".format(wallet_name, wallet_key))
        else:
          f.write("wallet open {} key\n".format(wallet_name))
        f.write("did use {}\n".format(did))
        f.write("pool connect {}\n".format(pool))
        f.write("ledger node target={} alias={} services={}\n".format(alias_did,
                alias, services))
        f.write("exit")
    demote_node = subprocess.check_output(["indy-cli", indy_cli_command_batch],
        stderr=subprocess.STDOUT, timeout=int(timeout), shell=False)

    return True


def set_services_by_node_name(genesis_file: str, alias: str,
    services: str = DEFAULT_CHAOS_NODE_SERVICES, did: str = DEFAULT_CHAOS_DID,
    seed: str = DEFAULT_CHAOS_SEED,
    wallet_name: str = DEFAULT_CHAOS_WALLET_NAME,
    wallet_key: str = DEFAULT_CHAOS_WALLET_KEY, pool: str = DEFAULT_CHAOS_POOL,
    timeout: Union[str,int] = DEFAULT_CHAOS_LEDGER_TRANSACTION_TIMEOUT,
    ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Change a node's services

    :param genesis_file: The relative or absolute path to a genesis file.
        Required.
    :type genesis_file: str
    :param alias: The node name/alias for which to set the 'services' attribute
    :type alias: str
    :param services: The node's services. Must be one of the following:
        "VALIDATOR", "OBSERVER", ""
    :type services: str
    :param did: A steward or trustee DID. A did OR a seed is required, but not
        both. The did will be used if both are given. Needed to get validator
        info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_DID)
    :type did: str
    :param services: One of the following: "VALIDATOR", "OBSERVER", ""
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_NODE_SERVICES)
    :type services: str
    :param seed : A steward or trustee seed. A did OR a seed is required, but
        not both. The did will be used if both are given. Needed to get
        validator info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SEED)
    :type seed: str
    :param wallet_name: The name of the wallet to use when getting validator
        info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_WALLET_NAME)
    :type wallet_name: str
    :param wallet_key: The key to use when opening the wallet designated by
        wallet_name.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_WALLET_KEY)
    :type wallet_key: str
    :param pool: The pool to connect to when getting validator info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_POOL)
    :type pool: str
    :param timeout: How long indy-cli can take to perform the operation before
        timing out.
        Optional.
        (Default: chaosindy.common.DEFAULT_CHAOS_LEDGER_TRANSACTION_TIMEOUT)
    :type timeout: Union[str,int]
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
    """
    # NOTE: Possible pure-python solution: https://github.com/hyperledger/indy-plenum/blob/62c8f47c20a1d204f2e90bb85f84cbf02c2b0b48/plenum/test/pool_transactions/helper.py#L413-L430
    logger.debug("Setting %s's services to >%s<", alias, services)
    logger.debug("Get %s's DID from genesis_file %s", alias, genesis_file)
    node_genesis_json = get_info_by_node_name(genesis_file, alias,
                                              path="txn.data")
    timeout = int(timeout)
    alias_did = node_genesis_json['dest']
    logger.debug("%s's did is %s", alias, alias_did)
    logger.debug("timeout set to %d", timeout)
    return set_node_services_from_cli(genesis_file, alias, alias_did=alias_did,
                                      services=services, did=did, seed=seed,
                                      wallet_name=wallet_name,
                                      wallet_key=wallet_key, pool=pool,
                                      timeout=timeout,
                                      ssh_config_file=ssh_config_file)


def demote_by_node_name(genesis_file: str, alias: str,
    services: str = DEFAULT_CHAOS_NODE_SERVICES, did: str = DEFAULT_CHAOS_DID,
    seed: str = DEFAULT_CHAOS_SEED,
    wallet_name: str = DEFAULT_CHAOS_WALLET_NAME,
    wallet_key: str = DEFAULT_CHAOS_WALLET_KEY, pool: str = DEFAULT_CHAOS_POOL,
    timeout: Union[str,int] = DEFAULT_CHAOS_LEDGER_TRANSACTION_TIMEOUT,
    ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Demote a node by setting it's "services" attribute to an empty list/string.

    demote_by_node_name and promote_by_node_name are abstractions on top of
    set_services_by_node_name

    :param genesis_file: The relative or absolute path to a genesis file.
        Required.
    :type genesis_file: str
    :param alias: The node name/alias for which to set the 'services' attribute
    :type alias: str
    :param services: One of the following: "VALIDATOR", "OBSERVER", ""
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_NODE_SERVICES)
    :type services: str
    :param did: A steward or trustee DID. A did OR a seed is required, but not
        both. The did will be used if both are given. Needed to get validator
        info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_DID)
    :type did: str
    :param seed : A steward or trustee seed. A did OR a seed is required, but
        not both. The did will be used if both are given. Needed to get
        validator info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SEED)
    :type seed: str
    :param wallet_name: The name of the wallet to use when getting validator
        info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_WALLET_NAME)
    :type wallet_name: str
    :param wallet_key: The key to use when opening the wallet designated by
        wallet_name.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_WALLET_KEY)
    :type wallet_key: str
    :param pool: The pool to connect to when getting validator info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_POOL)
    :type pool: str
    :param timeout: How long indy-cli can take to perform the operation before
        timing out.
        Optional.
        (Default: chaosindy.common.DEFAULT_CHAOS_LEDGER_TRANSACTION_TIMEOUT)
    :type timeout: Union[str,int]
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
    """
    logger.debug("Demoting {}".format(alias))
    return set_services_by_node_name(genesis_file, alias, services="", did=did,
                                     seed=seed, wallet_name=wallet_name,
                                     wallet_key=wallet_key, pool=pool,
                                     timeout=timeout,
                                     ssh_config_file=ssh_config_file)


def restart_node(genesis_file: str, alias: str,
    timeout: Union[str,int] = DEFAULT_CHAOS_LEDGER_TRANSACTION_TIMEOUT,
    stop_strategy: int = StopStrategy.SERVICE.value,
    ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Restart a node

    :param genesis_file: The relative or absolute path to a genesis file.
        Required.
    :type genesis_file: str
    :param alias: The node name/alias for which to set the 'services' attribute
    :type alias: str
    :param timeout: How long to perform the operation before timing out.
        Optional.
        (Default: chaosindy.common.DEFAULT_CHAOS_LEDGER_TRANSACTION_TIMEOUT)
    :type timeout: Union[str,int]
    :param stop_strategy: A stop strategy defined by the
        chaosindy.common.StopStrategy enum. Examples include:
        StopStrategy.SERVICE - Stop the indy-node service (graceful)
        StopStrategy.PORT - Block the node port
        StopStrategy.DEMOTE - Demote the node
        StopStrategy.KILL - Kill the indy-node service (ungraceful)
    :type stop_strategy: int
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
    """
    logger.debug("Restarting {}".format(alias))
    config = {
      'stop_strategy': StopStrategy.SERVICE.value
    }

    status = stop_by_strategy(genesis_file, alias,
                              config.get('stop_strategy', None),
                              timeout=timeout, ssh_config_file=ssh_config_file)
    if status:
        status = start_by_strategy(genesis_file, alias, config, timeout=timeout,
                                   ssh_config_file=ssh_config_file)
        if not status:
            logger.error("Failed to start {}".format(alias))
    else:
        logger.error("Failed to stop {}".format(alias))

    return status


def promote_by_node_name(genesis_file: str, alias: str,
    services: str = DEFAULT_CHAOS_NODE_SERVICES,
    did: str = DEFAULT_CHAOS_DID,
    seed: str = DEFAULT_CHAOS_SEED,
    wallet_name: str = DEFAULT_CHAOS_WALLET_NAME,
    wallet_key: str = DEFAULT_CHAOS_WALLET_KEY, pool: str = DEFAULT_CHAOS_POOL,
    timeout: Union[str,int] = DEFAULT_CHAOS_LEDGER_TRANSACTION_TIMEOUT,
    ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Promote a node by setting it's "services" attribute to an empty
    list/string.

    promote_by_node_name and demote_by_node_name are abstractions on top of
    set_services_by_node_name

    :param genesis_file: The relative or absolute path to a genesis file.
        Required.
    :type genesis_file: str
    :param alias: The node name/alias for which to set the 'services' attribute
    :type alias: str
    :param did: A steward or trustee DID. A did OR a seed is required, but not
        both. The did will be used if both are given. Needed to get validator
        info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_DID)
    :type did: str
    :param seed : A steward or trustee seed. A did OR a seed is required, but
        not both. The did will be used if both are given. Needed to get
        validator info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SEED)
    :type seed: str
    :param services: One of the following: "VALIDATOR", "OBSERVER", ""
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_NODE_SERVICES)
    :type services: str
    :param wallet_name: The name of the wallet to use when getting validator
        info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_WALLET_NAME)
    :type wallet_name: str
    :param wallet_key: The key to use when opening the wallet designated by
        wallet_name.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_WALLET_KEY)
    :type wallet_key: str
    :param pool: The pool to connect to when getting validator info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_POOL)
    :type pool: str
    :param timeout: How long indy-cli can take to perform the operation before
        timing out.
        Optional.
        (Default: chaosindy.common.DEFAULT_CHAOS_LEDGER_TRANSACTION_TIMEOUT)
    :type timeout: Union[str,int]
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
    """
    logger.debug("Promoting {}".format(alias))
    status = set_services_by_node_name(genesis_file, alias,
                                       services="VALIDATOR",
                                       did=did, seed=seed,
                                       wallet_name=wallet_name,
                                       wallet_key=wallet_key, pool=pool,
                                       timeout=timeout,
                                       ssh_config_file=ssh_config_file)

    if status:
        logger.debug("Restart {}".format(alias))
        # Restart nodes that are promoted. Doing so triggers catchup. Otherwise
        # catch up will only occur "after 2 checkpoint generations are stashed"
        # (Nikita Spivachuk).
        # The following issue changed the node promotion workflow to require a
        # node restart: https://jira.hyperledger.org/browse/INDY-1297
        logger.debug("Sleeping 10 seconds between setting %s's services to" \
                     " 'VALIDATOR' and restarting it's indy-node service.",
                     alias)
        sleep(5)
        status = restart_node(genesis_file, alias, timeout=timeout,
                              ssh_config_file=ssh_config_file)
        if not status:
            logger.error("Failed to restart {}".format(alias))
    else:
        logger.error("Failed to promote {}".format(alias))

    return status


def stop_by_strategy(genesis_file: str, alias: str, stop_strategy: int,
    timeout: Union[str,int] = DEFAULT_CHAOS_LEDGER_TRANSACTION_TIMEOUT,
    ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> Union[bool,Dict[str,str]]:
    """
    Remove a node from participating in consensus

    Returns False if it fails. Otherwise, a dictionary containing information
    required at a later time to rollback changes. The caller is expected to
    perform a predicate check on the returned value.

    Call start_by_strategy to undo what is done by stop_by_strategy.

    :param genesis_file: The relative or absolute path to a genesis file.
        Required.
    :type genesis_file: str
    :param alias: The node name/alias for which to set the 'services' attribute
    :type alias: str
    :param stop_strategy: A stop strategy defined by the
        chaosindy.common.StopStrategy enum. Examples include:
        StopStrategy.SERVICE - Stop the indy-node service (graceful)
        StopStrategy.PORT - Block the node port
        StopStrategy.DEMOTE - Demote the node
        StopStrategy.KILL - Kill the indy-node service (ungraceful)
    :type stop_strategy: int
    :param timeout: How long to perform the operation before timing out.
        Optional.
        (Default: chaosindy.common.DEFAULT_CHAOS_LEDGER_TRANSACTION_TIMEOUT)
    :type timeout: Union[str,int]
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: Union[bool, Dict[str,str]]
    """
    output_dir = get_chaos_temp_dir()
    succeeded = False
    operation = "stop/block/demote/kill"
    details = {
        "stop_strategy": stop_strategy
    }
    if stop_strategy == StopStrategy.SERVICE.value:
        # "stop" indy-node service
        succeeded = stop_by_node_name(alias, timeout=timeout,
            ssh_config_file=ssh_config_file)
        operation = "stop"
    elif stop_strategy == StopStrategy.PORT.value:
        with open("{}/{}-validator-info".format(output_dir, alias), 'r') as vif:
            validator_info = json.load(vif)
            node_info = validator_info['Node_info']
            # "stop/block" inbound messages from clients and other nodes
            details['client_port'] = str(node_info['Client_port'])
            details['node_port'] = str(node_info['Node_port'])
            succeeded = block_port_by_node_name(alias, details['client_port'],
                ssh_config_file=ssh_config_file)
            succeeded = block_port_by_node_name(alias, details['node_port'],
                ssh_config_file=ssh_config_file)
        operation = "block"
    elif stop_strategy == StopStrategy.DEMOTE.value:
        # "stop" participating in consensus
        succeeded = demote_by_node_name(genesis_file, alias,
            timeout=timeout, ssh_config_file=ssh_config_file)
        operation = "demote"
    elif stop_strategy == StopStrategy.KILL.value:
        # "stop/kill" indy-node service
        succeeded = stop_by_node_name(alias, gracefully=False, force=True,
            timeout=timeout, ssh_config_file=ssh_config_file)
        operation = "kill"
    else:
        message = """Stop strategy %s not supported or not found. The following
                     operation are supported: %s"""
        logger.error(message, stop_strategy, operation)
        return False
    if not succeeded:
        message = """Failed to %s %s"""
        logger.error(message, operation, alias)
        return False
    return details

def start_by_strategy(genesis_file: str, alias: str,
    details: Dict[str,str],
    timeout: Union[str,int] = DEFAULT_CHAOS_LEDGER_TRANSACTION_TIMEOUT,
    ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Restore a node to participating in consensus

    start_by_strategy is intended to undo what was done by stop_by_strategy.
    See stop_by_stragegy.

    The strategy used when calling stop_by_stragey is expected to be used again
    when calling start_by_stragey in order to undo what what done by
    stop_by_strategy.

    Returns False if it fails. Otherwise, a dictionary containing information
    required at a later time to rollback changes. The caller is expected to
    perform a predicate check on the returned value.

    :param genesis_file: The relative or absolute path to a genesis file.
        Required.
    :type genesis_file: str
    :param alias: The node name/alias for which to set the 'services' attribute
    :type alias: str
    :param stop_strategy: A stop strategy defined by the
        chaosindy.common.StopStrategy enum. Examples include:
        StopStrategy.SERVICE - Stop the indy-node service (graceful)
        StopStrategy.PORT - Block the node port
        StopStrategy.DEMOTE - Demote the node
        StopStrategy.KILL - Kill the indy-node service (ungraceful)
    :type stop_strategy: int
    :param timeout: How long to perform the operation before timing out.
        Optional.
        (Default: chaosindy.common.DEFAULT_CHAOS_LEDGER_TRANSACTION_TIMEOUT)
    :type timeout: Union[str,int]
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
    """
    succeeded = False
    operation = "start/unblock/promote"
    stop_strategy = details.get('stop_strategy', None)
    if (stop_strategy == StopStrategy.SERVICE.value
        or stop_strategy == StopStrategy.KILL.value):
        succeeded = start_by_node_name(alias, ssh_config_file=ssh_config_file)
        operation = "start"
    elif stop_strategy == StopStrategy.PORT.value:
        client_port = details.get('client_port', None)
        node_port = details.get('node_port', None)
        if not (client_port or node_port):
            message ="""Missing client_port and/or node_port element in
                        stopped_nodes_file state file {} for {}"""
            logger.error(message.format(stopped_nodes_file, alias))
            return False
        client_port_unblocked = unblock_port_by_node_name(alias,
            client_port, ssh_config_file=ssh_config_file)
        node_port_unblocked = unblock_port_by_node_name(alias,
            node_port, ssh_config_file=ssh_config_file)
        succeeded = (client_port_unblocked and node_port_unblocked)
        operation = "unblock"
    elif stop_strategy == StopStrategy.DEMOTE.value:
        succeeded = promote_by_node_name(genesis_file, alias,
            timeout=timeout, ssh_config_file=ssh_config_file)
        operation = "promote"
    else:
        message = """Stop strategy %s not supported or not found."""
        logger.error(message, stop_strategy)
        return False
    if not succeeded:
        message = """Failed to %s %s"""
        logger.error(message, operation, backup_primary)
        return False
    return True


def get_primary(genesis_file: str,
                ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE,
                compile_stats: bool = True) -> str:
    """
    Return the alias of the primary from the 'primaries' state file.

    :param genesis_file: The relative or absolute path to a genesis file.
        Required.
    :type genesis_file: str
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :param compile_stats: Set to True to create/recreate the 'primaries' state
        file. Set to False if the last computed "current_primary" in the
        'primaries' state file is sufficient. get_primary MUST be called at
        least once with compile_stats=True before calling it with
        compile_stats=False. Otherwise, the 'primaries' state file will not
        exist, resulting in a stacktrace. By design (in context to chaos
        experiments), the stacktrace (File Not Found) tells you your experiment
        is not written correctly.
        Optional. (Default: True)
    :type compile_stats: bool
    :return: str

    """
    primary = None
    if compile_stats:
        detect_primary(genesis_file, ssh_config_file=ssh_config_file)

    output_dir = get_chaos_temp_dir()
    with open("{}/primaries".format(output_dir), 'r') as primaries:
        primary_dict = json.load(primaries)
    primary = primary_dict.get("current_primary", None)

    return primary


def stop_primary(genesis_file: str,
                 stop_strategy: int = StopStrategy.SERVICE.value,
                 ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Detect and stop the node playing the role of 'primary'
    Store the name/alias of the primary in a 'stopped_primary' state file
    (JSON doc) within the experiment's chaos temp dir.

    start_stopped_primary_after_view_change may be called after calling
    stop_primary if the desired result is to start the old primary after a view
    change has completed.

    start_stopped_primary may be called after calling stop_primary if the
    desired result is to start the old primary without considering the state of
    a viewchange.

    :param genesis_file: The relative or absolute path to a genesis file.
        Required.
    :type genesis_file: str
    :param stop_strategy: A stop strategy defined by the
        chaosindy.common.StopStrategy enum. Examples include:
        StopStrategy.SERVICE - Stop the indy-node service (graceful)
        StopStrategy.PORT - Block the node port
        StopStrategy.DEMOTE - Demote the node
        StopStrategy.KILL - Kill the indy-node service (ungraceful)
        Optional. (Default: chaosindy.common.StopStrategy.SERVICE.value)
    :type stop_strategy: int
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


def wait_for_view_change(genesis_file: str,
    previous_primary: str = None, max_checks_for_primary: int = 6,
    sleep_between_checks: int = 10,
    ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> int:
    """
    Wait until view change is complete.

    When the primary is not the previous_primary a viewchange has progressed far
    enough to achive consensus.

    :param genesis_file: The relative or absolute path to a genesis file.
        Required.
    :type genesis_file: str
    :param previous_primary: The previous known primary
        Optional. (Default: None)
    :type previous_primary: str
    :param max_checks_for_primary: How many times to poll validator info for
        primary information.
        Optional. (Default: 6)
    :type max_checks_for_primary: int
    :param sleep_between_checks: How long (in seconds) to pause/sleep between
        polling validator info.
        Optional. (Default: 10)
    :type sleep_between_checks: int
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: int
    """
    tries = 0
    while tries < max_checks_for_primary:
        current_primary = get_primary(genesis_file,
                                      ssh_config_file=ssh_config_file,
                                      compile_stats=True)
        logger.debug("Check %d of %d if view change is complete", tries,
                     max_checks_for_primary)
        logger.debug("Former primary: %s", previous_primary)
        logger.debug("Current primary: %s", current_primary)
        if current_primary and previous_primary != current_primary:
            logger.debug("View change detected!")
            break;
        else:
            logger.debug("View change not yet complete. Sleeping for {}" \
                         " seconds...".format(sleep_between_checks))
            sleep(sleep_between_checks)
            tries += 1
    return tries


def start_stopped_primary_after_view_change(genesis_file: str,
    max_checks_for_primary: int = 6, sleep_between_checks: int = 10,
    start_backup_primaries: bool = True,
    ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
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
      - If a "stopped_nodes" element exists in the JSON, and the
        start_backup_primaries kwarg is True, the stopped backup primaries
        should be started.

    :param genesis_file: The relative or absolute path to a genesis file.
        Required.
    :type genesis_file: str
    :param max_checks_for_primary: How many times to poll validator info for
        primary information.
        Optional. (Default: 6)
    :type max_checks_for_primary: int
    :param sleep_between_checks: How long (in seconds) to pause/sleep between
        polling validator info.
        Optional. (Default: 10)
    :type sleep_between_checks: int
    :param start_backup_primaries: If the state file indicates that backup
        primaries (replicas) have been stopped, should backup primaries be
        started?
        Optional. (Default: True)
    :type start_backup_primaries: bool
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
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
        tries = wait_for_view_change(genesis_file=genesis_file,
            previous_primary=stopped_primary,
            max_checks_for_primary=max_checks_for_primary,
            sleep_between_checks=sleep_between_checks,
            ssh_config_file=ssh_config_file)

        # Only start stopped primary and backup primaries if a viewchange
        # completed.
        if tries < max_checks_for_primary:
            # Start backup primaries?
            stopped_nodes = stopped_primary_dict.get(
                'stopped_nodes', None)
            if start_backup_primaries and stopped_nodes:
                for backup_primary in stopped_nodes:
                    started = start_by_strategy(genesis_file, backup_primary,
                        stopped_nodes[backup_primary],
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


def start_stopped_primary(genesis_file: str,
    start_backup_primaries: bool = True,
    ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Start the node stopped by a call to stop_primary. When the primary is
    stopped, the pool will perform a viewchange. This function starts the
    stopped_primary even if the viewchange is not complete.

    By default, if an experiment stops replica nodes (a.k.a. backup primaries),
    the stopped replicas will be started before the stopped primary is started.

    :param genesis_file: The relative or absolute path to a genesis file.
        Required.
    :type genesis_file: str
    :param start_backup_primaries: If the state file indicates that backup
        primaries (replicas) have been stopped, should backup primaries be
        started?
        Optional. (Default: True)
    :type start_backup_primaries: bool
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
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
        stopped_nodes = stopped_primary_dict.get(
            'stopped_nodes', None)
        if stopped_nodes:
            message = """Detected stopped backup primaries %s. Starting backup
                         primaries before starting stopped primary..."""
            for backup_primary in stopped_nodes:
                started = start_by_strategy(genesis_file, backup_primary,
                    stopped_nodes[backup_primary],
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


def stop_f_backup_primaries_before_primary(genesis_file: str,
    f: Union[str, int] = None, stop_strategy: int = StopStrategy.SERVICE.value,
    ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Stop a given number of backup primaries.

    When not given, f Defaults to the cluster's f_value from validator-info.

    Creates a state "stopped_primary" state file. The following functions also
    create a "stopped_primary" state file. Do not use both
    stop_f_backup_primaries_before_primary with any of the following in your
    experiments unless you refactor code to allow you to do so w/o causing
    undesired side-effects:

    stop_primary

    The following read data from the "stopped_primary" state file and may be
    useful in combination with stop_f_backup_primaries_before_primary:

    start_stopped_primary_after_view_change
    start_stopped_primary

    TODO: Add selection_strategy? selection_strategy - How to select which <f>
          backup primaries to stop. Options defined by SelectionStrategy in
          chaosindy.common
    TODO: Move to a chaosindy.actions.replica.py?
    TODO: Change state file from stopped_nodes to stopped_primary? If so,
          must change logic to read the file into a dict (default empty dict),
          add/update the dict, and write it out to disk. Overwriting the file
          will not work. Perhaps the common module can be enhanced to support
          get_state, set_state abstractions?

    :param genesis_file: The relative or absolute path to a genesis file.
        Required.
    :type genesis_file: str
    :param f: This is typically the number of nodes that can fail w/o losing
        consensus and can be found in validator-info. It is exposed as a
        parameter as a means for experimentation.
    :type f: Union[str,int]
    :param stop_strategy: A stop strategy defined by the
        chaosindy.common.StopStrategy enum. Examples include:
        StopStrategy.SERVICE - Stop the indy-node service (graceful)
        StopStrategy.PORT - Block the node port
        StopStrategy.DEMOTE - Demote the node
        StopStrategy.KILL - Kill the indy-node service (ungraceful)
        Optional. (Default: chaosindy.common.StopStrategy.SERVICE.value)
    :type stop_strategy: int
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
        with open("{}/{}-validator-info".format(output_dir, primary), 'r') as vif:
            validator_info = json.load(vif)
        # Stop up to f backup primaries
        # Set f if not defined
        if not f:
            f = validator_info['Pool_info']['f_value']

        backup_primaries = {}
        # No backup primaries are stopped when f == 1
        i = 1
        if int(f) > 1:
            # Starting at 1 and iterating up to, but not inclding f ensures we
            # do not fall out of concensus by shutting down too many nodes.
            node_info = validator_info['Node_info']
            replica_status = node_info['Replicas_status']
            for i in range(1, f):
                replica = replica_status["{}:{}".format(primary, i)]['Primary']
                replica = replica.split(":")[0]
                details = stop_by_strategy(genesis_file, replica, stop_strategy,
                    ssh_config_file=ssh_config_file)
                backup_primaries[replica] = details
        # Get the next expected primary
        next_primary = replica_status["{}:{}".format(primary, i+1)]['Primary']
        next_primary = next_primary.split(":")[0]

        # Stop the primary
        primary_details = stop_by_strategy(genesis_file, primary, stop_strategy,
            ssh_config_file=ssh_config_file)

        primary_data = {
            'stopped_primary': primary,
            'stopped_primary_details': primary_details,
            'stopped_nodes': backup_primaries,
            'next_primary': next_primary
        }
        with open("{}/stopped_primary".format(output_dir), 'w') as sp:
            sp.write(json.dumps(primary_data))
        return True
    return False

def stop_n_nodes(genesis_file: str, number_of_nodes: Union[str, int] = 1,
    selection_strategy: int = SelectionStrategy.FORWARD.value,
    stop_strategy: int = StopStrategy.SERVICE.value,
    include_primary: str = 'Yes',
    include_backup_primaries: str = 'Yes',
    include_other_nodes: str = 'Yes',
    max_checks_for_primary: Union[str,int] = 6,
    sleep_between_checks: Union[str,int] = 10,
    stop_node_timeout: Union[str,int] = DEFAULT_CHAOS_LEDGER_TRANSACTION_TIMEOUT,
    ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Stop a least one or more nodes

    TODO: Change state file from stopped_nodes to stopped_primary? If so,
          must change logic to read the file into a dict (default empty dict),
          add/update the dict, and write it out to disk. Overwriting the file
          will not work. Perhaps the common module can be enhanced to support
          get_state, set_state abstractions?

    Assumptions:
      - A pool of at least 4 nodes
      - The node list from which to select nodes using the given
        selection_strategy will be in the following order:
        - primary
        - backup primaries
        - all other nodes in the order they are listed in the genesis file

    :type genesis_file: str
    :param genesis_file: The relative or absolute path to a genesis file.
        Required.
    :type genesis_file: str
    :param number_of_nodes: How many nodes to stop.
        Optional. (Default: 1)
    :type number_of_nodes: Union[str,int]
    :param selection_strategy: A selection strategy defined by the
        chaosindy.common.SelectionStrategy enum.
        Examples include:
        SelectionStrategy.FORWARD - Select nodes from the beginning of the list
        SelectionStrategy.REVERSE - Select nodes from the end of the list
        SelectionStrategy.RANDOM - Select nodes randomly
        The node list is created in the following order and then traversed in
        the manner defined by the selection_strategy.
        - primary
        - backup primaries
        - all other nodes in the order they are listed in the genesis file
        Optional. (Default: chaosindy.common.SelectionStrategy.FORWARD.value)
    :type selection_strategy: int
    :param stop_strategy: A stop strategy defined by the
        chaosindy.common.StopStrategy enum. Examples include:
        StopStrategy.SERVICE - Stop the indy-node service (graceful)
        StopStrategy.PORT - Block the node port
        StopStrategy.DEMOTE - Demote the node
        StopStrategy.KILL - Kill the indy-node service (ungraceful)
        Optional. (Default: chaosindy.common.StopStrategy.SERVICE.value)
    :type stop_strategy: int
    :param include_primary: Include the primary in the node selection list? This
        parameter is case insensitive.
        Valid true options include: 'y', 'yes', '1', 't', 'true'
        Valid false options include: 'n', 'no', '0', 'f', 'false'
        Optional. (Default: "Yes")
    :type include_primary: str
    :param include_backup_primaries: Include backup primaries in the node
        selection list? This parameter is case insensitive.
        Valid true options include: 'y', 'yes', '1', 't', 'true'
        Valid false options include: 'n', 'no', '0', 'f', 'false'
        Optional. (Default: "Yes")
    :type include_backup_primaries: str
    :param include_other_nodes: Include non-primary and non-backup-primary nodes
        when selecting nodes using the stop_strategy? This parameter is case
        insensitive.
        Valid true options include: 'y', 'yes', '1', 't', 'true'
        Valid false options include: 'n', 'no', '0', 'f', 'false'
        Optional. (Default: "Yes")
    :type include_other_nodes: str
    :param max_checks_for_primary: When a primary is stopped, what is the
        maximum number of times the function should check for a view change? See
        sleep_between_checks.
        Optional. (Default: 6)
    :type max_checks_for_primary: Union[str,int]
    :param sleep_between_checks: When a primary is stopped, how long should the
        function sleep between checks for a view change.
        See max_checks_for_primary.
        Optional. (Default: 10)
    :type sleep_between_checks: Union[str,int]
    :param stop_node_timeout: How long should the function wait for
        stop_strategy operation to complete?
    :type stop_node_timeout: Union[str,int]
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
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

    # Assume no "other" (non-primary and non-backup-primaries) nodes, by default
    genesis_file_aliases = get_aliases(genesis_file)
    stopped_nodes = {}
    node_selection = []
    other_nodes = []

    # Are all "other" nodes included? If so, prime the list with a complete list
    # of aliases from the genesis file. See true_list in chaosindy.common.
    #
    # Cast include_other_nodes to a string and then convert to lower case.
    # It appears that chaostoolkit converts false used in the experiment JSON
    # file to False (bool) and python typing (include_other_nodes: str = 'Yes')
    # doesn't seem to care.
    if str(include_other_nodes).lower() in true_list:
        include_other_nodes = True
        other_nodes = genesis_file_aliases.copy()
    else:
        include_other_nodes = False

    # Get replica information from the primary's validator info
    primary = get_primary(genesis_file, compile_stats=True,
                          ssh_config_file=ssh_config_file)
    # See true_list in chaosindy.common
    if include_primary.lower() in true_list:
        message = "Adding the primary ({}) to the node_selection list"
        logger.debug(message.format(primary))
        node_selection.append(primary)

    if not primary:
        logger.error("Failed to get primary node alias.")
        return False

    # Remove the primary from other nodes even if it is not included in
    # node_selection. The objective is to get other_nodes down to just the
    # list of non-primary and non-backup-primary nodes. See true_list in
    # chaosindy.common
    if include_other_nodes:
        other_nodes.remove(primary)

    # Get replica information from the primary's validator info
    output_dir = get_chaos_temp_dir()
    with open("{}/{}-validator-info".format(output_dir, primary), 'r') as vif:
        validator_info = json.load(vif)
    replica_count = validator_info['Node_info']['Count_of_replicas']
    node_info = validator_info['Node_info']
    replica_status = node_info['Replicas_status']

    # Extract the backup primaries
    backup_primaries = []
    for key in replica_status.keys():
        # Skip the primary. It already be added if include_primary is set to
        # True.
        if key.endswith(":0"):
            continue
        alias = replica_status[key]['Primary'].split(":")[0]
        backup_primaries.append(alias)

    # Add backup primaries to node_selection in the order they are listed in
    # the genesis file.
    for alias in genesis_file_aliases:
        if alias in backup_primaries:
            # Remove the backup primary from other nodes even if it is not
            # included in node_selection. The objective is to get other_nodes
            # down to just the list of non-primary and non-backup-primary nodes.
            if include_other_nodes:
                other_nodes.remove(alias)
            if include_backup_primaries:
                message = "Adding the backup primary (%s) to the node_selection"
                logger.debug(message, alias)
                node_selection.append(alias)

    # Include the list of ther nodes in node_selection?
    if include_other_nodes:
        message = "Adding other nodes ({}) to the node_selection list"
        logger.debug(message.format(other_nodes))
        node_selection.extend(other_nodes)

    # Can't stop more than the number of nodes in node_selection. Rather than
    # fail, if the caller is asking for more nodes than have been selected, stop
    # as many as are selected.
    if number_of_nodes > len(node_selection):
        number_of_nodes = len(node_selection)

    #import pdb; pdb.set_trace()
    # Determine the nodes to stop based on the SelectionStrategy
    if selection_strategy == SelectionStrategy.RANDOM.value:
        node_selection_random = []
        # Use a copy of the list of nodes to stop so randomly selected nodes
        # do not get randomly selected more than once.
        node_selection_copy = node_selection.copy()
        for i in range(number_of_nodes):
            random_node = random.choice(node_selection_copy)
            node_selection_random.append(random_node)
            # Remove the random_node so it doesn't get selected again.
            node_selection_copy.remove(random_node)
        node_selection = node_selection_random
    elif selection_strategy == SelectionStrategy.REVERSE.value:
        node_selection = list(reversed(node_selection))[0:number_of_nodes]
    elif selection_strategy == SelectionStrategy.FORWARD.value:
        node_selection = node_selection[0:number_of_nodes]

    for node in node_selection:
        details = stop_by_strategy(genesis_file, node, stop_strategy,
                                   timeout=stop_node_timeout,
                                   ssh_config_file=ssh_config_file)
        if not details:
            return False
        stopped_nodes[node] = details

    data = {
        'stopped_nodes': stopped_nodes
    }
    with open("{}/stopped_nodes".format(output_dir), 'w') as f:
        f.write(json.dumps(data))

    if primary in stopped_nodes.keys():
        message = "Primary %s was included in list of demoted nodes. Wait for" \
                  " view change."
        logger.debug(message, primary)
        tries = wait_for_view_change(genesis_file=genesis_file,
            previous_primary=primary,
            max_checks_for_primary=max_checks_for_primary,
            sleep_between_checks=sleep_between_checks,
            ssh_config_file=ssh_config_file)
        if tries >= max_checks_for_primary:
            message="No view change detected after approximately %d*%d seconds"
            logger.debug(message, max_checks_for_primary, sleep_between_checks)
            return False

    return True


def start_stopped_nodes(genesis_file: str,
    ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Start the nodes stopped by a call to stop_n_nodes.

    stop_n_nodes must be called before start_stopped_nodes. Otherwise the
    stopped_nodes state file in the experiment's chaos temp dir will not exist.

    TODO: Move to a chaosindy.actions.replica.py?
    TODO: Change state file from stopped_nodes to stopped_primary? If so,
          must change logic to read the file into a dict (default empty dict),
          add/update the dict, and write it out to disk. Overwriting the file
          will not work. Perhaps the common module can be enhanced to support
          get_state, set_state abstractions?

    Assumptions:
      - A "stopped_nodes" file exists in the experiments chaos temp
        dir and contains a JSON object produced by a call to
        stop_n_nodes, which has a stopped_nodes attribute.
      - A "stopped_nodes" element exists in the JSON

    Arguments:
      genesis_file - path to the pool genesis transaction file
    Keyword Arguments (optional):
      ssh_config_file - SSH config file. Defaults to ~/.ssh/config.
    :type genesis_file: str
    :param genesis_file: The relative or absolute path to a genesis file.
        Required.
    :type genesis_file: str
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
    """
    output_dir = get_chaos_temp_dir()
    stopped_primary_dict = {}
    stopped_nodes_file = "{}/stopped_nodes".format(output_dir)
    try:
        with open(stopped_nodes_file, 'r') as stopped_primary:
            stopped_primary_dict = json.load(stopped_primary)
    except FileNotFoundError as e:
        message = """%s does not exist. Must call stop_n_nodes before'
                     calling start_stopped_nodes"""
        logger.error(message, stopped_nodes_file)
        logger.exception(e)
        return False

    stopped_nodes = stopped_primary_dict.get('stopped_nodes', None)
    if not stopped_nodes:
        message ="""Missing stopped_nodes element in
                    stopped_nodes_file state file {}"""
        logger.error(message.format(stopped_nodes_file))
        return False

    for backup_primary in stopped_nodes.keys():
        succeeded = start_by_strategy(genesis_file, backup_primary,
            stopped_nodes[backup_primary],
            ssh_config_file=ssh_config_file)
        if not succeeded:
            return False
    return True


def decrease_f_to(genesis_file: str, f_value: Union[str,int] = 1,
    selection_strategy: int = SelectionStrategy.REVERSE.value,
    seed: str = DEFAULT_CHAOS_SEED, pool_name: str = DEFAULT_CHAOS_POOL,
    wallet_name: str = DEFAULT_CHAOS_WALLET_NAME,
    wallet_key: str = DEFAULT_CHAOS_WALLET_KEY,
    timeout: Union[str,int] = DEFAULT_CHAOS_GET_VALIDATOR_INFO_TIMEOUT,
    pause_after: Union[str,int] = DEFAULT_CHAOS_PAUSE,
    ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Decrease the pool's f_value to a given value.

    Demote a sufficient number of nodes in order to reach the given f_value.
    A "demoted_nodes" state file is created to track demoted nodes.

    A typical/suggested workflow is as follows:
    1. Decrease a pool's f_value. (decrease_f_to)
    2. Optionally do something (write a NYM to ledger. Still in consensus?)
    3. Increase a pool's f_value back to it's original f_value (revert_f)

    Assumptions:
      - A pool of at least 4 nodes
      - The node list from which to select nodes using the given
        selection_strategy will be in the following order:
        - primary
        - backup primaries
        - all other nodes in the order they are listed in the genesis file

    :type genesis_file: str
    :param genesis_file: The relative or absolute path to a genesis file.
        Required.
    :type genesis_file: str
    :param f_value: The new f_value
        Optional. (Default: 1)
    :type f_value: Union[str,int]
    :param selection_strategy: A selection strategy defined by the
        chaosindy.common.SelectionStrategy enum.
        Examples include:
        SelectionStrategy.FORWARD - Select nodes from the beginning of the list
        SelectionStrategy.REVERSE - Select nodes from the end of the list
        SelectionStrategy.RANDOM - Select nodes randomly
        The node list is created in the following order and then traversed in
        the manner defined by the selection_strategy.
        - primary
        - backup primaries
        - all other nodes in the order they are listed in the genesis file
        Optional. (Default: chaosindy.common.SelectionStrategy.FORWARD.value)
    :type selection_strategy: int
    :param seed : A steward or trustee seed. Needed to get validator info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SEED)
    :type seed: str
    :param pool: The pool to connect to when getting validator info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_POOL)
    :type pool: str
    :param wallet_name: The name of the wallet to use when getting validator
        info.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_WALLET_NAME)
    :type wallet_name: str
    :param wallet_key: The key to use when opening the wallet designated by
        wallet_name.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_WALLET_KEY)
    :type wallet_key: str
    :param timeout: How long indy-cli can take to perform the operation before
        timing out.
        Optional.
        (Default: chaosindy.common.DEFAULT_CHAOS_LEDGER_TRANSACTION_TIMEOUT)
    :type timeout: Union[str,int]
    :param pause_after: How long pause/sleep after demoting nodes.
        Optional.
        (Default: chaosindy.common.DEFAULT_CHAOS_PAUSE)
    :type pause_after: Union[str,int]
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
    """
    if f_value:
        f_value = int(f_value)
    if selection_strategy:
        selection_strategy = int(selection_strategy)

    if not SelectionStrategy.has_value(selection_strategy):
        message = """Invalid selection strategy.
                     chaosindy.common.SelectionStrategy does not contain value
                     {}"""
        logger.error(message.format(selection_strategy))
        return False

    primary = get_primary(genesis_file, ssh_config_file=ssh_config_file,
                          compile_stats=True)

    current_f_value = None
    if primary:
        output_dir = get_chaos_temp_dir()
        with open("{}/{}-validator-info".format(output_dir, primary), 'r') as vif:
            validator_info = json.load(vif)
        current_f_value = validator_info['Pool_info']['f_value']
    else:
        logger.error("Could not get primary.")
        return False

    # Validate f_value
    if f_value < 1 or f_value >= current_f_value:
        message = "{} is and invalid f_value. Must be between 1 and {}"
        logger.error(message.format(f_value, (current_f_value - 1)))
        return False

    # Get the list of currently participating validator nodes
    validator_nodes = get_current_validator_list(genesis_file=genesis_file,
                                                 seed=seed, pool_name=pool_name,
                                                 wallet_name=wallet_name,
                                                 wallet_key=wallet_key,
                                                 timeout=timeout)
    current_number_of_nodes = len(validator_nodes)

    # What is the minimum number of nodes we must demote to get current_f_value
    # down to the target f_value? Add 2 instead of 1, because f changes in
    # increments of 3 and adding two gives us the maximum number of nodes that
    # can be validators and still get the given f_value.
    new_number_of_nodes = ((3 * f_value) + 3)

    # Demote the minimum number of nodes to get the current f_value down to the
    # new f_value.
    demote_node_count = (current_number_of_nodes - new_number_of_nodes)

    # Determine the nodes to demote based on the SelectionStrategy
    nodes_to_demote = []

    # Make a copy of the validator_nodes list and remove the primary
    validator_nodes_copy = validator_nodes.copy()

    # Remove the primary from validator_nodes_copy. validator_nodes_copy will be
    # the list from which we will select nodes to demote AFTER removing the
    # primary from the list.
    validator_nodes_copy.remove(primary)

    if selection_strategy == SelectionStrategy.RANDOM.value:
        nodes_to_demote_random = []
        # Use a copy of the list of nodes to demote so randomly selected nodes
        # do not get randomly selected more than once.
        nodes_to_demote_copy = validator_nodes_copy.copy()
        for i in range(demote_node_count):
            random_node = random.choice(nodes_to_demote_copy)
            nodes_to_demote_random.append(random_node)
            # Remove the random_node so it doesn't get selected again.
            nodes_to_demote_copy.remove(random_node)
        nodes_to_demote = nodes_to_demote_random
    elif selection_strategy == SelectionStrategy.REVERSE.value:
        reversed_list = reversed(validator_nodes_copy)
        nodes_to_demote = list(reversed_list)[0:demote_node_count]
    elif selection_strategy == SelectionStrategy.FORWARD.value:
        nodes_to_demote = validator_nodes_copy[0:demote_node_count]

    # Demote the nodes in nodes_to_demote
    demoted_node_detail = {}
    for node in nodes_to_demote:
        details = stop_by_strategy(genesis_file, node,
                                   StopStrategy.DEMOTE.value,
                                   ssh_config_file=ssh_config_file)
        if not details:
            message = """Failed to stop primary node %s by strategy %d"""
            logger.error(message, node, StopStrategy.DEMOTE.value)
            return False
        # Add details for each node
        demoted_node_detail[node] = details
    # Write the demoted-nodes state file. This file will be used by the revert_f
    # function below.
    with open("{}/demoted-nodes".format(output_dir), 'w') as f:
        f.write(json.dumps(demoted_node_detail))

    # Convert pause_after to int in the event the caller is chaostoolkit (JSON)
    pause_after = int(pause_after)
    # Pause after demoting nodes to allow the system to reach a steady state.
    message = "Pausing %d seconds to allow system to reach steady state after" \
              " demoting nodes: %s"""
    logger.info(message, pause_after, nodes_to_demote)
    sleep(pause_after)
    return True


def revert_f(genesis_file: str,
             timeout: Union[str,int] = DEFAULT_CHAOS_LEDGER_TRANSACTION_TIMEOUT,
             pause_after: Union[str,int] = DEFAULT_CHAOS_PAUSE,
             ssh_config_file: str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    Promote all nodes in state file demoted-nodes.

    See decrease_f_to

    A typical/suggested workflow is as follows:
    1. Decrease a pool's f_value. (decrease_f_to)
    2. Optionally do something (write a NYM to ledger. Still in consensus?)
    3. Increase a pool's f_value back to it's original f_value (revert_f)

    :type genesis_file: str
    :param genesis_file: The relative or absolute path to a genesis file.
        Required.
    :type genesis_file: str
    :param timeout: How long indy-cli can take to perform the operation before
        timing out.
        Optional.
        (Default: chaosindy.common.DEFAULT_CHAOS_LEDGER_TRANSACTION_TIMEOUT)
    :type timeout: Union[str,int]
    :param pause_after: How long pause/sleep after demoting nodes.
        Optional.
        (Default: chaosindy.common.DEFAULT_CHAOS_PAUSE)
    :type pause_after: Union[str,int]
    :param ssh_config_file: The relative or absolute path to the SSH config
        file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
    """
    output_dir = get_chaos_temp_dir()
    demoted_nodes_file = "{}/demoted-nodes".format(output_dir)
    try:
        with open(demoted_nodes_file, 'r') as demoted_nodes_file:
            demoted_nodes = json.load(demoted_nodes_file)
    except FileNotFoundError as e:
        message = """%s does not exist. Must call decrease_f_value before'
                     calling revert_f"""
        logger.error(message, demoted_nodes_file)
        logger.exception(e)
        return False

    for node in demoted_nodes:
        succeeded = start_by_strategy(genesis_file, node, demoted_nodes[node],
                                      timeout=timeout,
                                      ssh_config_file=ssh_config_file)
        if not succeeded:
            message = """Failed to start node %s by strategy %d"""
            logger.error(message, node, StopStrategy.PROMOTE.value)
            return False

    # Convert pause_after to int in the event the caller is chaostoolkit (JSON)
    pause_after = int(pause_after)
    # Pause after demoting nodes to allow the system to reach a steady state.
    message = "Pausing %d seconds to allow system to reach steady state after" \
              " promoting nodes: %s"""
    logger.info(message, pause_after, list(demoted_nodes.keys()))
    sleep(pause_after)
    return True
