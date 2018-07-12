import json
import subprocess
import tempfile
from chaosindy.common import *
from chaosindy.execute.execute import FabricExecutor, ParallelFabricExecutor
from os.path import expanduser, join
from os import makedirs
from psutil import Process, NoSuchProcess
from logzero import logger
from multiprocessing import Pool


def get_chaos_temp_dir():
    # Get current process info
    myp = Process()
    subprocess_pid = myp.pid
    chaos_pid = None
    # Walk all the way up the process tree
    while(1):
        #  Break when we find the 'chaos' process
        if myp.name() == 'chaos':
            logger.debug("Found 'chaos' process")
            chaos_pid = myp.pid
            break
        try:
            myp = Process(myp.ppid())
            logger.debug("myp.name=%s", myp.name())
        except NoSuchProcess as e:
            logger.info("Did not find chaos pid before traversing all the way to the top of the process tree! Defaulting to %s", subprocess_pid)
            logger.exception(e)
            chaos_pid = subprocess_pid
            break

    logger.debug("subprocess pid: %s chaos pid: %s", subprocess_pid, chaos_pid)
    tempdir_path = "{}/validator-info.{}".format(tempfile.gettempdir(), chaos_pid)
    tempdir = makedirs(tempdir_path, exist_ok=True)
    logger.debug("tempdir: %s", tempdir_path)
    return tempdir_path


def get_validator_info_from_node_serial(genesis_file, 
                                        timeout=DEFAULT_CHAOS_GET_VALIDATOR_INFO_TIMEOUT,
                                        ssh_config_file="~/.ssh/config"):
    output_dir = get_chaos_temp_dir()
    logger.debug("genesis_file: %s ssh_config_file: %s", genesis_file, ssh_config_file)
    # 1. Open genesis_file and load all aliases into an array
    aliases = []
    with open(expanduser(genesis_file), 'r') as genesisfile:
        for line in genesisfile:
            aliases.append(json.loads(line)['txn']['data']['data']['alias'])
    logger.debug(str(aliases))

    executor = FabricExecutor(ssh_config_file=expanduser(ssh_config_file))

    # Get get validator info from each alias
    count = len(aliases)
    logger.debug("Getting validator data from all %i nodes...", count)
    tried_to_query= 0
    are_queried = 0
    for alias in aliases:
        logger.debug("alias to query validator info from: %s", alias)
        result = executor.execute(alias, "validator-info -v --json",
                                  timeout=int(timeout), as_sudo=True)
        if result.return_code == 0:
            are_queried += 1
            # Write JSON output to temp directory output_dir, creating a unique
            # file name using the alias
            with open(join(output_dir, "{}-validator-info".format(alias)), "w") as f:
                f.write(result.stdout)
        tried_to_query += 1

    logger.debug("are_queried: %s count: %i tried_to_query: %i len-aliases: %i", are_queried, count, tried_to_query, len(aliases))
    if are_queried < int(count):
        return False

    return True


def get_validator_info_from_node_parallel(genesis_file, 
                                          timeout=DEFAULT_CHAOS_GET_VALIDATOR_INFO_TIMEOUT,
                                          ssh_config_file="~/.ssh/config"):
    output_dir = get_chaos_temp_dir()
    logger.debug("genesis_file: %s ssh_config_file: %s", genesis_file, ssh_config_file)
    # 1. Open genesis_file and load all aliases into an array
    aliases = []
    with open(expanduser(genesis_file), 'r') as genesisfile:
        for line in genesisfile:
            aliases.append(json.loads(line)['txn']['data']['data']['alias'])
    logger.debug(str(aliases))

    executor = ParallelFabricExecutor(ssh_config_file=expanduser(ssh_config_file))

    # Get get validator info from each alias
    count = len(aliases)
    logger.debug("Getting validator data from all %i nodes...", count)
    tried_to_query = 0
    are_queried = 0
    logger.debug("alias to query validator info from: %s", str(aliases))
    result = executor.execute(aliases, "validator-info -v --json",
                              connect_timeout=int(timeout), as_sudo=True)

    for alias in aliases:
        if result[alias]['return_code'] == 0:
            are_queried += 1
            # Write JSON output to temp directory output_dir, creating a unique
            # file name using the alias
            with open(join(output_dir, "{}-validator-info".format(alias)), "w") as f:
                f.write(result[alias]['stdout'])
        tried_to_query += 1

    logger.debug("are_queried: %s count: %i tried_to_query: %i len-aliases: %i", are_queried, count, tried_to_query, len(aliases))
    if are_queried < int(count):
        return False

    return True


def get_validator_info_from_cli(genesis_file, did=DEFAULT_CHAOS_DID,
                                seed=DEFAULT_CHAOS_SEED,
                                wallet_name=DEFAULT_CHAOS_WALLET_NAME,
                                wallet_key=DEFAULT_CHAOS_WALLET_KEY,
                                pool=DEFAULT_CHAOS_POOL,
                                timeout=DEFAULT_CHAOS_GET_VALIDATOR_INFO_TIMEOUT,
                                ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
    '''
     The following steps are required to configure the client node where
     indy-cli will be used to retrieve validator-info:
     
     1. Install indy-cli
        `$ apt-get install indy-cli`
     2. Start indy-cli
        `$ indy-cli`
        `indy>`
     3. Create pool
        NOTE: Pool name will be a parameter for the experiments that need
              validator info
        `indy> pool create pool1 gen_txn_file=/home/ubuntu/pool_transactions_genesis`
     4. Create wallet
        NOTE: Wallet name and optional key will be parameters for the
              experiments that need validator info
        `indy> wallet create wallet1 pool_name=pool1 key=key1`
     5. Open wallet created in the previous step
        `indy> wallet open wallet1 key=key1`
        `wallet(wallet1):indy>`
     6. Create did with a Trustee seed
        NOTE: did will be a parameter for the experiments that need validator
              info. validator info is only available to Trustees and Stewards
        `wallet(wallet1):indy> did new seed=000000000000000000000000Trustee1`
     7. Open pool created in previous step
        `wallet(wallet1):indy> pool connect pool1`
        `pool(pool1):wallet(wallet1):indy>`
     8. Verify the did created with the Trustee seed can retrieve validator info
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

    # TODO: Do we want to get a list of aliases from the genesis file and make
    #       sure that indy-cli returns validator info for each node?

    # Pool creation
    indy_cli_command_batch = join(output_dir, "indy-cli-create-pool.in")
    with open(indy_cli_command_batch, "a") as f:
        f.write("pool create {} gen_txn_file={}\n".format(pool, genesis_file))
        f.write("exit")
    create_pool = subprocess.check_output(["indy-cli", indy_cli_command_batch], stderr=subprocess.STDOUT, shell=False)

    # Wallet creation
    indy_cli_command_batch = join(output_dir, "indy-cli-create-wallet.in")
    with open(indy_cli_command_batch, "a") as f:
        if wallet_key:
          f.write("wallet create {} pool_name={} key={}\n".format(wallet_name, pool, wallet_key))
        else:
          f.write("wallet create {} pool_name={} key\n".format(wallet_name, pool))
        f.write("exit")
    create_wallet = subprocess.check_output(["indy-cli", indy_cli_command_batch], stderr=subprocess.STDOUT, shell=False)

    # DID creation
    if seed:
        indy_cli_command_batch = join(output_dir, "indy-cli-create-did.in")
        with open(indy_cli_command_batch, "a") as f:
            if wallet_key:
              f.write("wallet open {} key={}\n".format(wallet_name, wallet_key))
            else:
              f.write("wallet open {} key\n".format(wallet_name))
            f.write("did new seed={}\n".format(seed))
            f.write("exit")
        create_did = subprocess.check_output(["indy-cli", indy_cli_command_batch], stderr=subprocess.STDOUT, shell=False)

    # Get validator information
    indy_cli_command_batch = join(output_dir, "indy-cli-get-validator-info.in")
    with open(indy_cli_command_batch, "a") as f:
        if wallet_key:
          f.write("wallet open {} key={}\n".format(wallet_name, wallet_key))
        else:
          f.write("wallet open {} key\n".format(wallet_name))
        f.write("did use {}\n".format(did))
        f.write("pool connect {}\n".format(pool))
        f.write("ledger get-validator-info\n")
        f.write("exit")
    all_validator_info = subprocess.check_output(["indy-cli", indy_cli_command_batch], stderr=subprocess.STDOUT, timeout=int(timeout), shell=False)
    lines = all_validator_info.splitlines()
    # ledger get-validator-info returns a JSON string for each node to STDOUT
    # Each JSON string is preceeded by "Get validator info response for node..."
    # verbiage. Parse each line and write each nodes' JSON string to a
    # <node_name>-validator-info file
    # 
    # NOTE: Can't use `for line in lines` combined with next(lines), because
    #       lines is an interable, but not an iterator.
    i = 0
    number_of_lines = len(lines)
    while i < number_of_lines:
        line = lines[i].decode()
        if "Get validator info response for node " in line:
            node_name = line.split("Get validator info response for node", 1)[1].split(":", 1)[0].strip()
            # The next line is the validator info JSON string
            i += 1
            node_info = lines[i].decode()
            node_info_file = join(output_dir, "{}-validator-info".format(node_name))
            with open(node_info_file, "w") as f:
                f.write(node_info)
        i += 1
    return True


def get_validator_info_from_node(genesis_file,
                                 timeout=DEFAULT_CHAOS_GET_VALIDATOR_INFO_TIMEOUT,
                                 ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE,
                                 parallel=True):
    if parallel:
        return get_validator_info_from_node_parallel(genesis_file, timeout=timeout,
                                                     ssh_config_file=ssh_config_file)
    else:
        return get_validator_info_from_node_serial(genesis_file, timeout=timeout,
                                                   ssh_config_file=ssh_config_file)


def get_validator_info(genesis_file, did=DEFAULT_CHAOS_DID,
                       seed=DEFAULT_CHAOS_SEED,
                       wallet_name=DEFAULT_CHAOS_WALLET_NAME,
                       wallet_key=DEFAULT_CHAOS_WALLET_KEY,
                       pool=DEFAULT_CHAOS_POOL,
                       timeout=DEFAULT_CHAOS_GET_VALIDATOR_INFO_TIMEOUT,
                       ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE,
                       source=DEFAULT_VALIDATOR_INFO_SOURCE):
    '''
    Validator info can be retrieved from any of the following:
      - A client that has indy-cli installed using `ledger get-validator-info`.
        This option provides more up-to-date information, but may take a long
        time to return results (100 sec default timeout when at least one node
        is down/unreachable). See ValidatorInfoSource.CLI in chaosindy/common.
      - A validator node using `validator-info -v --json`
        This option provides quicker results, but the data may be up to 60
        seconds stale/out-of-date.  See ValidatorInfoSource.NODE in
        chaosindy/common.

    The DEFAULT_VALIDATOR_INFO_SOURCE dictates where chaos experiments will get
    validator information by default. 
    '''
    if source == ValidatorInfoSource.NODE:
        return get_validator_info_from_node(genesis_file, timeout=timeout,
                                            ssh_config_file=ssh_config_file)
    elif source == ValidatorInfoSource.CLI:
        return get_validator_info_from_cli(genesis_file, did=did, seed=seed,
                                           wallet_name=wallet_name,
                                           wallet_key=wallet_key, pool=pool,
                                           timeout=timeout,
                                           ssh_config_file=ssh_config_file)
    else:
        logger.error("Unsupported validator info source: %s", source)
        return False


def detect_primary(genesis_file, did=DEFAULT_CHAOS_DID,
                   seed=DEFAULT_CHAOS_SEED,
                   wallet_name=DEFAULT_CHAOS_WALLET_NAME,
                   wallet_key=DEFAULT_CHAOS_WALLET_KEY,
                   pool=DEFAULT_CHAOS_POOL,
                   timeout=DEFAULT_CHAOS_GET_VALIDATOR_INFO_TIMEOUT,
                   ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
    # 1. Get validator info from all nodes
    get_validator_info(genesis_file, did=did, seed=seed, wallet_name=wallet_name,
                       wallet_key=wallet_key, pool=pool,
                       timeout=timeout, ssh_config_file=ssh_config_file)
    output_dir = get_chaos_temp_dir()

    logger.debug("genesis_file: %s ssh_config_file: %s", genesis_file, ssh_config_file)
    # 2. Open genesis_file and load all aliases into an array
    aliases = []
    with open(expanduser(genesis_file), 'r') as genesisfile:
        for line in genesisfile:
            aliases.append(json.loads(line)['txn']['data']['data']['alias'])
    logger.debug(str(aliases))

    # 3. Get primary from each nodes validator-info
    primary_map = {}
    count = len(aliases)
    logger.debug("Getting primary node alias from validator-info collected from all %i nodes...", count)
    tried_to_query= 0
    for alias in aliases:
        logger.debug("alias to query primary from validator info: %s", alias)
        validator_info = join(output_dir, "{}-validator-info".format(alias))
        logger.debug("Extract primary from %s", validator_info)

        try:
            with open(validator_info, 'r') as f:
                node_info = json.load(f)

            # For each node, Indy CLI returns json in a 'data' element
            try:
                primary = node_info['data']['Node_info']['Replicas_status']["{}:0".format(alias)]['Primary']
                primary = primary.split(":", 1)[0] if primary else None
                mode = node_info['data']['Node_info']['Mode']
            except KeyError as e:
                # For each node, validator-info script does NOT return json in a 'data' element
                primary = node_info['Node_info']['Replicas_status']["{}:0".format(alias)]['Primary']
                primary = primary.split(":", 1)[0] if primary else None
                mode = node_info['Node_info']['Mode']

        except FileNotFoundError:
            logger.info("Failed to load validator info for alias {}".format(alias))
            logger.info("Setting primary to Unknown for alias {}".format(alias))
            primary = "Unknown"
            logger.info("Setting mode to Unknown for alias {}".format(alias))
            mode = "Unknown"
        except Exception as e:
            logger.error("Failed to load validator info for alias {}".format(alias))
            logger.exception(e)
            return False

        # Set the alias' primary
        alias_map = primary_map.get(alias, {})
        alias_map["primary"] = primary
        primary_map[alias] = alias_map
        if primary != 'Unknown':
            # Put the alias in the primary's is_primary_to list
            primary_alias_map = primary_map.get(primary, {})
            is_primary_to_list = primary_alias_map.get("is_primary_to", [])
            if alias not in is_primary_to_list:
                is_primary_to_list.append(alias)
            primary_alias_map['is_primary_to'] = is_primary_to_list
            primary_map[primary] = primary_alias_map

        logger.info("%s's primary is %s - mode: %s", alias, primary, mode)
        tried_to_query += 1

    # 4. Reconcile who is actually the primary. A primary is any node/alias with
    #    an is_primary_to list. However, the node/alias the majority of nodes
    #    reporting it as the primary is the actual primary.
    primary_map['node_count'] = count
    nodes_with_is_primary_to_list = 0
    current_primary = None
    for alias in aliases:
        alias_map = primary_map.get(alias, {})
        is_master_to_count = len(alias_map.get('is_primary_to', []))
        if is_master_to_count > 0:
            nodes_with_is_primary_to_list += 1
        if is_master_to_count > (count / 2):
            alias_map['is_primary'] = True
            primary_map['current_primary'] = alias
    primary_map['reported_primaries'] = nodes_with_is_primary_to_list 

    logger.debug("count: %i tried_to_query: %s len-aliases: %s", count, tried_to_query, len(aliases))
    if tried_to_query < int(count):
        return False

    with open(join(output_dir, "primaries"), "w") as f:
        f.write(json.dumps(primary_map))

    return True


def detect_mode(genesis_file, did=DEFAULT_CHAOS_DID,
                seed=DEFAULT_CHAOS_SEED,
                wallet_name=DEFAULT_CHAOS_WALLET_NAME,
                wallet_key=DEFAULT_CHAOS_WALLET_KEY,
                pool=DEFAULT_CHAOS_POOL,
                timeout=DEFAULT_CHAOS_GET_VALIDATOR_INFO_TIMEOUT,
                ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
    # 1. Get validator info from all nodes
    get_validator_info(genesis_file, did=did, seed=seed, wallet_name=wallet_name,
                       wallet_key=wallet_key, pool=pool,
                       timeout=timeout, ssh_config_file=ssh_config_file)
    output_dir = get_chaos_temp_dir()

    logger.debug("genesis_file: %s ssh_config_file: %s", genesis_file, ssh_config_file)
    # 2. Open genesis_file and load all aliases into an array
    aliases = []
    with open(expanduser(genesis_file), 'r') as genesisfile:
        for line in genesisfile:
            aliases.append(json.loads(line)['txn']['data']['data']['alias'])
    logger.debug(str(aliases))

    # 3. Get mode from each nodes validator-info
    mode_map = {}
    count = len(aliases)
    logger.debug("Getting mode from validator-info collected from all %i nodes...", count)
    tried_to_query= 0
    for alias in aliases:
        logger.debug("alias to query mode from validator info: %s", alias)
        validator_info = join(output_dir, "{}-validator-info".format(alias))
        logger.debug("Extract mode from %s", validator_info)

        try:
            with open(validator_info, 'r') as f:
                node_info = json.load(f)
            mode = node_info['data']['Node_info']['Mode']
        except FileNotFoundError:
            logger.info("Failed to load validator info for alias {}".format(alias))
            logger.info("Setting mode to Unknown for alias {}".format(alias))
            mode = "Unknown"
        except Exception as e:
            logger.error("Failed to load validator info for alias {}".format(alias))
            logger.exception(e)
            return False

        logger.info("%s's mode is %s", alias, mode)
        # Set the alias' mode
        alias_map = mode_map.get(alias, {})
        alias_map["mode"] = mode
        mode_map[alias] = alias_map
        tried_to_query += 1

    logger.debug("count: %i tried_to_query: %s len-aliases: %s", count, tried_to_query, len(aliases))
    if tried_to_query < int(count):
        return False

    with open(join(output_dir, "mode"), "w") as f:
        f.write(json.dumps(mode_map))

    return True


def nodes_in_mode(genesis_file, mode, count, did=DEFAULT_CHAOS_DID,
                  seed=DEFAULT_CHAOS_SEED,
                  wallet_name=DEFAULT_CHAOS_WALLET_NAME,
                  wallet_key=DEFAULT_CHAOS_WALLET_KEY,
                  pool=DEFAULT_CHAOS_POOL,
                  timeout=DEFAULT_CHAOS_GET_VALIDATOR_INFO_TIMEOUT,
                  ssh_config_file=DEFAULT_CHAOS_SSH_CONFIG_FILE):
    # Must first get mode of each node using validator info.
    if not detect_mode(genesis_file, did=did, seed=seed, wallet_name=wallet_name,
                       wallet_key=wallet_key, pool=pool, timeout=timeout,
                       ssh_config_file=ssh_config_file):
        return False

    output_dir = get_chaos_temp_dir()
    node_mode = {}
    with open("{}/mode".format(output_dir), 'r') as f:
       node_mode = json.load(f)

    ncount = 0
    for alias in node_mode.keys():
       nmode = node_mode[alias]['mode']
       if mode == nmode:
           ncount += 1

    if int(count) == ncount:
        return True
    else:
        return False


def resurrected_nodes_are_caught_up(genesis_file, transactions, 
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
    # "killed_nodes_random" file has been created in a temporary directory
    # created using rules defined by get_chaos_temp_dir()
    # 1. Get validator info from all nodes
    get_validator_info(genesis_file, did=did, seed=seed, wallet_name=wallet_name,
                       wallet_key=wallet_key, pool=pool,
                       timeout=timeout, ssh_config_file=ssh_config_file)
    output_dir = get_chaos_temp_dir()
    selected = []
    try:
        with open(join(output_dir, "killed_nodes_random"), "r") as f:
            selected = json.load(f)
    except Exception as e:
        # Do not fail on exceptions like FileNotFoundError if best_effort is True
        if best_effort:
            return True
        else:
            raise e

    matching = []
    not_matching = {}
    for alias in selected:
        logger.debug("Checking if node %s has %s catchup transactions", alias, transactions)
        validator_info = join(output_dir, "{}-validator-info".format(alias))
        try:
            with open(validator_info, 'r') as f:
                node_info = json.load(f)

            catchup_transactions = node_info['data']['Node_info']['Catchup_status']['Number_txns_in_catchup']['1']
            ledger_status = node_info['data']['Node_info']['Catchup_status']['Ledger_statuses']['1']
        except FileNotFoundError:
            logger.info("Failed to load validator info for alias {}".format(alias))
            logger.info("Setting number of catchup transactions to None for alias {}".format(alias))
            catchup_transactions = None
            logger.info("Setting ledger status to Unknown for alias {}".format(alias))
            ledger_status = "Unknown"
        except Exception as e:
            logger.error("Failed to load validator info for alias {}".format(alias))
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
            logger.debug("Node %s failed to catchup. Reported %s transactions. Should have been %s".format(node, str(catchup_transactions), transactions))
        return False

    return True
