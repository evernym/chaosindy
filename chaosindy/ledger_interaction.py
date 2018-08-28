import json
from indy import ledger, did, wallet, pool
from indy.error import IndyError, ErrorCode
from os.path import expanduser, join
from chaosindy.common import *
from logzero import logger
from datetime import datetime


# NOTE: Workaround: Until https://jira.hyperledger.org/browse/IS-903 is
#       completed, create, populate, use and then delete a new wallet each time
#       write_nym_and_check is called.
async def write_nym_and_check(seed: str = None, pool_name: str = None,
                              my_wallet_name: str = None,
                              my_wallet_key: str = None,
                              their_wallet_name: str = None,
                              their_wallet_key: str = None,
                              genesis_file: str = None,
                              cleanup=True) -> None:
    """
    Write a NYM to the ledger.

    Write a NYM to the ledger and confirm/check that it was successfull by
    reading the NYM from the ledger. Not idempotent.

    :param seed: 32 byte string used to generate did, verkey pair. The seed must
        be the seed for a Trustee, Steward, or Trust Anchor.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SEED)
    :type seed: str
    :param pool_name: Pool name
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_POOL)
    :type pool_name: str
    :param my_wallet_name: My wallet name
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_MY_WALLET_NAM)
    :type my_wallet_name: str
    :param my_wallet_key: My wallet key
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_WALLET_KEY)
    :type my_wallet_key: str
    :param their_wallet_name: Their wallet name
        Optional. (Default: chaosindy.common.DEFAULT_THEIR_WALLET_NAME)
    :type their_wallet_name: str
    :param their_wallet_key: Their wallet key
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_WALLET_KEY)
    :type their_wallet_key: str
    :param genesis_file: Relative or absolute path to the pool's genesis
        transaction file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_GENESIS_FILE)
    :type genesis_file: str
    :param cleanup: Delete wallets and pool configuration?
        Optional. (Default: True)
    :type cleanup: bool
    :return: None
    """
    # TODO: validate inputs
    if seed is None:
        seed = DEFAULT_CHAOS_SEED

    if pool_name is None:
        pool_name = DEFAULT_CHAOS_POOL

    if my_wallet_name is None:
        my_wallet_name = DEFAULT_CHAOS_MY_WALLET_NAME

    now = datetime.now()
    my_wallet_name = "{}-{}".format(my_wallet_name,
                                    now.strftime("%Y%m%dT%H%M%S"))

    if my_wallet_key is None:
        my_wallet_key = DEFAULT_CHAOS_WALLET_KEY

    if their_wallet_name is None:
        their_wallet_name = DEFAULT_CHAOS_THEIR_WALLET_NAME

    their_wallet_name = "{}-{}".format(my_wallet_name,
                                       now.strftime("%Y%m%dT%H%M%S"))

    if their_wallet_key is None:
        their_wallet_key = DEFAULT_CHAOS_WALLET_KEY

    if genesis_file is None:
        genesis_file = DEFAULT_CHAOS_GENEIS_FILE

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
        #logger.exception(e)
        pass

    logger.debug("pool_config: %s", pool_config)
    pool_handle = await pool.open_pool_ledger(pool_name, "{}")
    logger.debug("pool_handle is set")

    my_wallet_config = json.dumps({'id': my_wallet_name})
    my_wallet_credentials = json.dumps({"key": my_wallet_key})
    try:
        logger.debug("create_wallet: %s with config %s", my_wallet_name,
                     my_wallet_config)
        await wallet.create_wallet(my_wallet_config, my_wallet_credentials)
    except IndyError as e:
        logger.info("Handled IndyError")
        #logger.exception(e)
        pass

    my_wallet_handle = await wallet.open_wallet(my_wallet_config,
                                                my_wallet_credentials)

    logger.debug('# 4. Create Their Wallet and Get Wallet Handle')

    their_wallet_config = json.dumps({'id': their_wallet_name})
    their_wallet_credentials = json.dumps({'key': their_wallet_key})
    try:
        await wallet.create_wallet(their_wallet_config,
                                   their_wallet_credentials)
    except IndyError as e:
        logger.info("Handled IndyError")
        logger.info(e)
        pass

    their_wallet_handle = await wallet.open_wallet(their_wallet_config,
                                                   their_wallet_credentials)

    logger.debug('# 5. Create My DID')
    (my_did, my_verkey) = await did.create_and_store_my_did(my_wallet_handle,
                                                            "{}")

    logger.debug('# 6. Create Their DID from Trustee1 seed')
    try:
        (their_did, their_verkey) = await did.create_and_store_my_did(
            their_wallet_handle, json.dumps({"seed": seed}))
    except IndyError as e:
        if e.error_code == ErrorCode.DidAlreadyExistsError:
            # TODO: Generate (their_did, their_verkey) tuple from seed (like
            #       DidUtils::create_my_did)
            logger.info("Handled DidAlreadyExistsError exception...")
            pass
        else:
            logger.exception(e)
            raise e

    their_dict = {'did': their_did, 'verkey': their_verkey}
    await did.store_their_did(my_wallet_handle, json.dumps(their_dict))

    logger.debug('# 8. Prepare and send NYM transaction')
    nym_txn_req = await ledger.build_nym_request(their_did, my_did, None, None,
                                                 None)
    await ledger.sign_and_submit_request(pool_handle, their_wallet_handle,
                                         their_did, nym_txn_req)

    logger.debug('# 9. Prepare and send GET_NYM request')
    get_nym_txn_req = await ledger.build_get_nym_request(their_did, my_did)
    get_nym_txn_resp = await ledger.submit_request(pool_handle, get_nym_txn_req)

    get_nym_txn_resp = json.loads(get_nym_txn_resp)

    assert get_nym_txn_resp['result']['dest'] == my_did

    # 10. Close wallets and pool
    await wallet.close_wallet(their_wallet_handle)
    await wallet.close_wallet(my_wallet_handle)
    await pool.close_pool_ledger(pool_handle)

    if cleanup:
        try:
            await wallet.delete_wallet(their_wallet_config,
                                       their_wallet_credentials)
        except Exception as e:
            logger.info("Best-effort deletion of wallet %s failed.",
                        their_wallet_name)
            #logger.exception(e)
            pass

        try:
            await wallet.delete_wallet(my_wallet_config, my_wallet_credentials)
        except Exception as e:
            logger.info("Best-effort deletion of wallet %s failed.",
                        my_wallet_name)
            #logger.exception(e)
            pass


        try:
            await pool.delete_pool_ledger_config(pool_name)
        except Exception as e:
            logger.info("Best-effort deletion of %s pool ledger config failed.",
                        pool_name)
            #logger.exception(e)
            pass


# NOTE: Workaround: Until https://jira.hyperledger.org/browse/IS-903 is
#       completed, create, populate, use and then delete a new wallet each time
#       write_nym_and_check is called.
async def get_validator_state(genesis_file: str = None, seed: str = None,
                              pool_name: str = None, wallet_name: str = None,
                              wallet_key: str = None, cleanup=True) -> None:
    """
    Not to be confused with the validator-info script or the indy-cli
    `ledger get-validator-info`.

    This version of validator info is extracted from the pool ledger.

    :param genesis_file: Relative or absolute path to the pool's genesis
        transaction file.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_GENESIS_FILE)
    :type genesis_file: str
    :param seed: 32 byte string used to generate did, verkey pair.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_SEED)
    :type seed: str
    :param pool_name: Pool name.
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_POOL)
    :type pool_name: str
    :param wallet_name: Wallet name
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_WALLET_NAME)
    :type wallet_name: str
    :param wallet_key: Wallet key
        Optional. (Default: chaosindy.common.DEFAULT_CHAOS_WALLET_KEY)
    :type wallet_key: str
    :param cleanup: Delete the wallet and pool configuration?
        Optional. (Default: True)
    :type cleanup: bool
    :return: None
    """
    output_dir = get_chaos_temp_dir()
    validators = {}
    # validators is a dictionary of dictionaries that maps dest to the current
    # values of the attritubes for that dest
    #  {
    #    dest1:{'alias':value1, 'blskey':value1, ...},
    #    dest2:{'alias':value2, 'blskey':value2, ...},
    #    ...
    #  }

    if seed is None:
        seed = DEFAULT_CHAOS_STEWARD_SEED

    if pool_name is None:
        pool_name = DEFAULT_CHAOS_POOL

    if wallet_name is None:
        wallet_name = DEFAULT_CHAOS_WALLET_NAME

    now = datetime.now()
    wallet_name = "{}-{}".format(wallet_name,
                                 now.strftime("%Y%m%dT%H%M%S"))

    if wallet_key is None:
        wallet_key = DEFAULT_CHAOS_WALLET_KEY

    if genesis_file is None:
        genesis_file = DEFAULT_CHAOS_GENEIS_FILE

    logger.debug('# 0. Set protocol version to 2')
    try:
        await pool.set_protocol_version(2)
    except IndyError as e:
        logger.info("Handled IndyError")
        logger.exception(e)
        pass

    logger.debug('# 1. Create ledger config from genesis txn file')
    pool_config = json.dumps({"genesis_txn": str(genesis_file)})
    logger.debug("pool_name: %s", pool_name)
    logger.debug("pool_config: %s", pool_config)
    try:
        await pool.create_pool_ledger_config(pool_name, pool_config)
    except IndyError as e:
        logger.info("Handled IndyError")
        #logger.exception(e)
        pass

    logger.debug("# 2. Open pool ledger - pool_config: %s", pool_config)
    pool_handle = await pool.open_pool_ledger(pool_name, "{}")
    logger.debug("pool_handle is set")

    wallet_config = json.dumps({'id': wallet_name})
    wallet_credentials = json.dumps({'key': wallet_key})
    try:
        logger.debug("# 3. Create wallet %s with config %s credentials %s",
                     wallet_name, wallet_config, wallet_credentials)
        await wallet.create_wallet(wallet_config, wallet_credentials)
    except IndyError as e:
        logger.info("Handled IndyError")
        #logger.exception(e)
        pass

    wallet_handle = await wallet.open_wallet(wallet_config, wallet_credentials)

    try:
        logger.debug('# 4. Create My DID')
        did_json = json.dumps({'seed': seed})
        (my_did, my_verkey) = await did.create_and_store_my_did(wallet_handle,
                                                                did_json)
    except IndyError as e:
        if e.error_code == ErrorCode.DidAlreadyExistsError:
            # TODO: Generate (their_did, their_verkey) tuple from seed (like
            #       DidUtils::create_my_did)
            #my_did = "Th7MpTaRZVRYnPiabds81Y"
            logger.info("Handled DidAlreadyExistsError exception...")
            pass
        else:
            logger.exception(e)
            raise e
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
            # Update attribute value of the destination if the attributes exists
            # in the current transaction dump
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

    logger.debug('# 5. Close wallet and pool')
    await wallet.close_wallet(wallet_handle)
    await pool.close_pool_ledger(pool_handle)

    if cleanup:
        try:
            await wallet.delete_wallet(wallet_config, wallet_credentials)
        except Exception as e:
            logger.info("Best-effort deletion of wallet %s failed.",
                        wallet_name)
            #logger.exception(e)
            pass

        try:
            await pool.delete_pool_ledger_config(pool_name)
        except Exception as e:
            logger.info("Best-effort deletion of %s pool ledger config failed.",
                        pool_name)
            #logger.exception(e)
            pass
