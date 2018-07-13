import json

from indy import ledger, did, wallet, pool
from indy.error import IndyError

from logzero import logger

default_pool_name = 'pool1'
default_my_wallet_name = 'my_wallet1'
default_their_wallet_name = 'their_wallet1'
wallet_credentials = json.dumps({"key": "wallet"})
pool_genesis_txn_path = '/home/lovesh/dev/chaos/pool_transactions_genesis'
seed_trustee1 = '000000000000000000000000Trustee1'


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

    my_wallet_config = {'id': my_wallet_name}
    try:
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
