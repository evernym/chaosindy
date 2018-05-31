import os
import json
import random
from chaosindy.execute.execute import FabricExecutor


# TODO: abstract the body of ensure_nodes_up and kill_random_nodes into
#       a execute_random_looper object and create a 'common.py' module
def ensure_nodes_up(genesis_file, count, ssh_config_file="~/.ssh/config"):
    print("genesis_file:", genesis_file, "count:", count, "ssh_config_file:", ssh_config_file)
    # 1. Open genesis_file and load all aliases into an array
    aliases = []
    with open(os.path.expanduser(genesis_file), 'r') as genesisfile:
        for line in genesisfile:
            aliases.append(json.loads(line)['data']['alias'])
    print(aliases)

    executor = FabricExecutor(ssh_config_file=os.path.expanduser(ssh_config_file))

    # 2. Start 'count' nodes. It is okay to count a node if the service is already alive/started
    tried_to_start = 0
    are_alive = 0
    number_of_aliases = len(aliases)
    while are_alive < int(count) and tried_to_start < number_of_aliases:
        target = random.choice(aliases)
        aliases.remove(target)
        print("target alias to start:", target)
        result = executor.execute(target, "systemctl start indy-node", as_sudo=True)
        if result.return_code == 0:
            are_alive += 1
        tried_to_start += 1

    print("are_alive:", are_alive, "count:", count, "tried_to_start:", tried_to_start, "len-aliases:", number_of_aliases)
    if are_alive < int(count):
        return False

    return True
