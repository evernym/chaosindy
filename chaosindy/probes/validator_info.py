import json
import subprocess
import tempfile
from chaosindy.execute.execute import FabricExecutor
from os.path import expanduser, join
from os import makedirs
from psutil import Process, NoSuchProcess
from logzero import logger

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
            logger.info("Did not find chaos pid before traversing all the way to the top of the process tree!")
            logger.exception(e)
            break

    logger.debug("subprocess pid: %s chaos pid: %s", subprocess_pid, chaos_pid)
    tempdir_path = "{}/validator-info.{}".format(tempfile.gettempdir(), chaos_pid)
    tempdir = makedirs(tempdir_path, exist_ok=True)
    logger.debug("tempdir: %s", tempdir_path)
    return tempdir_path


def get_validator_info(genesis_file, did="V4SGRU86Z58d6TV7PBUe6f",
                       seed="000000000000000000000000Trustee1",
                       wallet_name="chaosindy", wallet_key="chaosindy",
                       pool="chaosindy", ssh_config_file="~/.ssh/config"):
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
    all_validator_info = subprocess.check_output(["indy-cli", indy_cli_command_batch], stderr=subprocess.STDOUT, shell=False)
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


def detect_primary(genesis_file, did="V4SGRU86Z58d6TV7PBUe6f",
                   seed="000000000000000000000000Trustee1",
                   wallet_name="chaosindy", wallet_key="chaosindy",
                   pool="chaosindy", ssh_config_file="~/.ssh/config"):
    # 1. Get validator info from all nodes
    get_validator_info(genesis_file, did, seed, wallet_name, wallet_key, pool, ssh_config_file)
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
        except Exception as e:
            logger.error("Failed to load validator info for alias {}".format(alias))
            logger.exception(e)
            return False

        primary = node_info['data']['Node_info']['Replicas_status']["{}:0".format(alias)]['Primary'].split(":", 1)[0]
        # Set the alias' primary
        alias_map = primary_map.get(alias, {})
        alias_map["primary"] = primary
        primary_map[alias] = alias_map
        # Put the alias in the primary's is_primary_to list
        primary_alias_map = primary_map.get(primary, {})
        is_primary_to_list = primary_alias_map.get("is_primary_to", [])
        if alias not in is_primary_to_list:
            is_primary_to_list.append(alias)
        primary_alias_map['is_primary_to'] = is_primary_to_list
        primary_map[primary] = primary_alias_map

        mode = node_info['data']['Node_info']['Mode']
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


def detect_mode(genesis_file, did="V4SGRU86Z58d6TV7PBUe6f",
                seed="000000000000000000000000Trustee1",
                wallet_name="chaosindy", wallet_key="chaosindy",
                pool="chaosindy", ssh_config_file="~/.ssh/config"):
    # 1. Get validator info from all nodes
    get_validator_info(genesis_file, did, seed, wallet_name, wallet_key, pool, ssh_config_file)
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
        except Exception as e:
            logger.error("Failed to load validator info for alias {}".format(alias))
            logger.exception(e)
            return False

        mode = node_info['data']['Node_info']['Mode']
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


def nodes_in_mode(genesis_file, mode, count, did="V4SGRU86Z58d6TV7PBUe6f",
                  seed="000000000000000000000000Trustee1",
                  wallet_name="chaosindy", wallet_key="chaosindy",
                  pool="chaosindy", ssh_config_file="~/.ssh/config"):
    # Must first get mode of each node using validator info.
    if not detect_mode(genesis_file, did, seed, wallet_name, wallet_key, pool, ssh_config_file):
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
                                    did="V4SGRU86Z58d6TV7PBUe6f",
                                    seed="000000000000000000000000Trustee1",
                                    wallet_name="chaosindy",
                                    wallet_key="chaosindy", pool="chaosindy",
                                    ssh_config_file="~/.ssh/config"):
    # TODO: add support for all ledgers, not just domain ledger.
    #
    # This function assumes that kill_random_nodes has been called and a
    # "killed_nodes_random" file has been created in a temporary directory
    # created using rules defined by get_chaos_temp_dir()
    # 1. Get validator info from all nodes
    get_validator_info(genesis_file, did, seed, wallet_name, wallet_key, pool, ssh_config_file)
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
            logger.info("%s's ledger status in catchup is %s", alias, ledger_status)
            logger.info("%s's number of transactions in catchup is %s", alias, catchup_transactions)

            #if ledger_status == 'syncing' or (ledger_status == 'synced' and catchup_transactions == int(transactions)):
            if ledger_status == 'synced' and catchup_transactions == int(transactions):
                matching.append(alias)
            else:
                not_matching[alias] = catchup_transactions
        except Exception as e:
            logger.error("Failed to load validator info for alias {}".format(alias))
            logger.exception(e)
            return False

    if len(not_matching.keys()) != 0:
        for node in not_matching.keys():
            logger.debug("Node %s failed to catchup. Reported %s transactions. Should have been %s".format(node, str(catchup_transactions), transactions))
        return False

    return True
