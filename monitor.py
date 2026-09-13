"""Surveillance en lecture seule de cinq adresses crypto vers Telegram.

Ne demande ni n'utilise de clé privée. Python 3.10+; aucune dépendance externe.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

BASE_DIR = Path(__file__).resolve().parent
STATE_PATH = BASE_DIR / "state.json"

BTC = "bc1qukfvfv88pf3laxv8tfqwjeswfthckwls54at3v"
ETH = "0x10cdE57a3Cf40EE2066c4C36181fC3459a301698".lower()
LTC = "LVCoLLRyKrCo4Lq1UMLqyhor7HB67TsrHr"
SOL = "9XBFMfHnkFnq5gZDLfq8QhqMMtzaM4DjDa19Aj9Ty1Um"
USDT_CONTRACT = "0xdac17f958d2ee523a2206206994597c13d831ec7"  # USDT ERC-20
# Python sous Windows peut ne pas inclure la base des fuseaux. Dans ce cas,
# l'heure locale réglée sur l'ordinateur est utilisée (Paris pour cette installation).
try:
    PARIS = ZoneInfo("Europe/Paris")
except ZoneInfoNotFoundError:
    PARIS = datetime.now().astimezone().tzinfo


def read_env() -> dict[str, str]:
    """Lit un .env local sans dépendance externe."""
    values = dict(os.environ)
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


CFG = read_env()
TOKEN = CFG.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = CFG.get("TELEGRAM_CHAT_ID", "")
ETH_RPC = CFG.get("ETH_RPC_URL", "https://ethereum-rpc.publicnode.com")
SOL_RPC = CFG.get("SOL_RPC_URL", "https://api.mainnet-beta.solana.com")
POLL_SECONDS = max(10, int(CFG.get("POLL_SECONDS", "30")))


def get_json(url: str) -> object:
    request = urllib.request.Request(url, headers={"User-Agent": "crypto-telegram-alert/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, payload: dict) -> object:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def rpc(url: str, method: str, params: list) -> object:
    response = post_json(url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    if "error" in response:
        raise RuntimeError(f"RPC {method}: {response['error']}")
    return response["result"]


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict) -> None:
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
    temporary.replace(STATE_PATH)


def fmt(amount: Decimal, symbol: str) -> str:
    text = f"{amount.normalize():f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text + f" {symbol}"


def notify(network: str, amount: Decimal, symbol: str, address: str, txid: str, explorer: str) -> None:
    now = datetime.now(PARIS).strftime("%d/%m/%Y à %H:%M:%S (%Z)")
    message = (
        f"💰 Réception détectée\n\n"
        f"Réseau : {network}\nMontant : {fmt(amount, symbol)}\n"
        f"Date : {now}\nAdresse : <code>{address}</code>\n"
        f"Transaction : <a href=\"{explorer}{txid}\">voir sur l'explorateur</a>"
    )
    response = post_json(f"https://api.telegram.org/bot{TOKEN}/sendMessage", {
        "chat_id": CHAT_ID, "text": message, "parse_mode": "HTML", "disable_web_page_preview": True,
    })
    if not response.get("ok"):
        raise RuntimeError(f"Telegram: {response}")
    print(f"Alerte envoyée : {network} {amount} {symbol}", flush=True)


def send_test_message() -> None:
    """Vérifie le bot Telegram sans simuler ni créer de transaction."""
    now = datetime.now(PARIS).strftime("%d/%m/%Y à %H:%M:%S (%Z)")
    response = post_json(f"https://api.telegram.org/bot{TOKEN}/sendMessage", {
        "chat_id": CHAT_ID,
        "text": f"✅ Test réussi : le bot d'alerte crypto est connecté.\nDate : {now}",
    })
    if not response.get("ok"):
        raise RuntimeError(f"Telegram: {response}")


def incoming_sats(tx: dict, address: str) -> int:
    return sum(output.get("value", 0) for output in tx.get("vout", []) if output.get("scriptpubkey_address") == address)


def watch_utxo(state: dict, key: str, name: str, address: str, api: str, unit: str, factor: int, explorer: str) -> None:
    txs = get_json(api)
    known = set(state.get(key, []))
    if not known:
        state[key] = [tx["txid"] for tx in txs]
        return
    for tx in reversed(txs):
        txid = tx["txid"]
        if txid not in known:
            received = incoming_sats(tx, address)
            if received:
                notify(name, Decimal(received) / factor, unit, address, txid, explorer)
    state[key] = list(dict.fromkeys([tx["txid"] for tx in txs] + list(known)))[:100]


def watch_ethereum(state: dict) -> None:
    latest = int(rpc(ETH_RPC, "eth_blockNumber", []), 16)
    previous = state.get("eth_block")
    if previous is None:
        state["eth_block"] = latest
        return
    # Traite les blocs manqués, avec une limite qui évite une avalanche après un arrêt prolongé.
    start = max(int(previous) + 1, latest - 200)
    for number in range(start, latest + 1):
        block_hex = hex(number)
        block = rpc(ETH_RPC, "eth_getBlockByNumber", [block_hex, True])
        for tx in block.get("transactions", []):
            if (tx.get("to") or "").lower() == ETH and int(tx.get("value", "0x0"), 16) > 0:
                amount = Decimal(int(tx["value"], 16)) / Decimal(10 ** 18)
                notify("Ethereum", amount, "ETH", ETH, tx["hash"], "https://etherscan.io/tx/")
        # Evénements Transfer(0xddf252ad...) où la destination est notre adresse.
        topic_to = "0x" + "0" * 24 + ETH[2:]
        logs = rpc(ETH_RPC, "eth_getLogs", [{"fromBlock": block_hex, "toBlock": block_hex,
            "address": USDT_CONTRACT, "topics": ["0xddf252ad", None, topic_to]}])
        for log in logs:
            amount = Decimal(int(log["data"], 16)) / Decimal(10 ** 6)
            if amount > 0:
                notify("USDT (ERC-20)", amount, "USDT", ETH, log["transactionHash"], "https://etherscan.io/tx/")
    state["eth_block"] = latest


def watch_solana(state: dict) -> None:
    signatures = rpc(SOL_RPC, "getSignaturesForAddress", [SOL, {"limit": 20}])
    known = set(state.get("sol_signatures", []))
    if not known:
        state["sol_signatures"] = [item["signature"] for item in signatures]
        return
    for item in reversed(signatures):
        signature = item["signature"]
        if signature in known or item.get("err") is not None:
            continue
        tx = rpc(SOL_RPC, "getTransaction", [signature, {"encoding": "json", "maxSupportedTransactionVersion": 0}])
        if not tx:
            continue
        keys = tx["transaction"]["message"]["accountKeys"]
        index = next((i for i, entry in enumerate(keys) if entry.get("pubkey") == SOL), None)
        if index is None:
            continue
        meta = tx["meta"]
        change = meta["postBalances"][index] - meta["preBalances"][index]
        if change > 0:
            notify("Solana", Decimal(change) / Decimal(10 ** 9), "SOL", SOL, signature, "https://solscan.io/tx/")
    state["sol_signatures"] = list(dict.fromkeys([x["signature"] for x in signatures] + list(known)))[:100]


def validate_config() -> None:
    if not TOKEN or "collez_ici" in TOKEN or not CHAT_ID:
        raise SystemExit("Configurez TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID dans le fichier .env.")


def scan(state: dict) -> None:
    watch_utxo(state, "btc", "Bitcoin", BTC, f"https://mempool.space/api/address/{BTC}/txs", "BTC", 100_000_000, "https://mempool.space/tx/")
    watch_utxo(state, "ltc", "Litecoin", LTC, f"https://litecoinspace.org/api/address/{LTC}/txs", "LTC", 100_000_000, "https://litecoinspace.org/tx/")
    watch_ethereum(state)
    watch_solana(state)


def main() -> None:
    validate_config()
    state = load_state()
    if "--once" in sys.argv:
        scan(state)
        save_state(state)
        print("Vérification terminée.", flush=True)
        return
    if "--test" in sys.argv:
        send_test_message()
        print("Message de test Telegram envoyé. Test des cinq réseaux…", flush=True)
        try:
            scan(state)
            save_state(state)
            print("Test réussi : les cinq réseaux sont joignables.", flush=True)
        except (OSError, ValueError, urllib.error.URLError, urllib.error.HTTPError, RuntimeError, KeyError, IndexError) as error:
            print(f"Telegram fonctionne, mais un réseau est momentanément indisponible : {error}", flush=True)
        return
    print(f"Surveillance active toutes les {POLL_SECONDS} secondes. Ctrl+C pour arrêter.", flush=True)
    while True:
        try:
            scan(state)
            save_state(state)
        except (OSError, ValueError, urllib.error.URLError, urllib.error.HTTPError, RuntimeError, KeyError, IndexError) as error:
            print(f"Vérification impossible : {error}", flush=True)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
