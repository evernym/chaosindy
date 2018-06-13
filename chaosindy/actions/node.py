import os
import json
import random
from chaosindy.execute.execute import FabricExecutor
from logzero import logger

# Begin Helper Functions

# Helper functions are not intended to be used directly by experiements. They are
# intended to promote code reuse by functions that are for use directly by
# experiments.

def get_aliases(genesis_file):
    aliases = []
    # Open genesis_file and load all aliases into an array
    with open(os.path.expanduser(genesis_file), 'r') as genesisfile:
        for line in genesisfile:
            aliases.append(json.loads(line)['txn']['data']['data']['alias'])
    return aliases

# End Helper Functions


def stop_node_by_name(node, ssh_config_file="~/.ssh/config"):
    logger.debug("stop node: %s", node)
    executor = FabricExecutor(ssh_config_file=os.path.expanduser(ssh_config_file))

    # 1. Stop the node by alias name
    result = executor.execute(node, "systemctl stop indy-node", as_sudo=True)
    if result.return_code != 0:
        logger.error("Failed to stop %s", node)
        return False

    return True


def start_node_by_name(node, ssh_config_file="~/.ssh/config"):
    logger.debug("start node: %s", node)
    executor = FabricExecutor(ssh_config_file=os.path.expanduser(ssh_config_file))

    # 1. Stop the node by alias name
    result = executor.execute(node, "systemctl start indy-node", as_sudo=True)
    if result.return_code != 0:
        logger.error("Failed to start %s", node)
        return False

    return True


def start_nodes(aliases=[], ssh_config_file="~/.ssh/config"):
    # Start all nodes listed in aliases list
    count = len(aliases)
    tried_to_start = 0
    are_alive = 0
    for alias in aliases:
        logger.debug("alias to start: %s", alias)
        if start_node_by_name(alias, ssh_config_file):
            are_alive += 1
        tried_to_start += 1

    logger.debug("are_alive: %s -- count: %s -- tried_to_start: %s -- len-aliases: %s", are_alive, count, tried_to_start, len(aliases))
    if are_alive != int(count):
        return False

    return True


def stop_nodes(aliases=[], ssh_config_file="~/.ssh/config"):
    # Start all nodes listed in aliases list
    count = len(aliases)
    tried_to_stop = 0
    are_alive = 0
    for alias in aliases:
        logger.debug("alias to stop: %s", alias)
        if stop_node_by_name(alias, ssh_config_file):
            are_alive += 1
        tried_to_stop += 1

    logger.debug("are_alive: %s -- count: %s -- tried_to_stop: %s -- len-aliases: %s", are_alive, count, tried_to_stop, len(aliases))

    if are_alive != int(count):
        return False

    return True


def start_all_but_node_by_name(node, genesis_file, ssh_config_file="~/.ssh/config"):
    logger.debug("node: %s -- genesis_file: %s", node, genesis_file)
    # 1. Get all node aliases
    aliases = get_aliases(genesis_file)
    logger.debug(aliases)

    if node in aliases:
       # 2. Remove alias in node parameter from list of aliases
       aliases.remove(node)
       # 3. Call stop_nodes
       return start_nodes(aliases, ssh_config_file)
    
    return False


def all_nodes_up(genesis_file, ssh_config_file="~/.ssh/config"):
    logger.debug("genesis_file: %s -- ssh_config_file: %s", genesis_file, ssh_config_file)
    # 1. Get all node aliases
    aliases = get_aliases(genesis_file)
    logger.debug(aliases)

    # 2. Start all nodes.
    return start_nodes(aliases, ssh_config_file)


def kill_random_nodes(genesis_file, count, ssh_config_file="~/.ssh/config"):
    logger.debug("genesis_file: %s -- count: %s", genesis_file, count)
    # 1. Get all node aliases
    aliases = get_aliases(genesis_file)
    logger.debug(aliases)

    # 2. Kill 'count' nodes. It is okay to count a node if the service is already dead/stopped
    tried_to_kill = 0
    are_dead = 0
    number_of_aliases = len(aliases)
    while are_dead < int(count) and tried_to_kill < number_of_aliases:
        target = random.choice(aliases)
        aliases.remove(target)
        logger.debug("target alias to kill: %s", target)
        if stop_node_by_name(target, ssh_config_file):
            are_dead += 1
        tried_to_kill += 1

    logger.debug("are_dead: %s -- count: %s -- tried_to_kill: %s -- len-aliases: %s", are_dead, count, tried_to_kill, number_of_aliases)
    if are_dead < int(count):
        return False

    return True


def ensure_nodes_up(genesis_file, count, ssh_config_file="~/.ssh/config"):
    logger.debug("genesis_file: %s -- count: %s -- ssh_config_file: %s", genesis_file, count, ssh_config_file)
    # 1. Get all node aliases
    aliases = get_aliases(genesis_file)
    logger.debug(aliases)

    executor = FabricExecutor(ssh_config_file=os.path.expanduser(ssh_config_file))

    # 2. Start 'count' nodes. It is okay to count a node if the service is already alive/started
    tried_to_start = 0
    are_alive = 0
    number_of_aliases = len(aliases)
    while are_alive < int(count) and tried_to_start < number_of_aliases:
        target = random.choice(aliases)
        aliases.remove(target)
        logger.debug("target alias to start: %s", target)
        if start_node(target, ssh_config_file):
            are_alive += 1
        tried_to_start += 1

    logger.debug("are_alive: %s -- count: %s -- tried_to_start: %s -- len-aliases: %s", are_alive, count, tried_to_start, number_of_aliases)
    if are_alive < int(count):
        return False

    return True
