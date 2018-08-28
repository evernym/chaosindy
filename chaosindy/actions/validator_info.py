import json
from chaosindy.common import (
    get_chaos_temp_dir,
    DEFAULT_CHAOS_SSH_CONFIG_FILE,
    true_list, false_list
)
from logzero import logger
from os.path import expanduser, join
from os import remove
from shutil import rmtree

def delete_validator_info(genesis_file: str = None, cleanup: str = "True",
    ssh_config_file:str = DEFAULT_CHAOS_SSH_CONFIG_FILE) -> bool:
    """
    All experiments depend on validator-info for each node. This function allows
    experiment writers the option to cleanup the entire temp directory used by
    and experiment or just delete the validator info files in an experiment's
    temp directory.

    Delete temporary directory containing validator info or just validator info
    files created in the temporary directory.

    :param genesis_file: Relative or absolute path to the pool's genesis
        transaction file.
        Optional. (Default: None)
    :type genesis_file: str
    :param cleanup: Delete an experiment's temp files and/or directory?
        Optional. (Default: "True")
        Valid inputs (case insensitive): 'false', '0', 'f', 'n', 'no', 'true',
        '1', 't', 'y', 'yes'
    :type cleanup: str
    :param ssh_config_file: The relative or absolute path to the
        ssh_config_file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SSH_CONFIG_FILE)
    :type ssh_config_file: str
    :return: bool
    """
    output_dir = get_chaos_temp_dir()

    if cleanup.lower() in false_list:
        logger.debug("Skipping cleanup. You will be expected to remove %s",
                     output_dir)
        return True

    if genesis_file:
        logger.debug("genesis_file: %s ssh_config_file: %s", genesis_file,
                     ssh_config_file)
        # 1. Open genesis_file and load all aliases into an array
        aliases = []
        with open(expanduser(genesis_file), 'r') as genesisfile:
            for line in genesisfile:
                aliases.append(json.loads(line)['data']['alias'])
        logger.debug(str(aliases))

        # 2. Delete validator info collected by the experiment
        count = len(aliases)
        logger.debug("Deleting validator data collected for experiment from " \
                     "all %i nodes...", count)
        tried_to_delete= 0
        are_deleted = 0
        for alias in aliases:
            logger.debug("alias to delete validator info: %s", alias)
            tried_to_delete += 1
            remove(join(output_dir, "{}-validator-info".format(alias)))
            are_deleted += 1

        logger.debug("are_deleted: %s count: %i tried_to_delete: %i " \
                     "len-aliases: %i", are_deleted, count, tried_to_delete,
                     len(aliases))
        if are_deleted < int(count):
            return False
    else:
        try:
            rmtree(output_dir)
        except Exception as e:
            logger.error("Failed to cleanup %s with error exception",
                         output_dir)
            logger.exception(e)
            return False

    return True
