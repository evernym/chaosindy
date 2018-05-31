import os
import json
import random
from chaosindy.execute.execute import FabricExecutor


# TODO: abstract the body of ensure_nodes_up and kill_random_nodes into
#       a execute_random_looper object and create a 'common.py' module
def kill_random_nodes(genesis_file, count, ssh_config_file="~/.ssh/config"):
    print("genesis_file:", genesis_file, "count:", count)
    # 1. Open genesis_file and load all aliases into an array
    aliases = []
    with open(os.path.expanduser(genesis_file), 'r') as genesisfile:
        for line in genesisfile:
            aliases.append(json.loads(line)['data']['alias'])
    print(aliases)

    executor = FabricExecutor(ssh_config_file=os.path.expanduser(ssh_config_file))

    # 2. Kill 'count' nodes. It is okay to count a node if the service is already dead/stopped
    tried_to_kill = 0
    are_dead = 0
    number_of_aliases = len(aliases)
    while are_dead < int(count) and tried_to_kill < number_of_aliases:
        target = random.choice(aliases)
        aliases.remove(target)
        print("target alias to kill:", target)
        result = executor.execute(target, "systemctl stop indy-node", as_sudo=True)
        if result.return_code in [0, 3]:
            are_dead += 1
        tried_to_kill += 1

    print("are_dead:", are_dead, "count:", count, "tried_to_kill:", tried_to_kill, "len-aliases:", number_of_aliases)
    if are_dead < int(count):
        return False

    return True
