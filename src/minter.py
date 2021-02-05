from src.ligo import PtzUtils


class Minter(object):

    def __init__(self, client: PtzUtils):
        self.utils = client

    def unwrap_erc20(self, contract_id, erc_20, amount, fees, destination):
        contract = self._contract(contract_id)
        op = contract.unwrap_erc20(erc_20=erc_20, amount=int(amount), fees=int(fees), destination=destination) \
            .inject()
        self._wait(op)

    def unwrap_erc721(self, contract_id, erc_721, token_id, destination):
        contract = self._contract(contract_id)
        op = contract.unwrap_erc721(erc_721=erc_721, token_id=int(token_id), destination=destination) \
            .with_amount(500_000) \
            .inject()
        self._wait(op)

    def confirm_admin(self, contract_id, fa2_contracts):
        print(f"Confirming admin on {contract_id} for {fa2_contracts}")
        contract = self._contract(contract_id)
        op = contract \
            .confirm_tokens_administrator(fa2_contracts).inject()
        self._wait(op)

    def set_signer(self, contract_id, quorum_contract):
        contract = self._contract(contract_id)
        op = contract.set_signer(quorum_contract).inject()
        self._wait(op)

    def set_administrator(self, contract_id, administrator):
        contract = self._contract(contract_id)
        op = contract.set_administrator(administrator).inject()
        self._wait(op)

    def pause_contract(self, contract_id, token_id):
        contract = self._contract(contract_id)
        op = contract.pause_contract([[token_id, True]]).inject()
        self._wait(op)

    def unpause_contract(self, contract_id, token_id):
        contract = self._contract(contract_id)
        op = contract.pause_contract([[token_id, False]]).inject()
        self._wait(op)

    def _contract(self, contract_id):
        return self.utils.client.contract(contract_id)

    def _wait(self, op):
        res = self.utils.wait_for_ops(op)
        print(f"Done {res[0]['hash']}")
