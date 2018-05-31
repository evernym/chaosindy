import os
import json
from chaosindy.execute.execute import FabricExecutor


# TODO: Abstract the body of this function to common module and share between
#       all_nodes_up action and probe
def all_nodes_up(genesis_file, ssh_config_file="~/.ssh/config"):
    print("genesis_file:", genesis_file, "ssh_config_file:", ssh_config_file)
    # 1. Open genesis_file and load all aliases into an array
    aliases = []
    with open(os.path.expanduser(genesis_file), 'r') as genesisfile:
        for line in genesisfile:
            aliases.append(json.loads(line)['data']['alias'])
    print(aliases)

    executor = FabricExecutor(ssh_config_file=os.path.expanduser(ssh_config_file))

    # 2. Start all nodes.
    count = len(aliases)
    print("Restarting all", count, "nodes...")
    tried_to_start = 0
    are_alive = 0
    for alias in aliases:
        print("alias to start:", alias)
        result = executor.execute(alias, "systemctl status indy-node", as_sudo=True)
        if result.return_code == 0:
            are_alive += 1
        tried_to_start += 1

    print("are_alive:", are_alive, "count:", count, "tried_to_start:", tried_to_start, "len-aliases:", len(aliases))
    if are_alive < int(count):
        return False

    return True