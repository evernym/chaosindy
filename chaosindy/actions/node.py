import os
import json
import random
import time
from chaosindy.common import *
from chaosindy.execute.execute import FabricExecutor
from chaosindy.probes.validator_info import get_chaos_temp_dir, get_validator_info
from logzero import logger
from multiprocessing import Pool
from os.path import expanduser, join

# Begin Helper Functions

# Helper functions are not intended to be used directly by experiements. They are
# intended to promote code reuse by functions that are for use directly by
# experiments.

def get_info_by_node_name(genesis_file, node):
    aliases = []
    # Open genesis_file and load all aliases into an array
    with open(expanduser(genesis_file), 'r') as genesisfile:
        for line in genesisfile:
            line_json = json.loads(line)
            alias = line_json['txn']['data']['data']['alias']
            if (alias == node):
                return line_json['txn']['data']['data']
    return None


def get_aliases(genesis_file):
    aliases = []
    # Open genesis_file and load all aliases into an array
    with open(expanduser(genesis_file), 'r') as genesisfile:
        for line in genesisfile:
            line_json = json.loads(line)
            alias = line_json['txn']['data']['data']['alias']
            aliases.append(alias)
    return aliases


# End Helper Functions

def generate_load(client, command=DEFAULT_CHAOS_LOAD_COMMAND,
                  timeout=DEFAULT_CHAOS_LOAD_TIMEOUT,
                  ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
    logger.info("Generating load from client %s using command >%s< and timeout >%s seconds<", client, command, timeout)
    executor = FabricExecutor(ssh_config_file=expanduser(ssh_config_file))
    result = executor.execute(client, command, as_sudo=True, timeout=int(timeout))
    if result.return_code != 0:
        logger.error("Failed to generate load from client %s", client)
        return False
    return True

def generate_load_parallel(clients, command=DEFAULT_CHAOS_LOAD_COMMAND,
                           timeout=DEFAULT_CHAOS_LOAD_TIMEOUT,
                           ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
    #logger.debug("Generating load from client(s) %s in parallel", clients)
    logger.info("Generating load from client(s) %s in sequence. TODO: do this in parallel.", clients)
    nodes = map(lambda x: (x, command, timeout), json.loads(clients))
    for node in nodes:
        generate_load(node[0], command=node[1], timeout=node[2],
            ssh_config_file=ssh_config_file)
    #with Pool(processes=4) as pool: 
        #pool = Pool()
        #pool.starmap(generate_load, nodes)


def apply_iptables_rule_by_node_name(node, rule, ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
    logger.debug("applying iptables rule >%s< on node: %s", rule, node)
    executor = FabricExecutor(ssh_config_file=expanduser(ssh_config_file))

    ## 1. Apply iptables rule
    try:
        result = executor.execute(node, "iptables {}".format(rule), as_sudo=True)
        if result.return_code != 0:
            logger.error("Failed to apply iptables rule >%s< on node %s", rule, node)
            return False
    except Exception as e:
        logger.exception(e)
        raise e

    return True


def block_port_by_node_name(node, port, ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
    ## 1. Block a port or port range using a firewall
    if ":" in port:
        rule = "-A INPUT -p tcp --match multiport --dports {} -j DROP".format(port)
    else:
        rule = "-A INPUT -p tcp --destination-port {} -j DROP".format(port)
    return apply_iptables_rule_by_node_name(node, rule, ssh_config_file)


def unblock_port_by_node_name(node, port, best_effort=False, ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
    do_not_fail = None
    if best_effort:
       do_not_fail = " || true"

    ## 1. Unblock a port or port range using a firewall
    if ":" in port:
        rule = "-D INPUT -p tcp --match multiport --dports {} -j DROP{}".format(port, do_not_fail)
    else:
        rule = "-D INPUT -p tcp --destination-port {} -j DROP{}".format(port, do_not_fail)

    try:
        return apply_iptables_rule_by_node_name(node, rule, ssh_config_file)
    except Exception as e:
        logger.exception(e)
        raise e

    return True


def stop_by_node_name(node, ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
    logger.debug("stop node: %s", node)
    executor = FabricExecutor(ssh_config_file=expanduser(ssh_config_file))

    # 1. Stop the node by alias name
    result = executor.execute(node, "systemctl stop indy-node", as_sudo=True)
    if result.return_code != 0:
        logger.error("Failed to stop %s", node)
        return False

    return True


def start_by_node_name(node, ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
    logger.debug("start node: %s", node)
    executor = FabricExecutor(ssh_config_file=expanduser(ssh_config_file))

    # 1. Stop the node by alias name
    result = executor.execute(node, "systemctl start indy-node", as_sudo=True)
    if result.return_code != 0:
        logger.error("Failed to start %s", node)
        return False

    return True


def start_nodes(aliases=[], ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
    # Start all nodes listed in aliases list
    count = len(aliases)
    tried_to_start = 0
    are_alive = 0
    for alias in aliases:
        logger.debug("alias to start: %s", alias)
        if start_by_node_name(alias, ssh_config_file):
            are_alive += 1
        tried_to_start += 1

    logger.debug("are_alive: %s -- count: %s -- tried_to_start: %s -- len-aliases: %s", are_alive, count, tried_to_start, len(aliases))
    if are_alive != int(count):
        return False

    return True


def stop_nodes(aliases=[], ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
    # Start all nodes listed in aliases list
    count = len(aliases)
    tried_to_stop = 0
    are_alive = 0
    for alias in aliases:
        logger.debug("alias to stop: %s", alias)
        if stop_by_node_name(alias, ssh_config_file):
            are_alive += 1
        tried_to_stop += 1

    logger.debug("are_alive: %s -- count: %s -- tried_to_stop: %s -- len-aliases: %s", are_alive, count, tried_to_stop, len(aliases))

    if are_alive != int(count):
        return False

    return True


def start_all_but_by_node_name(node, genesis_file, ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
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


def all_nodes_up(genesis_file, ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
    logger.debug("genesis_file: %s -- ssh_config_file: %s", genesis_file, ssh_config_file)
    # 1. Get all node aliases
    aliases = get_aliases(genesis_file)
    logger.debug(aliases)

    # 2. Start all nodes.
    return start_nodes(aliases, ssh_config_file)


def unblock_node_port_all_nodes(genesis_file, best_effort=True, ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
    logger.debug("genesis_file: %s", genesis_file)
    # 1. Get all node aliases
    aliases = get_aliases(genesis_file)
    logger.debug(aliases)

    for node in aliases:
        logger.debug("node: %s -- genesis_file: %s", node, genesis_file)
        node_info = get_info_by_node_name(genesis_file, node)
        try:
            unblock_port_by_node_name(node, str(node_info['node_port']), ssh_config_file)
        except Exception as e:
            logger.exception(e)
            if not best_effort:
                return False

    return True


def get_random_nodes(genesis_file, count):
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

    logger.debug("selected: %s, count: %s, len-aliases: %s", len(selected), count, number_of_aliases)
    return selected


def block_node_port_random(genesis_file, count, ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
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

    logger.debug("blocked: %s -- count: %s -- tried_to_block: %s -- len-aliases: %s", blocked, count, tried_to_block, len(selected))

    # Write out the block_node_port_random file to the temp output_dir created for this experiment
    with open(join(output_dir, "block_node_port_random"), "w") as f:
        f.write(json.dumps(blocked_ports))

    if blocked < int(count):
        return False

    return True


def unblocked_nodes_are_caught_up(genesis_file, transactions=None,
                                  pause_before_synced_check=None,
                                  best_effort=True,
                                  did=DEFAULT_CHAOS_DID,
                                  seed=DEFAULT_CHAOS_SEED,
                                  wallet_name=DEFAULT_CHAOS_WALLET_NAME,
                                  wallet_key=DEFAULT_CHAOS_WALLET_KEY,
                                  pool=DEFAULT_CHAOS_POOL,
                                  ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
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
        # Do not fail on exceptions like FileNotFoundError if best_effort is True
        if best_effort:
            return True
        else:
            raise e

    selected = blocked_ports.keys()

    # Only check if resurrected nodes are caught up if both a pause and number of
    # transactions are given.
    if pause_before_synced_check and transactions:
        logger.debug("Pausing %s seconds before checking if unblocked nodes are synced...", pause_before_synced_check)
        # TODO: Use a count down timer? May be nice for those who are running
        #       experiments manually.
        time.sleep(int(pause_before_synced_check))
        logger.debug("Checking if unblocked nodes are synced and report %s transactions...", transactions)
        return nodes_are_caught_up(selected, genesis_file, transactions, did,
                                   seed, wallet_name, wallet_key, pool,
                                   ssh_config_file)
    return True


def unblock_node_port_random(genesis_file, transactions=None,
                             pause_before_synced_check=None, best_effort=True,
                             did=DEFAULT_CHAOS_DID,
                             seed=DEFAULT_CHAOS_SEED,
                             wallet_name=DEFAULT_CHAOS_WALLET_NAME,
                             wallet_key=DEFAULT_CHAOS_WALLET_KEY,
                             pool=DEFAULT_CHAOS_POOL,
                             ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
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
        # Do not fail on exceptions like FileNotFoundError if best_effort is True
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
            if unblock_port_by_node_name(node, str(blocked_ports[node]), ssh_config_file):
                unblocked += 1
            else:
                still_blocked_ports[node] = blocked_ports[node]
        except Exception as e:
            if best_effort:
                pass
        tried_to_unblock += 1

    logger.debug("unblocked: %s -- tried_to_unblock: %s -- len-aliases: %s", unblocked, tried_to_unblock, len(selected))
    if not best_effort and unblocked < len(selected):
        return False

    # Only check if resurrected nodes are caught up if both a pause and number of
    # transactions are given.
    if pause_before_synced_check and transactions:
        logger.debug("Pausing %s seconds before checking if unblocked nodes are synced...", pause_before_synced_check)
        # TODO: Use a count down timer? May be nice for those who are running
        #       experiments manually.
        time.sleep(int(pause_before_synced_check))
        logger.debug("Checking if unblocked nodes are synced and report %s transactions...", transactions)
        return unblocked_nodes_are_caught_up(genesis_file, transactions, did,
                                             seed, wallet_name, wallet_key, pool,
                                             ssh_config_file)
    return True


def kill_random_nodes(genesis_file, count, ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
    selected = get_random_nodes(genesis_file, count)
    tried_to_kill = 0
    are_dead = 0
    number_of_aliases = len(selected)
    for node in selected:
        logger.debug("node alias to kill: %s", node)
        if stop_by_node_name(node, ssh_config_file):
            are_dead += 1
        tried_to_kill += 1

    logger.debug("are_dead: %s -- count: %s -- tried_to_kill: %s -- len-aliases: %s", are_dead, count, tried_to_kill, number_of_aliases)
    if are_dead < int(count):
        return False

    output_dir = get_chaos_temp_dir()
    # Write out the killed nodes list to the temp output_dir created for this experiment
    with open(join(output_dir, "nodes_random"), "w") as f:
        f.write(json.dumps(selected))

    return True


def resurrect_random_nodes(genesis_file, transactions=None,
                           pause_before_synced_check=None, best_effort=True,
                           did=DEFAULT_CHAOS_DID,
                           seed=DEFAULT_CHAOS_SEED,
                           wallet_name=DEFAULT_CHAOS_WALLET_NAME,
                           wallet_key=DEFAULT_CHAOS_WALLET_KEY,
                           pool=DEFAULT_CHAOS_POOL,
                           timeout=DEFAULT_CHAOS_GET_VALIDATOR_INFO_TIMEOUT,
                           ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
    # This function assumes that kill_random_nodes has been called and a
    # "nodes_random" file has been created in a temporary directory
    # created using rules defined by get_chaos_temp_dir()
    output_dir = get_chaos_temp_dir()
    selected = []
    try:
        with open(join(output_dir, "nodes_random"), "r") as f:
            selected = json.load(f)
    except Exception as e:
        # Do not fail on exceptions like FileNotFoundError if best_effort is True
        if best_effort:
            return True
        else:
            raise e

    resurrected = 0
    tried_to_resurrect = 0
    # Keep track of nodes/ports that could not be resurrected either by the
    # experiment's method or rollback segments and write it back to
    # block_node_port_random in the experiement's temp directory
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

    logger.debug("resurrected: %s -- tried_to_resurrect: %s -- len-aliases: %s", resurrected, tried_to_resurrect, len(selected))
    if not best_effort and resurrected < len(selected):
        return False

    # Write out the killed nodes list file to the temp output_dir created
    # for this experiment. Doing so allows resurrect_random_nodes to be called
    # in the rollback segment of an experiment w/o causing problems
    with open(join(output_dir, "nodes_random"), "w") as f:
        f.write(json.dumps(still_killed_nodes))

    # Only check if resurrected nodes are caught up if both a pause and number of
    # transactions are given.
    if pause_before_synced_check and transactions:
        logger.debug("Pausing %s seconds before checking if resurrected nodes are synced...", pause_before_synced_check)
        # TODO: Use a count down timer? May be nice for those who are running
        #       experiments manually.
        time.sleep(int(pause_before_synced_check))
        logger.debug("Checking if resurrected nodes are synced and report %s transactions...", transactions)
        return nodes_are_caught_up(selected, genesis_file, transactions, did=did,
                                   seed=seed, wallet_name=wallet_name,
                                   wallet_key=wallet_key, pool=pool,
                                   timeout=timeout,
                                   ssh_config_file=ssh_config_file)
    return True


def nodes_are_caught_up(nodes, genesis_file, transactions, 
                        did=DEFAULT_CHAOS_DID,
                        seed=DEFAULT_CHAOS_SEED,
                        wallet_name=DEFAULT_CHAOS_WALLET_NAME,
                        wallet_key=DEFAULT_CHAOS_WALLET_KEY,
                        pool=DEFAULT_CHAOS_POOL,
                        timeout=DEFAULT_CHAOS_GET_VALIDATOR_INFO_TIMEOUT,
                        ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
    # TODO: add support for all ledgers, not just domain ledger.
    #
    # This function assumes that kill_random_nodes has been called and a
    # "nodes_random" file has been created in a temporary directory
    # created using rules defined by get_chaos_temp_dir()
    # 1. Get validator info from all nodes
    get_validator_info(genesis_file, did=did, seed=seed, wallet_name=wallet_name,
                       wallet_key=wallet_key, pool=pool, timeout=timeout,
                       ssh_config_file=ssh_config_file)
    output_dir = get_chaos_temp_dir()

    matching = []
    not_matching = {}
    for alias in nodes:
        logger.debug("Checking if node %s has %s catchup transactions", alias, transactions)
        validator_info = join(output_dir, "{}-validator-info".format(alias))
        try:
            with open(validator_info, 'r') as f:
                node_info = json.load(f)

            catchup_transactions = node_info['data']['Node_info']['Catchup_status']['Number_txns_in_catchup']['1']
            ledger_status = node_info['data']['Node_info']['Catchup_status']['Ledger_statuses']['1']
        except FileNotFoundError:
            logger.info("Setting number of catchup transactions to Unknown for alias {}".format(alias))
            catchup_transactions = "Unknown"
            logger.info("Setting ledger status to Unknown for alias {}".format(alias))
            ledger_status = "Unknown"
        except Exception as e:
            logger.error("Failed to load validator info for alias %s", alias)
            logger.exception(e)
            return False

        logger.info("%s's ledger status in catchup is %s", alias, ledger_status)
        logger.info("%s's number of transactions in catchup is %s", alias, catchup_transactions)

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
            logger.error("Node %s failed to catchup. Reported %s transactions. Should have been %s", node, str(catchup_transactions), transactions)
            logger.info("%s's number of transactions in catchup is %s", alias, catchup_transactions)
        return False

    return True


def ensure_nodes_up(genesis_file, count, ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
    logger.debug("genesis_file: %s -- count: %s -- ssh_config_file: %s", genesis_file, count, ssh_config_file)
    # 1. Get all node aliases
    aliases = get_aliases(genesis_file)
    logger.debug(aliases)

    executor = FabricExecutor(ssh_config_file=expanduser(ssh_config_file))

    # 2. Start 'count' nodes. It is okay to count a node if the service is already alive/started
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

    logger.debug("are_alive: %s -- count: %s -- tried_to_start: %s -- len-aliases: %s", are_alive, count, tried_to_start, number_of_aliases)
    if are_alive < int(count):
        return False

    return True
