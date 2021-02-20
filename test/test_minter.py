from pathlib import Path
from unittest import TestCase

from pytezos import michelson_to_micheline, MichelsonRuntimeError, Key
from src.ligo import LigoContract

super_admin = 'tz1irF8HUsQp2dLhKNMhteG1qALNU9g3pfdN'
user = 'tz1grSQDByRpnVs7sPtaprNZRp531ZKz6Jmm'
fees_contract = 'tz1et19hnF9qKv6yCbbxjS1QDXB5HVx6PCVk'
token_contract = 'KT1LEzyhXGKfFsczmLJdfW1p8B1XESZjMCvw'
nft_contract = 'KT1X82SpRG97yUYpyiYSWN4oPFYSq46BthCi'
other_party = 'tz3SYyWM9sq9eWTxiA8KHb36SAieVYQPeZZm'
self_address = 'KT1RXpLtz22YgX24QQhxKVyKvtKZFaAVtTB9'
dev_pool = Key.generate(export=False).public_key_hash()
staking_pool = Key.generate(export=False).public_key_hash()


class MinterTest(TestCase):
    @classmethod
    def compile_contract(cls):
        root_dir = Path(__file__).parent.parent / "ligo"
        cls.bender_contract = LigoContract(root_dir / "minter" / "main.mligo", "main").compile_contract()

    @classmethod
    def setUpClass(cls):
        cls.compile_contract()
        cls.maxDiff = None

    def _tokens_of(self, storage, addr, token_address):
        key = (addr,) + token_address
        self.assertIn(key, storage["fees"]["tokens"])
        return storage["fees"]["tokens"][key]

    def _xtz_of(self, address, storage):
        self.assertIn(address, storage["fees"]["xtz"])
        return storage["fees"]["xtz"][address]


class MinterMintErc20Test(MinterTest):

    def test_rejects_mint_if_not_signer(self):
        with self.assertRaises(MichelsonRuntimeError) as context:
            self.bender_contract.mint_erc20(mint_erc20_parameters()).interpret(
                storage=valid_storage(),
                sender=user)

        self.assertEqual("'NOT_SIGNER'", context.exception.args[-1])

    def test_cant_mint_if_paused(self):
        with self.assertRaises(MichelsonRuntimeError) as context:
            self.bender_contract.mint_erc20(mint_erc20_parameters()).interpret(
                storage=valid_storage(paused=True),
                sender=super_admin)

        self.assertEqual("'CONTRACT_PAUSED'", context.exception.args[-1])

    def test_calls_fa2_mint_for_user_and_fees_contract(self):
        amount = 1 * 10 ** 16

        res = self.bender_contract.mint_erc20(
            mint_erc20_parameters(amount=amount)).interpret(
            storage=valid_storage(fees_ratio=1),
            self_address=self_address,
            sender=super_admin)

        self.assertEqual(1, len(res.operations))
        user_mint = res.operations[0]
        self.assertEqual('0', user_mint['amount'])
        self.assertEqual(f'{token_contract}', user_mint['destination'])
        self.assertEqual('tokens', user_mint['parameters']['entrypoint'])
        collected_fees = int(0.0001 * 10 ** 16)
        self.assertEqual(michelson_to_micheline(
            f'( Right {{ Pair "{user}"  1 {int(0.9999 * 10 ** 16)}  ; Pair "{self_address}" 1 {collected_fees} }})'),
            user_mint['parameters']['value'])
        self.assertEqual(collected_fees, self._tokens_of(res.storage, self_address, (token_contract, 1)))

    def test_generates_only_one_mint_if_fees_to_low(self):
        amount = 1

        res = self.bender_contract.mint_erc20(
            mint_erc20_parameters(amount=amount)).interpret(
            storage=valid_storage(fees_ratio=1),
            sender=super_admin)

        self.assertEqual(1, len(res.operations))
        user_mint = res.operations[0]
        self.assertEqual(michelson_to_micheline(
            f'( Right {{ Pair "{user}" 1 {amount}}})'),
            user_mint['parameters']['value'])

    def test_cannot_replay_same_tx(self):
        with self.assertRaises(MichelsonRuntimeError) as context:
            self.bender_contract.mint_erc20(
                mint_erc20_parameters(block_hash=b'aTx', log_index=3)).interpret(
                storage=valid_storage(mints={(b'aTx', 3): None}),
                sender=super_admin)
        self.assertEqual("'TX_ALREADY_MINTED'", context.exception.args[-1])

    def test_saves_tx_id(self):
        block_hash = bytes.fromhex("386bf131803cba7209ff9f43f7be0b1b4112605942d3743dc6285ee400cc8c2d")
        log_index = 5

        res = self.bender_contract.mint_erc20(
            mint_erc20_parameters(block_hash=block_hash, log_index=log_index)).interpret(
            storage=valid_storage(),
            sender=super_admin)

        self.assertIn((block_hash, log_index), res.storage["assets"]["mints"])


class MinterUwrapErc20Test(MinterTest):

    def test_cannot_unwrap_if_paused(self):
        with self.assertRaises(MichelsonRuntimeError) as context:
            self.bender_contract.unwrap_erc20(
                unwrap_fungible_parameters()).interpret(
                storage=valid_storage(paused=True),
                sender=super_admin)
        self.assertEqual("'CONTRACT_PAUSED'", context.exception.args[-1])

    def test_rejects_unwrap_with_fees_to_low(self):
        amount = 100
        fees = 1
        with self.assertRaises(MichelsonRuntimeError) as context:
            self.bender_contract.unwrap_erc20(
                unwrap_fungible_parameters(amount=amount, fees=fees)).interpret(
                storage=valid_storage(fees_ratio=200),
                source=user
            )
        self.assertEqual("'FEES_TOO_LOW'", context.exception.args[-1])

    def test_rejects_unwrap_for_small_amount(self):
        amount = 10
        fees = 1
        with self.assertRaises(MichelsonRuntimeError) as context:
            self.bender_contract.unwrap_erc20(
                unwrap_fungible_parameters(amount=amount, fees=fees)).interpret(
                storage=valid_storage(fees_ratio=200),
                source=user
            )
        self.assertEqual("'AMOUNT_TOO_SMALL'", context.exception.args[-1])

    def test_unwrap_amount_for_account_and_distribute_fees(self):
        amount = 100
        fees = 1

        res = self.bender_contract.unwrap_erc20(
            unwrap_fungible_parameters(amount=amount, fees=fees)).interpret(
            storage=valid_storage(fees_ratio=100),
            self_address=self_address,
            source=user
        )

        self.assertEqual(2, len(res.operations))
        burn_operation = res.operations[0]
        self.assertEqual('0', burn_operation['amount'])
        self.assertEqual(f'{token_contract}', burn_operation['destination'])
        self.assertEqual('tokens', burn_operation['parameters']['entrypoint'])
        self.assertEqual(michelson_to_micheline(f'(Left {{ Pair "{user}" 1 {amount + fees} }})'),
                         burn_operation['parameters']['value'])
        mint_operation = res.operations[1]
        self.assertEqual('0', mint_operation['amount'])
        self.assertEqual(f'{token_contract}', mint_operation['destination'])
        self.assertEqual('tokens', mint_operation['parameters']['entrypoint'])
        self.assertEqual(michelson_to_micheline(f'(Right {{ Pair "{self_address}" 1 {fees} }})'),
                         mint_operation['parameters']['value'])
        self.assertIn((self_address, token_contract, 1), res.storage["fees"]["tokens"])
        self.assertEqual(fees, self._tokens_of(res.storage, self_address, (token_contract, 1)))


class MinterERC721Test(MinterTest):

    def test_calls_erc721_mint(self):
        res = self.bender_contract.mint_erc721(mint_erc721_parameters(token_id=5)) \
            .interpret(storage=valid_storage(nft_fees=20), sender=super_admin, amount=20, self_address=self_address)

        self.assertEqual(1, len(res.operations))
        user_mint = res.operations[0]
        self.assertEqual('0', user_mint['amount'])
        self.assertEqual(f'{nft_contract}', user_mint['destination'])
        self.assertEqual('tokens', user_mint['parameters']['entrypoint'])
        self.assertEqual(michelson_to_micheline(
            f'( Right {{ Pair "{user}" 5 1 }})'),
            user_mint['parameters']['value'])
        self.assertEqual(20, self._xtz_of(self_address, res.storage))

    def test_unwrap_nft(self):
        token_id = 1337
        fees = 10

        res = self.bender_contract.unwrap_erc721(
            unwrap_nft_parameters(token_id=token_id)).interpret(
            storage=valid_storage(nft_fees=fees),
            source=user,
            amount=10,
            self_address=self_address
        )

        self.assertEqual(1, len(res.operations))
        burn_operation = res.operations[0]
        self.assertEqual('0', burn_operation['amount'])
        self.assertEqual(f'{nft_contract}', burn_operation['destination'])
        self.assertEqual('tokens', burn_operation['parameters']['entrypoint'])
        self.assertEqual(michelson_to_micheline(f'(Left {{ Pair "{user}" 1337 1}})'),
                         burn_operation['parameters']['value'])
        self.assertEqual(10, self._xtz_of(self_address, res.storage))


class MinterGovernanceTest(MinterTest):

    def test_set_wrapping_fees(self):
        res = self.bender_contract.set_erc20_wrapping_fees(10).interpret(
            storage=valid_storage(),
            source=super_admin
        )

        self.assertEqual(10, res.storage['governance']['erc20_wrapping_fees'])

    def test_set_unwrapping_fees(self):
        res = self.bender_contract.set_erc20_unwrapping_fees(10).interpret(
            storage=valid_storage(),
            source=super_admin
        )

        self.assertEqual(10, res.storage['governance']['erc20_unwrapping_fees'])

    def test_set_governance(self):
        res = self.bender_contract.set_governance(user).interpret(
            storage=valid_storage(),
            source=super_admin
        )

        self.assertEqual(user, res.storage['governance']['contract'])


class MinterAdminTest(MinterTest):

    def test_changes_administrator(self):
        res = self.bender_contract.set_administrator(other_party).interpret(storage=valid_storage(),
                                                                            sender=super_admin)
        self.assertEqual(res.storage['admin']['administrator'], other_party)

    def test_can_pause(self):
        res = self.bender_contract.pause_contract(True) \
            .interpret(storage=valid_storage(), source=super_admin)

        self.assertEqual(True, res.storage['admin']['paused'])


class MinterTokenTest(MinterTest):

    def test_rejects_xtz_transfer(self):
        with self.assertRaises(MichelsonRuntimeError) as context:
            self.bender_contract.set_administrator(other_party).interpret(storage=valid_storage(),
                                                                          sender=super_admin,
                                                                          amount=10
                                                                          )
        self.assertEqual("'FORBIDDEN_XTZ'", context.exception.args[-1])

    def test_add_fungible_token(self):
        res = self.bender_contract.add_erc20({
            "eth_contract": b"ethContract",
            "token_address": ["KT19RiH4xg7vjgxeBeFU5eBmhS5W9bcpDwL6", 2]
        }).interpret(
            storage=valid_storage(tokens={}),
            source=super_admin
        )

        self.assertIn(b'ethContract', res.storage['assets']['erc20_tokens'])
        self.assertEqual(("KT19RiH4xg7vjgxeBeFU5eBmhS5W9bcpDwL6", 2),
                         res.storage['assets']['erc20_tokens'][b'ethContract'])
        self.assertEqual(0, len(res.operations))

    def test_add_nft(self):
        res = self.bender_contract.add_erc721({
            "eth_contract": b"ethContract",
            "token_contract": "KT19RiH4xg7vjgxeBeFU5eBmhS5W9bcpDwL6"
        }).interpret(
            storage=valid_storage(tokens={}),
            source=super_admin
        )

        self.assertIn(b'ethContract', res.storage['assets']['erc721_tokens'])
        self.assertEqual("KT19RiH4xg7vjgxeBeFU5eBmhS5W9bcpDwL6",
                         res.storage['assets']['erc721_tokens'][b'ethContract'])
        self.assertEqual(0, len(res.operations))

    def test_confirm_fa2_admin(self):
        res = self.bender_contract.confirm_tokens_administrator([token_contract]).interpret(storage=valid_storage(),
                                                                                            source=super_admin)

        self.assertEqual(1, len(res.operations))
        op = res.operations[0]
        self.assertEqual(token_contract, op["destination"])
        self.assertEqual("admin", op["parameters"]["entrypoint"])
        self.assertEqual(michelson_to_micheline('(Left (Left Unit))'), op["parameters"]["value"])

    def test_pause_token(self):
        res = self.bender_contract.pause_tokens([{"contract": token_contract, "tokens": [1], "paused": True}]) \
            .interpret(storage=valid_storage(), source=super_admin)

        self.assertEqual(1, len(res.operations))
        op_fungible = res.operations[0]
        self.assertEqual(token_contract, op_fungible["destination"])
        self.assertEqual("admin", op_fungible["parameters"]["entrypoint"])
        self.assertEqual(michelson_to_micheline('(Left (Right {  Pair 1 True } ))'),
                         op_fungible["parameters"]["value"])

    def test_change_token_admin(self):
        res = self.bender_contract.change_tokens_administrator(user, [token_contract, nft_contract]) \
            .interpret(storage=valid_storage(), source=super_admin)

        self.assertEqual(2, len(res.operations))
        op = res.operations[0]
        self.assertEqual(token_contract, op["destination"])
        self.assertEqual("admin", op["parameters"]["entrypoint"])
        self.assertEqual(michelson_to_micheline(f'(Right "{user}")'),
                         op["parameters"]["value"])
        op = res.operations[1]
        self.assertEqual(nft_contract, op["destination"])
        self.assertEqual("admin", op["parameters"]["entrypoint"])
        self.assertEqual(michelson_to_micheline(f'(Right "{user}")'),
                         op["parameters"]["value"])


signer_1_key = Key.generate(export=False).public_key_hash()
signer_2_key = Key.generate(export=False).public_key_hash()
signer_3_key = Key.generate(export=False).public_key_hash()


class MinterFeesDistributionTest(MinterTest):

    def test_distribute_xtz_to_dev(self):
        initial_storage = valid_storage()
        with_xtz_to_distribute(100, initial_storage)
        initial_storage["fees"]["xtz"][dev_pool] = 50

        res = self.bender_contract.distribute_xtz([]).interpret(storage=initial_storage,
                                                                sender=super_admin,
                                                                self_address=self_address)

        self.assertEqual(60, self._xtz_of(dev_pool, res.storage))

    def test_distribute_xtz_to_staking(self):
        initial_storage = valid_storage()
        with_xtz_to_distribute(100, initial_storage)

        res = self.bender_contract.distribute_xtz([]).interpret(storage=initial_storage,
                                                                sender=super_admin,
                                                                self_address=self_address)

        self.assertEqual(40, self._xtz_of(staking_pool, res.storage))

    def test_distribute_xtz_to_signer_default_payment_address(self):
        initial_storage = valid_storage()
        with_xtz_to_distribute(100, initial_storage)

        res = self.bender_contract.distribute_xtz([signer_1_key]).interpret(storage=initial_storage,
                                                                            sender=super_admin,
                                                                            self_address=self_address)

        self.assertEqual(50, self._xtz_of(signer_1_key, res.storage))
        self.assertEqual(0, self._xtz_of(self_address, res.storage))

    def test_distribute_xtz_to_signer_registered_payment_address(self):
        signer_1_payment_address = Key.generate(export=False).public_key_hash()
        initial_storage = valid_storage()
        with_xtz_to_distribute(100, initial_storage)
        initial_storage["fees"]["signers"][signer_1_key] = signer_1_payment_address

        res = self.bender_contract.distribute_xtz([signer_1_key]).interpret(storage=initial_storage,
                                                                            sender=super_admin,
                                                                            self_address=self_address)

        self.assertEqual(50, self._xtz_of(signer_1_payment_address, res.storage))

    def test_distribute_xtz_to_several_signers_and_keeps_remaining_to_distribute(self):
        initial_storage = valid_storage()
        with_xtz_to_distribute(100, initial_storage)

        res = self.bender_contract.distribute_xtz([signer_1_key, signer_2_key, signer_3_key]).interpret(
            storage=initial_storage,
            sender=super_admin,
            self_address=self_address)

        self.assertEqual(16, self._xtz_of(signer_1_key, res.storage))
        self.assertEqual(16, self._xtz_of(signer_2_key, res.storage))
        self.assertEqual(16, self._xtz_of(signer_3_key, res.storage))
        self.assertEqual(2, self._xtz_of(self_address, res.storage))

    def test_distribute_tokens_to_dev_pool(self):
        initial_storage = valid_storage()
        token_address = (token_contract, 0)
        with_token_to_distribute(initial_storage, token_address, 100)
        initial_storage["fees"]["tokens"][(dev_pool, token_contract, 0)] = 10

        res = self.bender_contract.distribute_tokens([], [token_address]).interpret(storage=initial_storage,
                                                                                    sender=super_admin,
                                                                                    self_address=self_address)

        self.assertEqual(50, self._tokens_of(res.storage, self_address, token_address))
        self.assertEqual(20, self._tokens_of(res.storage, dev_pool, token_address))

    def test_distribute_tokens_to_staking(self):
        initial_storage = valid_storage()
        token_address = (token_contract, 0)
        with_token_to_distribute(initial_storage, token_address, 100)
        initial_storage["fees"]["tokens"][(staking_pool, token_contract, 0)] = 40

        res = self.bender_contract.distribute_tokens([], [token_address]).interpret(storage=initial_storage,
                                                                                    sender=super_admin,
                                                                                    self_address=self_address)

        self.assertEqual(80, self._tokens_of(res.storage, staking_pool, token_address))

    def test_distribute_tokens_to_signer(self):
        initial_storage = valid_storage()
        token_address = (token_contract, 0)
        with_token_to_distribute(initial_storage, token_address, 100)
        initial_storage["fees"]["tokens"][(signer_1_key, token_contract, 0)] = 40

        res = self.bender_contract.distribute_tokens([signer_1_key], [token_address]).interpret(storage=initial_storage,
                                                                                                sender=super_admin,
                                                                                                self_address=self_address)

        self.assertEqual(90, self._tokens_of(res.storage, signer_1_key, token_address))
        self.assertEqual(0, self._tokens_of(res.storage, self_address, token_address))

    def test_distribute_several_tokens(self):
        initial_storage = valid_storage()
        first_token = (token_contract, 0)
        second_token = (token_contract, 1)
        with_token_to_distribute(initial_storage, first_token, 100)
        with_token_to_distribute(initial_storage, second_token, 200)

        res = self.bender_contract.distribute_tokens([], [first_token, second_token]).interpret(storage=initial_storage,
                                                                                                self_address=self_address,
                                                                                                sender=super_admin)

        self.assertEqual(10, self._tokens_of(res.storage, dev_pool, first_token))
        self.assertEqual(20, self._tokens_of(res.storage, dev_pool, second_token))


def with_xtz_to_distribute(amount, initial_storage):
    initial_storage["fees"]["xtz"][self_address] = amount


def with_token_to_distribute(initial_storage, token_address, amount):
    initial_storage["fees"]["tokens"][(self_address,) + token_address] = amount


def valid_storage(mints=None, fees_ratio=0, nft_fees=1, tokens=None, paused=False):
    if mints is None:
        mints = {}
    if tokens is None:
        tokens = {b'BOB': [token_contract, 1]}
    return {
        "admin": {
            "administrator": super_admin,
            "signer": super_admin,
            "paused": paused
        },
        "assets": {
            "erc20_tokens": tokens,
            "erc721_tokens": {b'NFT': nft_contract},
            "mints": mints
        },
        "governance": {
            "contract": super_admin,
            "staking": staking_pool,
            "dev_pool": dev_pool,
            "erc20_wrapping_fees": fees_ratio,
            "erc20_unwrapping_fees": fees_ratio,
            "erc721_wrapping_fees": nft_fees,
            "erc721_unwrapping_fees": nft_fees,
            "fees_share": {
                "dev_pool": 10,
                "staking": 40,
                "signers": 50
            }
        },
        "fees": {
            "signers": {},
            "tokens": {},
            "xtz": {}
        },
        "metadata": {}
    }


def mint_erc20_parameters(
        block_hash=bytes.fromhex("e1286c8cdafc9462534bce697cf3bf7e718c2241c6d02763e4027b072d371b7c"),
        log_index=1,
        owner=user,
        amount=2):
    return {"erc_20": b'BOB',
            "event_id": {"block_hash": block_hash, "log_index": log_index},
            "owner": owner,
            "amount": amount
            }


def mint_erc721_parameters(block_hash=bytes.fromhex("e1286c8cdafc9462534bce697cf3bf7e718c2241c6d02763e4027b072d371b7c"),
                           log_index=1,
                           owner=user,
                           token_id=2):
    return {"erc_721": b'NFT',
            "event_id": {"block_hash": block_hash, "log_index": log_index},
            "owner": owner,
            "token_id": token_id
            }


def unwrap_fungible_parameters(amount=2, fees=1):
    return {"erc_20": b'BOB',
            "amount": amount,
            "fees": fees,
            "destination": b"ethAddress"
            }


def unwrap_nft_parameters(token_id=2):
    return {"erc_721": b'NFT',
            "token_id": token_id,
            "destination": b"ethAddress"
            }
