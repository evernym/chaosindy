import json
from indy import ledger, did, wallet, pool
from indy.error import IndyError
from os.path import expanduser, join
from chaosindy.common import *

from logzero import logger

default_pool_name = 'pool1'
default_my_wallet_name = 'my_wallet1'
default_their_wallet_name = 'their_wallet1'
wallet_credentials = json.dumps({"key": "wallet"})
pool_genesis_txn_path = '/home/lovesh/dev/chaos/pool_transactions_genesis'
seed_trustee1 = '000000000000000000000000Trustee1'
seed_steward1 = '000000000000000000000000Steward1'


# TODO: clean up (beyond closing the handle) my_wallet and their_wallet?
async def write_nym_and_check(seed=None, pool_name=None, my_wallet_name=None,
                              their_wallet_name=None, genesis_file=None):
    if seed is None:
        seed = seed_trustee1

    if pool_name is None:
        pool_name = default_pool_name

    if my_wallet_name is None:
        my_wallet_name = default_my_wallet_name

    if their_wallet_name is None:
        their_wallet_name = default_their_wallet_name

    if genesis_file is None:
        genesis_file = pool_genesis_txn_path

    logger.debug('# 0. Set protocol version to 2')
    try:
        await pool.set_protocol_version(2)
    except IndyError as e:
        logger.info("Handled IndyError")
        logger.exception(e)

    logger.debug('# 1. Create ledger config from genesis txn file')
    pool_config = json.dumps({"genesis_txn": str(genesis_file)})
    logger.debug("pool_name: %s", pool_name)
    logger.debug("pool_config: %s", pool_config)
    try:
        await pool.create_pool_ledger_config(pool_name, pool_config)
    except IndyError as e:
        logger.info("Handled IndyError")
        logger.exception(e)
        pass

    logger.debug("pool_config: %s", pool_config)
    pool_handle = await pool.open_pool_ledger(pool_name, pool_config)
    logger.debug("pool_handle is set")

    my_wallet_config = {'id': my_wallet_name}
    try:
        logger.debug("create_wallet: %s with config %s", my_wallet_name, json.dumps(my_wallet_config))
        await wallet.create_wallet(json.dumps(my_wallet_config), wallet_credentials)
    except IndyError as e:
        logger.info("Handled IndyError")
        logger.exception(e)
        pass

    my_wallet_handle = await wallet.open_wallet(json.dumps(my_wallet_config), wallet_credentials)

    logger.debug('# 4. Create Their Wallet and Get Wallet Handle')

    their_wallet_config = {'id': their_wallet_name}
    try:
        await wallet.create_wallet(json.dumps(their_wallet_config), wallet_credentials)
    except IndyError as e:
        logger.info("Handled IndyError")
        logger.info(e)
        pass

    their_wallet_handle = await wallet.open_wallet(json.dumps(their_wallet_config), wallet_credentials)

    logger.debug('# 5. Create My DID')
    (my_did, my_verkey) = await did.create_and_store_my_did(my_wallet_handle, "{}")

    logger.debug('# 6. Create Their DID from Trustee1 seed')
    (their_did, their_verkey) = await did.create_and_store_my_did(their_wallet_handle,
                                                                  json.dumps({"seed": seed_trustee1}))

    await did.store_their_did(my_wallet_handle, json.dumps({'did': their_did, 'verkey': their_verkey}))

    logger.debug('# 8. Prepare and send NYM transaction')
    nym_txn_req = await ledger.build_nym_request(their_did, my_did, None, None, None)
    await ledger.sign_and_submit_request(pool_handle, their_wallet_handle, their_did, nym_txn_req)

    logger.debug('# 9. Prepare and send GET_NYM request')
    get_nym_txn_req = await ledger.build_get_nym_request(their_did, my_did)
    get_nym_txn_resp = await ledger.submit_request(pool_handle, get_nym_txn_req)

    get_nym_txn_resp = json.loads(get_nym_txn_resp)

    assert get_nym_txn_resp['result']['dest'] == my_did

    # 10. Close wallets and pool
    await wallet.close_wallet(their_wallet_handle)
    await wallet.close_wallet(my_wallet_handle)
    await wallet.delete_wallet(json.dumps(their_wallet_config), wallet_credentials)
    await wallet.delete_wallet(json.dumps(my_wallet_config), wallet_credentials)
    await pool.close_pool_ledger(pool_handle)
    await pool.delete_pool_ledger_config(pool_name)


async def get_validator_state(seed=None, pool_name=None, wallet_name=None,
                              genesis_file=None):
    """
    Not to be confused with the validator-info script or the indy-cli
    `ledger get-validator-info`.

    This version of validator info is extracted from the pool ledger.
    """
    output_dir = get_chaos_temp_dir()

    validators = {}
    # validators is dictionary of dictionaries that maps dest to the current values of the attritubes for that dest
    #  { dest1:{'alias':value1, 'blskey':value1, ...} , dest2:{'alias':value2, 'blskey':value2, ...}, ...}

    if seed is None:
        seed = seed_steward1

    if pool_name is None:
        pool_name = default_pool_name

    if wallet_name is None:
        wallet_name = default_my_wallet_name

    if genesis_file is None:
        genesis_file = pool_genesis_txn_path

    logger.debug('# 0. Set protocol version to 2')
    try:
        await pool.set_protocol_version(2)
    except IndyError as e:
        logger.info("Handled IndyError")
        logger.exception(e)

    logger.debug('# 1. Create ledger config from genesis txn file')
    pool_config = json.dumps({"genesis_txn": str(genesis_file)})
    logger.debug("pool_name: %s", pool_name)
    logger.debug("pool_config: %s", pool_config)
    try:
        await pool.create_pool_ledger_config(pool_name, pool_config)
    except IndyError as e:
        logger.info("Handled IndyError")
        logger.exception(e)
        pass

    logger.debug("# 2. Open pool ledger - pool_config: %s", pool_config)
    pool_handle = await pool.open_pool_ledger(pool_name, pool_config)
    logger.debug("pool_handle is set")

    wallet_config = {'id': wallet_name}
    try:
        logger.debug("# 3. Create wallet %s with config %s", wallet_name,
                     json.dumps(wallet_config))
        await wallet.create_wallet(json.dumps(wallet_config), wallet_credentials)
    except IndyError as e:
        logger.info("Handled IndyError")
        logger.exception(e)
        pass

    wallet_handle = await wallet.open_wallet(json.dumps(wallet_config),
                                             wallet_credentials)

    try:
        logger.debug('# 4. Create My DID')
        did_json = json.dumps({'seed': seed})
        (my_did, my_verkey) = await did.create_and_store_my_did(wallet_handle, did_json)
    except IndyError as e:
        # TODO: Generate (my_did, my_verkey) tuple from seed (like DidUtils::create_my_did)
        my_did = "Th7MpTaRZVRYnPiabds81Y"
        logger.info("Handled IndyError")
        logger.exception(e)
        pass

    end_of_ledger = False
    current_txn = 0

    logger.info("Traversing through transactions in the pool ledger")

    while (not (end_of_ledger)):
        current_txn = current_txn + 1
        nym_transaction_request = await ledger.build_get_txn_request(
            submitter_did=my_did, seq_no=current_txn, ledger_type="POOL")

        nym_transaction_response = await ledger.sign_and_submit_request(
            pool_handle=pool_handle, wallet_handle=wallet_handle,
            submitter_did=my_did, request_json=nym_transaction_request)
        txn_json_dump = json.loads(nym_transaction_response)

        # No more transactions?
        # TODO: Determine if 'result' will always be present.
        result = txn_json_dump.get('result', None)
        if (result is None ) :
            break
        result_data = result.get('data', None)
        if (result_data is None ) :
            break

        result_data_txn_data = result_data['txn']['data']
        result_data_txn_data_data = result_data_txn_data['data']

        # Get destination field from the JSON dump of the current transaction
        #current_dest = result_data_txn_data['dest']
        current_dest = result_data_txn_data_data['alias']

        # Add destination to the dictionary if it does not exist
        if not( current_dest in validators.keys() ):
            validators[current_dest] = {}

        for key in result_data_txn_data_data.keys():
            # Update attribute value of the destination if the attributes exists in the current transaction dump
            try:
                validators[current_dest][key]  = result_data_txn_data_data[key]
            except KeyError:
                pass

        try:
            validators[current_dest]['dest']  = result_data_txn_data['dest']
        except KeyError:
            pass

        try:
            validators[current_dest]['identifier']  = result['identifier']
        except KeyError:
            pass

    logger.debug("Dumping data to validator-state state file")
    with open(join(output_dir, 'validator-state'), 'w') as json_file:
        json.dump(validators, json_file, sort_keys=True, indent=4)

    logger.debug('# 5. Close wallets and pool')
    await wallet.close_wallet(wallet_handle)
    await wallet.delete_wallet(json.dumps(wallet_config), wallet_credentials)
    await pool.close_pool_ledger(pool_handle)
    await pool.delete_pool_ledger_config(pool_name)
