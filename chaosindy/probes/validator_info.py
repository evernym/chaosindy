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


def get_validator_info(genesis_file, ssh_config_file="~/.ssh/config"):
    output_dir = get_chaos_temp_dir()
    logger.debug("genesis_file: %s ssh_config_file: %s", genesis_file, ssh_config_file)
    # 1. Open genesis_file and load all aliases into an array
    aliases = []
    with open(expanduser(genesis_file), 'r') as genesisfile:
        for line in genesisfile:
            aliases.append(json.loads(line)['txn']['data']['data']['alias'])
    logger.debug(str(aliases))

    executor = FabricExecutor(ssh_config_file=expanduser(ssh_config_file))

    # 2. Start all nodes.
    count = len(aliases)
    logger.debug("Getting validator data from all %i nodes...", count)
    tried_to_query= 0
    are_queried = 0
    for alias in aliases:
        logger.debug("alias to query validator info from: %s", alias)
        result = executor.execute(alias, "validator-info -v", as_sudo=True)
        if result.return_code == 0:
            are_queried += 1
            with open(join(output_dir, "{}-validator-info".format(alias)), "w") as f:
                f.write(result.stdout)
        tried_to_query += 1

    logger.debug("are_queried: %s count: %i tried_to_query: %i len-aliases: %i", are_queried, count, tried_to_query, len(aliases))
    if are_queried < int(count):
        return False

    return True


def detect_primary(genesis_file, ssh_config_file="~/.ssh/config"):
    # 1. Get validator info from all nodes
    get_validator_info(genesis_file, ssh_config_file)
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
        # Scrape the primary from validator-info output.
        # TODO: refactor to use JSON once valid json is produced by
        #       validator-info

        # Useful for debugging: Capture the entire contents of the
        # validator_info file
        #validator_info_cat = subprocess.Popen(["cat", validator_info],
        #                                      stdout=subprocess.PIPE,
        #                                      shell=False)
        #validator_info_lines = validator_info_cat.communicate()[0]

        # Scrape out the replica set
        #replica_sed = subprocess.Popen(["sed", "-n", "-e",
        #                                "'/Replicas_status/,/Pool_info/ p'",
        #                                validator_info],
        #                               stdout=subprocess.PIPE,
        #                               shell=False)
        #replica_grep = subprocess.Popen(["grep", "-E",
        #                                 "'\"[A-Za-z0-9]{1,}:[0-9]{1,}\"'"],
        #                                stdin=replica_sed.stdout,
        #                                stdout=subprocess.PIPE, shell=False)
        #replica_sed.stdout.close()
        #
        ## Extract the replica set, decode them, and strip off carriage returns
        #replicaset = replica_grep.communicate()[0]

        primary_grep = subprocess.Popen(["grep", "\"Primary\":",
                                          validator_info],
                                        stdout=subprocess.PIPE, shell=False)
        primary_grep2 = subprocess.Popen(["grep", ":0"],
                                         stdin=primary_grep.stdout,
                                         stdout=subprocess.PIPE,
                                         shell=False)
        primary_cut = subprocess.Popen(['cut', '-f', '2', '-d', ':'],
                                        stdin=primary_grep2.stdout,
                                        stdout=subprocess.PIPE, shell=False)
        primary_awk = subprocess.Popen(['awk', '{$1=$1};1'],
                                       stdin=primary_cut.stdout,
                                       stdout=subprocess.PIPE, shell=False)
        primary_grep.stdout.close()
        primary_grep2.stdout.close()
        primary_cut.stdout.close()

        # Extract the primary, decode it, and strip off carriage returns
        result = primary_awk.communicate()[0]

        if result:
            primary = result.decode().strip()
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

        mode_grep = subprocess.Popen(["grep", "\"Mode\":", validator_info],
                                     stdout=subprocess.PIPE,
                                     shell=False)
        mode_cut = subprocess.Popen(['cut', '-f', '2', '-d', ':'],
                                    stdin=mode_grep.stdout,
                                    stdout=subprocess.PIPE, shell=False)
        mode_awk = subprocess.Popen(['awk', '{$1=$1};1'],
                                    stdin=mode_cut.stdout,
                                    stdout=subprocess.PIPE, shell=False)
        mode_grep.stdout.close()
        mode_cut.stdout.close()

        # Extract the primary, decode it, and strip off carriage returns
        result = mode_awk.communicate()[0]
        mode = result.decode().strip()
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
