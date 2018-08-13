import os
import json
import random
import subprocess
import time
from chaosindy.common import *
from chaosindy.execute.execute import FabricExecutor, ParallelFabricExecutor
from chaosindy.probes.validator_info import get_validator_info
from logzero import logger
from multiprocessing import Pool
from os.path import expanduser, join

# Begin Helper Functions

# Helper functions are not intended to be used directly by experiements. They
# are intended to promote code reuse by functions that are for use directly by
# experiments.

def get_info_by_node_name(genesis_file, node, path=None):
    aliases = []
    # Open genesis_file and load all aliases into an array
    with open(expanduser(genesis_file), 'r') as genesisfile:
        for line in genesisfile:
            line_json = json.loads(line)
            alias = line_json['txn']['data']['data']['alias']
            if (alias == node):
                if not path:
                    return line_json['txn']['data']['data']
                else:
                    filters = path.split(".")
                    return_json = line_json
                    for f in filters:
                        return_json = return_json[f]
                    return return_json
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

def generate_load_parallel(clients, command=DEFAULT_CHAOS_LOAD_COMMAND,
                           timeout=DEFAULT_CHAOS_LOAD_TIMEOUT,
                           ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
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


def apply_iptables_rule_by_node_name(node, rule, ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
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


def block_port_by_node_name(node, port, ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
    logger.debug("block node %s on port %s", node, port)
    ## 1. Block a port or port range using a firewall
    if ":" in port:
        rule = "-A INPUT -p tcp --match multiport --dports {} -j DROP".format(port)
    else:
        rule = "-A INPUT -p tcp --destination-port {} -j DROP".format(port)
    return apply_iptables_rule_by_node_name(node, rule, ssh_config_file)


def unblock_port_by_node_name(node, port, best_effort=False, ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
    logger.debug("unblock node %s on port %s", node, port)
    do_not_fail = ""
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

def indy_node_is_stopped(node, timeout=30,
                         ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
    """
    Check if indy-node and indy-node-control services are stopped.
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

def stop_by_node_name(node, gracefully=True, force=True, timeout=30,
                      ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
    logger.debug("stop node: %s", node)
    executor = FabricExecutor(ssh_config_file=expanduser(ssh_config_file))

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
                time.sleep(6)
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

            if 'data' in node_info:
                catchup_transactions = node_info['data']['Node_info']['Catchup_status']['Number_txns_in_catchup']['1']
                ledger_status = node_info['data']['Node_info']['Catchup_status']['Ledger_statuses']['1']
            else:
                catchup_transactions = node_info['Node_info']['Catchup_status']['Number_txns_in_catchup']['1']
                ledger_status = node_info['Node_info']['Catchup_status']['Ledger_statuses']['1']
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

def set_node_services_from_cli(genesis_file, alias, alias_did,
                               did=DEFAULT_CHAOS_DID,
                               services=DEFAULT_CHAOS_NODE_SERVICES,
                               seed=DEFAULT_CHAOS_SEED,
                               wallet_name=DEFAULT_CHAOS_WALLET_NAME,
                               wallet_key=DEFAULT_CHAOS_WALLET_KEY,
                               pool=DEFAULT_CHAOS_POOL,
                               timeout=DEFAULT_CHAOS_LEDGER_TRANSACTION_TIMEOUT,
                               ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
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
    create_pool = subprocess.check_output(["indy-cli", indy_cli_command_batch], stderr=subprocess.STDOUT, shell=False)

    # Wallet creation
    indy_cli_command_batch = join(output_dir, "indy-cli-create-wallet.in")
    with open(indy_cli_command_batch, "w") as f:
        if wallet_key:
          f.write("wallet create {} key={}\n".format(wallet_name, wallet_key))
        else:
          f.write("wallet create {} key\n".format(wallet_name))
        f.write("exit")
    create_wallet = subprocess.check_output(["indy-cli", indy_cli_command_batch], stderr=subprocess.STDOUT, shell=False)

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
        create_did = subprocess.check_output(["indy-cli", indy_cli_command_batch], stderr=subprocess.STDOUT, shell=False)

    # Get the node's DID from the genesis transaction file. The DID can be found
    # in the txn.data.dest attribute where txn.data.data.alias == alias passed in.
    indy_cli_command_batch = join(output_dir, "indy-cli-demote-node.in")
    with open(indy_cli_command_batch, "w") as f:
        if wallet_key:
          f.write("wallet open {} key={}\n".format(wallet_name, wallet_key))
        else:
          f.write("wallet open {} key\n".format(wallet_name))
        f.write("did use {}\n".format(did))
        f.write("pool connect {}\n".format(pool))
        f.write("ledger node target={} alias={} services={}\n".format(alias_did, alias, services))
        f.write("exit")
    demote_node = subprocess.check_output(["indy-cli", indy_cli_command_batch], stderr=subprocess.STDOUT, timeout=int(timeout), shell=False)
    return True

def set_services_by_node_name(genesis_file, alias,
                              services=DEFAULT_CHAOS_NODE_SERVICES,
                              did=DEFAULT_CHAOS_DID,
                              seed=DEFAULT_CHAOS_SEED,
                              wallet_name=DEFAULT_CHAOS_WALLET_NAME,
                              wallet_key=DEFAULT_CHAOS_WALLET_KEY,
                              pool=DEFAULT_CHAOS_POOL,
                              timeout=DEFAULT_CHAOS_LEDGER_TRANSACTION_TIMEOUT,
                              ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
    """
    Change a node's services
    NOTE: Possible pure-python solution: https://github.com/hyperledger/indy-plenum/blob/62c8f47c20a1d204f2e90bb85f84cbf02c2b0b48/plenum/test/pool_transactions/helper.py#L413-L430
    """
    logger.debug("Setting %s's services to >%s<", alias, services)
    logger.debug("Get {}'s DID from genesis_file {}".format(alias, genesis_file))
    node_genesis_json = get_info_by_node_name(genesis_file, alias,
                                              path="txn.data")
    alias_did = node_genesis_json['dest']
    logger.debug("{}'s did is {}".format(alias, alias_did))
    return set_node_services_from_cli(genesis_file, alias, alias_did=alias_did,
                                      services=services, did=did, seed=seed,
                                      wallet_name=wallet_name,
                                      wallet_key=wallet_key, pool=pool,
                                      timeout=timeout,
                                      ssh_config_file=ssh_config_file)

def demote_by_node_name(genesis_file, alias,
                        services=DEFAULT_CHAOS_NODE_SERVICES,
                        did=DEFAULT_CHAOS_DID,
                        seed=DEFAULT_CHAOS_SEED,
                        wallet_name=DEFAULT_CHAOS_WALLET_NAME,
                        wallet_key=DEFAULT_CHAOS_WALLET_KEY,
                        pool=DEFAULT_CHAOS_POOL,
                        timeout=DEFAULT_CHAOS_LEDGER_TRANSACTION_TIMEOUT,
                        ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
    """
    Demote a node by setting it's "services" attribute to and empty list/string.
    """
    logger.debug("Demoting {}".format(alias))
    return set_services_by_node_name(genesis_file, alias, services="", did=did,
                                     seed=seed, wallet_name=wallet_name,
                                     wallet_key=wallet_key, pool=pool,
                                     timeout=timeout,
                                     ssh_config_file=ssh_config_file)

def restart_node(genesis_file, alias,
                 timeout=DEFAULT_CHAOS_LEDGER_TRANSACTION_TIMEOUT,
                 stop_strategy=StopStrategy.SERVICE.value,
                 ssh_config_file="~/.ssh/config"):
    """
    Restart a node

    Arguments:
      genesis_file - path to the pool genesis transaction file
      alias - Node to restart. Must be a name/alias found in the genesis_file
    Keyword Arguments (optional):
      timeout - Timeout in seconds.
      stop_strategy - See chaosindy.common.StopStrategy for options. Defaults to
                      StopStrategy.SERVICE.value
      ssh_config_file - SSH config file. Defaults to ~/.ssh/config
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

def promote_by_node_name(genesis_file, alias,
                         services=DEFAULT_CHAOS_NODE_SERVICES,
                         did=DEFAULT_CHAOS_DID,
                         seed=DEFAULT_CHAOS_SEED,
                         wallet_name=DEFAULT_CHAOS_WALLET_NAME,
                         wallet_key=DEFAULT_CHAOS_WALLET_KEY,
                         pool=DEFAULT_CHAOS_POOL,
                         timeout=DEFAULT_CHAOS_LEDGER_TRANSACTION_TIMEOUT,
                         ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
    """
    Promote a node by setting it's "services" attribute to and empty
    list/string.
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
        status = restart_node(genesis_file, alias, timeout=timeout,
                              ssh_config_file=ssh_config_file)
        if not status:
            logger.error("Failed to restart {}".format(alias))
    else:
        logger.error("Failed to promote {}".format(alias))

    return status

def stop_by_strategy(genesis_file, alias, stop_strategy,
                     timeout=DEFAULT_CHAOS_LEDGER_TRANSACTION_TIMEOUT,
                     ssh_config_file="~/.ssh/config"):
    """
    Assuptions:
        - A <alias>-validator-info file contains validator info for the given
          alias
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
            # "stop/block" inbound messages from clients and other nodes
            details['client_port'] = str(validator_info['Node_info']['Client_port'])
            details['node_port'] = str(validator_info['Node_info']['Node_port'])
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


def start_by_strategy(genesis_file, alias, details,
                      timeout=DEFAULT_CHAOS_LEDGER_TRANSACTION_TIMEOUT,
                      ssh_config_file="~/.ssh/config"):
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
                        stopped_replicas state file {} for {}"""
            logger.error(message.format(stopped_replicas_file, alias))
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


def reduce_f_by_one(genesis_file,
                    selection_strategy=SelectionStrategy.REVERSE.value,
                    ssh_config_file="~/.ssh/config"):
    if not SelectionStrategy.has_value(selection_strategy):
        message = """Invalid selection strategy.
                     chaosindy.common.SelectionStrategy does not contain value
                     {}"""
        logger.error(message.format(selection_strategy))
        return False

    aliases = get_aliases(genesis_file)

    # Determine the nodes to demote based on the SelectionStrategy
    nodes_to_demote = []
    number_of_nodes = 3
    if selection_strategy == SelectionStrategy.RANDOM.value:
        nodes_to_demote_random = []
        # Use a copy of the list of nodes to demote so randomly selected nodes
        # do not get randomly selected more than once.
        nodes_to_demote_copy = nodes_to_demote.copy()
        for i in range(number_of_nodes):
            random_node = random.choice(nodes_to_demote_copy)
            nodes_to_demote_random.append(random_node)
            # Remove the random_node so it doesn't get selected again.
            nodes_to_demote_copy.remove(random_node)
        nodes_to_demote = nodes_to_demote_random
    elif selection_strategy == SelectionStrategy.REVERSE.value:
        nodes_to_demote = list(reversed(nodes_to_demote))[0:number_of_nodes]
    elif selection_strategy == SelectionStrategy.FORWARD.value:
        nodes_to_demote = nodes_to_demote[0:number_of_nodes]

    # TODO: write demoted nodes to a state file

    return True


def promote_demoted_nodes(genesis_file, ssh_config_file="~/.ssh/config"):
    # TODO: read demoted nodes from a state file
    return True
