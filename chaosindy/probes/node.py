import json, socket
from chaosindy.execute.execute import FabricExecutor
from chaosindy.common import get_chaos_temp_dir
from logzero import logger
from os.path import expanduser
from time import sleep

def node_ports_are_reachable(genesis_file: str, node: str) -> bool:
    """
    Are the client and node ports reachable on a given node?

    :param genesis_file: The relative or absolute path to the pool genesis
        transaction file
    :type genesis_file: str
    :param node: The node alias used to get the IP address and ports from
        genesis_file
    :type node: str
    """
    # Search for ip and node port info for both client and node port
    with open(expanduser(genesis_file), 'r') as genesisfile:
        for line in genesisfile:
            node_genesis_info = json.loads(line)
            if node_genesis_info['txn']['data']['data']['alias'] == node:
                logger.debug("Found node information for alias %s", node)
                data = node_genesis_info['txn']['data']['data']
                client_ip = data['client_ip']
                client_port = data['client_port']
                node_ip = data['node_ip']
                node_port = data['node_port']

                logger.debug("Check if client IP %s is reachable on port %d", client_ip, client_port)
                logger.debug("Node if node IP %s is reachable on port %d", node_ip, node_port)
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_sock:
                    result = client_sock.connect_ex((client_ip, client_port))
                    if result != 0:
                       logger.debug("Client port %d is not reachable at ip %s",
                                    client_port, client_ip)
                       return False
                    logger.debug("Client port %d is reachable at ip %s",
                                 client_port, client_ip)
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as node_sock:
                    result = node_sock.connect_ex((node_ip, node_port))
                    if result != 0:
                       logger.debug("Node port %d is not reachable at ip %s",
                                    node_port, node_ip)
                       return False
                    logger.debug("Node port %d is reachable at ip %s", node_port, node_ip)
                # Found matching alias. No need to keep looking.
                break
    return True
