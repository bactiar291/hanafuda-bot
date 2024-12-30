import asyncio
import json
import time
import os
from web3 import Web3
import aiohttp
import argparse
from colorama import init, Fore, Style
import random
from fake_useragent import UserAgent

init(autoreset=True)

RPC_URL = "https://mainnet.base.org"
CONTRACT_ADDRESS = "0xC5bf05cD32a14BFfb705Fb37a9d218895187376c"
api_url = "https://hanafuda-backend-app-520478841386.us-central1.run.app/graphql"
web3 = Web3(Web3.HTTPProvider(RPC_URL))

with open("accounts.json", "r") as file:
    accounts = json.load(file)

contract_abi = '''
[
    {
        "constant": false,
        "inputs": [],
        "name": "depositETH",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function"
    }
]
'''

ua = UserAgent()

def get_random_user_agent():
    return ua.random

headers = {
    'Accept': '*/*',
    'Content-Type': 'application/json',
    'User-Agent': get_random_user_agent()
}

def clear_terminal():
    os.system('cls' if os.name == 'nt' else 'clear')

async def colay(session, url, method, payload_data=None):
    headers['User-Agent'] = get_random_user_agent()
    async with session.request(method, url, headers=headers, json=payload_data) as response:
        if response.status != 200:
            raise Exception(f'Kesalahan HTTP! Status: {response.status}')
        return await response.json()

async def refresh_access_token(session, refresh_token):
    api_key = "AIzaSyDipzN0VRfTPnMGhQ5PSzO27Cxm3DohJGY"
    async with session.post(
        f'https://securetoken.googleapis.com/v1/token?key={api_key}',
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=f'grant_type=refresh_token&refresh_token={refresh_token}'
    ) as response:
        if response.status != 200:
            raise Exception("Gagal memperbarui token akses")
        data = await response.json()
        return data.get('access_token')

async def handle_grow_and_garden(session, account):
    refresh_token = account['access_token']
    private_key = account['private_key']
    
    new_access_token = await refresh_access_token(session, refresh_token)
    headers['authorization'] = f'Bearer {new_access_token}'

    info_query = {
        "query": "query getCurrentUser { "
                  "currentUser { id totalPoint depositCount } "
                  "getGardenForCurrentUser { "
                  "gardenStatus { growActionCount gardenRewardActionCount } "
                  "} "
                  "} ",
        "operationName": "getCurrentUser"
    }
    info = await colay(session, api_url, 'POST', info_query)

    balance = info['data']['currentUser']['totalPoint']
    deposit = info['data']['currentUser']['depositCount']
    grow = info['data']['getGardenForCurrentUser']['gardenStatus']['growActionCount']
    garden = info['data']['getGardenForCurrentUser']['gardenStatus']['gardenRewardActionCount']

    print(f"{Fore.CYAN}Akun {private_key[:4]}...{private_key[-4:]} - {Style.BRIGHT}Poin: {balance} | Jumlah Deposit: {deposit} | Sisa Grow: {grow} | Sisa Garden: {garden}{Style.RESET_ALL}")

    async def grow_action():
        grow_action_query = {
            "query": """
                mutation executeGrowAction {
                    executeGrowAction(withAll: true) {
                        totalValue
                        multiplyRate
                    }
                    executeSnsShare(actionType: GROW, snsType: X) {
                        bonus
                    }
                }
            """,
            "operationName": "executeGrowAction"
        }

        try:
            mine = await colay(session, api_url, 'POST', grow_action_query)
            if mine and 'data' in mine and 'executeGrowAction' in mine['data']:
                reward = mine['data']['executeGrowAction']['totalValue']
                return reward
            else:
                print(f"{Fore.RED}Kesalahan: Format respons tidak seperti yang diharapkan: {mine}{Style.RESET_ALL}")
                return 0
        except Exception as e:
            return 0

    if grow > 0:
        reward = await grow_action()
        if reward:
            balance += reward
            grow = 0
            print(f"{Fore.GREEN}Hadiah: {reward} | Saldo: {balance} | Sisa Grow: {grow}{Style.RESET_ALL}")

    while garden >= 10:
        garden_action_query = {
            "query": "mutation executeGardenRewardAction($limit: Int!) { executeGardenRewardAction(limit: $limit) { data { cardId group } isNew } }",
            "variables": {"limit": 10},
            "operationName": "executeGardenRewardAction"
        }
        mine_garden = await colay(session, api_url, 'POST', garden_action_query)
        card_ids = [item['data']['cardId'] for item in mine_garden['data']['executeGardenRewardAction']]
        print(f"{Fore.GREEN}Garden Dibuka: {card_ids}{Style.RESET_ALL}")
        garden -= 10

def get_random_eth_amount():
    return random.uniform(0.0000005, 0.0000008)

async def handle_eth_transactions(session, account, num_transactions):
    private_key = account['private_key']
    contract = web3.eth.contract(address=CONTRACT_ADDRESS, abi=json.loads(contract_abi))
    nonces = {private_key: web3.eth.get_transaction_count(web3.eth.account.from_key(private_key).address)}

    for i in range(num_transactions):
        from_address = web3.eth.account.from_key(private_key).address
        short_from_address = from_address[:4] + "..." + from_address[-4:]

        amount_wei = web3.to_wei(get_random_eth_amount(), 'ether')

        try:
            transaction = contract.functions.depositETH().build_transaction({
                'from': from_address,
                'value': amount_wei,
                'gas': 100000,
                'gasPrice': web3.eth.gas_price,
                'nonce': nonces[private_key],
            })

            signed_txn = web3.eth.account.sign_transaction(transaction, private_key=private_key)

            tx_hash = web3.eth.send_raw_transaction(signed_txn.raw_transaction)
            print(f"{Fore.GREEN}Deposit {i + 1} sukses dari {short_from_address} dengan hash transaksi: {tx_hash.hex()}{Style.RESET_ALL}")

            nonces[private_key] += 1
            await asyncio.sleep(1)

        except Exception as e:
            if 'nonce too low' in str(e):
                print(f"{Fore.RED}Kesalahan deposit transaksi dari {short_from_address}: Nonce terlalu rendah. Memperbarui nonce...{Style.RESET_ALL}")
                nonces[private_key] = web3.eth.get_transaction_count(from_address)
            else:
                print(f"{Fore.RED}Kesalahan deposit transaksi dari {short_from_address}: {str(e)}{Style.RESET_ALL}")

def display_menu():
    clear_terminal()
    print(f"{Fore.YELLOW}{Style.BRIGHT}Pilih Tindakan:{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{Style.BRIGHT}╔════════════════════════════════════════╗")
    print(f"{Fore.CYAN}║ {Style.BRIGHT}1: Deposit Transaksi              ║")
    print(f"{Fore.CYAN}║ {Style.BRIGHT}2: Grow dan Garden               ║")
    print(f"{Fore.CYAN}╚════════════════════════════════════════╝{Style.RESET_ALL}")

async def main(mode, num_transactions=None):
    async with aiohttp.ClientSession() as session:
        if mode == '1':
            if num_transactions is None:
                num_transactions = int(input(f"{Fore.YELLOW}Masukkan jumlah transaksi yang akan dieksekusi: {Style.RESET_ALL}"))
            for account in accounts:
                await handle_eth_transactions(session, account, num_transactions)
        elif mode == '2':
            while True:
                for account in accounts:
                    await handle_grow_and_garden(session, account)
                print(f"{Fore.YELLOW}Semua akun telah diproses. Menunggu selama 10 menit...{Style.RESET_ALL}")
                time.sleep(600)
        else:
            print(f"{Fore.RED}Pilihan tidak valid. Silakan pilih 1 atau 2.{Style.RESET_ALL}")

if __name__ == '__main__':
    display_menu()

    parser = argparse.ArgumentParser(description='Pilih mode operasi.')
    parser.add_argument('-a', '--action', choices=['1', '2'], help='1: Eksekusi Deposit, 2: Grow dan Garden')
    parser.add_argument('-tx', '--transactions', type=int, help='Jumlah transaksi yang akan dieksekusi (opsional untuk aksi 1)')

    args = parser.parse_args()

    if args.action is None:
        action = input(f"{Fore.YELLOW}Pilih tindakan (1: Deposit Transaksi, 2: Grow dan Garden): {Style.RESET_ALL}")
        while action not in ['1', '2']:
            print(f"{Fore.RED}Pilihan tidak valid. Silakan pilih 1 atau 2.{Style.RESET_ALL}")
            action = input(f"{Fore.YELLOW}Pilih tindakan (1: Deposit Transaksi, 2: Grow dan Garden): {Style.RESET_ALL}")
    else:
        action = args.action

    if action == '1':
        transactions = int(input(f"{Fore.YELLOW}Masukkan jumlah transaksi yang akan dieksekusi: {Style.RESET_ALL}"))
        asyncio.run(main(action, transactions))
    else:
        asyncio.run(main(action))
