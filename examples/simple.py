"""
Minimal viable example of flashbots usage with dynamic fee transactions.
Sends a bundle of two transactions which transfer some ETH into a random account.

Environment Variables:
- ETH_SENDER_KEY: Private key of account which will send the ETH.
- ETH_SIGNER_KEY: Private key of account which will sign the bundle. 
    - This account is only used for reputation on flashbots and should be empty.
- PROVIDER_URL: HTTP JSON-RPC Ethereum provider URL.
"""

import os
import time
import secrets
import json
import requests
from uuid import uuid4
from eth_account import Account, messages
from eth_account.signers.local import LocalAccount
from flashbots import flashbot
from web3 import Web3, HTTPProvider
from web3.exceptions import TransactionNotFound
from web3.types import TxParams

# change this to `False` if you want to use mainnet
USE_SEPOLIA = True
CHAIN_ID = 5 if USE_SEPOLIA else 1

w3 = Web3(HTTPProvider('https://goerli.infura.io/v3/'))

# account to send the transfer and sign transactions
sender: LocalAccount = Account.from_key('')

# account to sign bundles & establish flashbots reputation
# NOTE: this account should not store funds
signer: LocalAccount = Account.from_key('')

def env(key: str) -> str:
    return os.environ.get(key)


def random_account() -> LocalAccount:
    key = "0x" + secrets.token_hex(32)
    return Account.from_key(key)

def simulate_bundle(bundle, target_blk_num):
    url = 'https://relay-sepolia.flashbots.net'

    target_blk_hex = w3.toHex(target_blk_num)
    data = {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "eth_callBundle",
        "params": [
            {
                'txs': bundle,  # List of signed transactions
                'blockNumber': target_blk_hex,  # Block number
                "stateBlockNumber": "latest"
            }
        ]
    }

    body = json.dumps(data)
    message = messages.encode_defunct(text=Web3.keccak(text=body).hex())
    signature = signer.address + ':' + Account.sign_message(message, signer.privateKey.hex()).signature.hex()

    headers = {
        'Content-Type': 'application/json',
        'X-Flashbots-Signature': signature,
    }

    response = requests.post(url, data=body, headers=headers)
    return response.json()


def main() -> None:
    # account to receive the transfer
    receiverAddress: str = random_account().address

    """
        self.titan_url = 'https://rpc.titanbuilder.xyz/'
        self.beaver_url = 'https://rpc.beaverbuild.org/'
        self.builder69_url = 'https://builder0x69.io/'
        self.rsync_url = 'https://rsync-builder.xyz/'
        self.flashbots_url = 'https://relay.flashbots.net'
        self.builder_urls = [self.titan_url, self.beaver_url, self.builder69_url, self.rsync_url, self.flashbots_url]
    """

    if USE_SEPOLIA:
        flashbot(w3, signer, 'https://relay-goerli.flashbots.net')
    else:
        flashbot(w3, signer)

    print(f"Sender address: {sender.address}")
    print(f"Receiver address: {receiverAddress}")
    print(
        f"Sender account balance: {Web3.fromWei(w3.eth.get_balance(sender.address), 'ether')} ETH"
    )
    print(
        f"Receiver account balance: {Web3.fromWei(w3.eth.get_balance(receiverAddress), 'ether')} ETH"
    )

    # bundle two EIP-1559 (type 2) transactions, pre-sign one of them
    # NOTE: chainId is necessary for all EIP-1559 txns
    # NOTE: nonce is required for signed txns

    nonce = w3.eth.get_transaction_count(sender.address)
    print(f"Nonce: {nonce}")
    tx1: TxParams = {
        "to": receiverAddress,
        "value": Web3.toWei(0.001, "ether"),
        "gas": 21000,
        "maxFeePerGas": Web3.toWei(200, "gwei"),
        "maxPriorityFeePerGas": Web3.toWei(50, "gwei"),
        "nonce": nonce,
        "chainId": CHAIN_ID,
        "type": 2,
    }
    tx1_signed = sender.sign_transaction(tx1)
    # print(tx1_signed.rawTransaction)
    # exit(0)

    tx2: TxParams = {
        "to": receiverAddress,
        "value": Web3.toWei(0.001, "ether"),
        "gas": 21000,
        "maxFeePerGas": Web3.toWei(200, "gwei"),
        "maxPriorityFeePerGas": Web3.toWei(50, "gwei"),
        "nonce": nonce + 1,
        "chainId": CHAIN_ID,
        "type": 2,
    }

    bundle = [
        {"signed_transaction": tx1_signed.rawTransaction},
        {"signer": sender, "transaction": tx2}
    ]
    print(f"Bundle: {bundle}")


    # keep trying to send bundle until it gets mined
    while True:
        block = w3.eth.block_number
        print(f"Simulating on block {block}")
        # simulate bundle on current block
        """
            block is an optional parameter for simulate, if not provided, the current block is used
            however, if your rpc provider is not fast enough, you might get error: "block extrapolation negative"
            see extrapolate_timestamp() in flashbots/flashbots.py
        """
        # try:
        #     res = simulate_bundle(bundle, block)
        #     print("Simulation result", res)
        #     print("Simulation successful.")
        # except Exception as e:
        #     print("Simulation error", e)
        #     return

        # send bundle targeting next block
        print(f"Sending bundle targeting block {block+1}")
        replacement_uuid = str(uuid4())
        print(f"replacementUuid {replacement_uuid}")
        send_result = w3.flashbots.send_bundle(
            bundle,
            target_block_number=block + 10,
            opts={"replacementUuid": replacement_uuid},
        )
        print("bundleHash", w3.toHex(send_result.bundle_hash()))

        time.sleep(12)

        stats_v1 = w3.flashbots.get_bundle_stats(
            w3.toHex(send_result.bundle_hash()), block
        )
        print("bundleStats v1", stats_v1)

        stats_v2 = w3.flashbots.get_bundle_stats_v2(
            w3.toHex(send_result.bundle_hash()), block
        )
        print("bundleStats v2", stats_v2)

        send_result.wait()
        try:
            receipts = send_result.receipts()
            print(f"\nBundle was mined in block {receipts[0].blockNumber}\a")
            break
        except TransactionNotFound:
            print(f"Bundle not found in block {block+1}")
            # essentially a no-op but it shows that the function works
            # cancel_res = w3.flashbots.cancel_bundles(replacement_uuid)
            # print(f"canceled {cancel_res}\n")
        

    print(
        f"Sender account balance: {Web3.fromWei(w3.eth.get_balance(sender.address), 'ether')} ETH"
    )
    print(
        f"Receiver account balance: {Web3.fromWei(w3.eth.get_balance(receiverAddress), 'ether')} ETH"
    )

if __name__ == "__main__":
    main()
