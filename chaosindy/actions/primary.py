import json
from chaosindy.execute.execute import FabricExecutor
from chaosindy.probes.validator_info import get_chaos_temp_dir, get_validator_info, detect_primary
from chaosindy.actions.node import stop_node_by_name, start_all_but_node_by_name

def get_primary(genesis_file, ssh_config_file="~/.ssh/config", compile_stats=True):
    primary = None
    if compile_stats:
        detect_primary(genesis_file, ssh_config_file=ssh_config_file)

    output_dir = get_chaos_temp_dir()
    with open("{}/primaries".format(output_dir), 'r') as primaries:
        primary_dict = json.load(primaries)
    primary = primary_dict.get("current_primary", None)

    return primary

def stop_primary(genesis_file, ssh_config_file="~/.ssh/config", compile_stats=True):
    primary = get_primary(genesis_file, compile_stats=compile_stats,
                          ssh_config_file=ssh_config_file)
    if primary:
        return stop_node_by_name(primary, ssh_config_file=ssh_config_file)
    return False

def start_all_but_primary(genesis_file, ssh_config_file="~/.ssh/config", compile_stats=False):
    primary = get_primary(genesis_file, compile_stats=compile_stats,
                          ssh_config_file=ssh_config_file)
    if primary:
        return start_all_but_node_by_name(primary, genesis_file=genesis_file, ssh_config_file=ssh_config_file)

    return False
