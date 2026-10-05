"""
Thin wrapper around genlayer-py's read_contract for the indexer + any
live-read endpoints. API verified against the installed genlayer-py==0.16.3
package directly (create_client, client.read_contract(address,
function_name, args=..., kwargs=...)) -- not guessed.

Cache-vs-live pattern (documented here + in README.md):
  - The indexer polls the *_dict view methods and writes into Postgres as
    a read cache for fast list/detail endpoints.
  - Any caller that needs a guaranteed-fresh answer for a money-relevant
    question ("can I claim right now") MUST call `read_contract_view`
    directly instead of reading the Postgres cache, since the cache can
    lag behind the chain by up to INDEXER_POLL_INTERVAL_SECONDS.
"""
from __future__ import annotations

from typing import Any, Optional

from genlayer_py import generate_private_key
from genlayer_py.accounts import create_account
from genlayer_py.chains import localnet, studionet, testnet_asimov, testnet_bradbury
from genlayer_py.client.genlayer_client import GenLayerClient

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.rpc_budget import check_and_increment_rpc_budget

log = get_logger(__name__)

_NETWORKS = {
    "localnet": localnet,
    "studionet": studionet,
    "testnet_asimov": testnet_asimov,
    "testnet_bradbury": testnet_bradbury,
}

_client_singleton = None


def get_chain() -> Any:
    settings = get_settings()
    chain = _NETWORKS.get(settings.GENLAYER_NETWORK)
    if chain is None:
        raise ValueError(
            f"Unknown GENLAYER_NETWORK={settings.GENLAYER_NETWORK!r}, "
            f"expected one of {list(_NETWORKS)}"
        )
    return chain


def get_client():
    """
    Returns a read-only genlayer-py client for the indexer / live-read
    endpoints. NOTE (discovered empirically against the real deployed
    contract, verified with a live view call): genlayer-py's
    `create_client` / `read_contract` requires *some* local account bound
    to the client even for pure view calls -- there is no account-less
    read path in this SDK version. Since this backend never signs or
    submits transactions (it is read-only against the chain; all writes
    happen from the user's own wallet in the frontend), we generate a
    throwaway ephemeral local keypair purely to satisfy that requirement.
    It never holds funds and is never used to sign a write/transaction.
    """
    global _client_singleton
    if _client_singleton is None:
        settings = get_settings()
        chain = get_chain()
        if settings.GENLAYER_RPC_URL:
            chain = chain.model_copy(
                update={"rpc_urls": {"default": {"http": [settings.GENLAYER_RPC_URL]}}}
            )
        ephemeral_account = create_account(generate_private_key())
        # `genlayer_py.create_client()` eagerly initializes the consensus
        # contract. That initialization is only needed for writes; this
        # backend is read-only. On current StudioNet responses the eager
        # initialization can fail while decoding consensus RLP, preventing
        # otherwise valid application view calls (including get_loan_count)
        # from ever being attempted. Construct the client directly so the
        # indexer only uses the application RPC calls it actually needs.
        _client_singleton = GenLayerClient(chain_config=chain, account=ephemeral_account)
    return _client_singleton


def call_contract_view_budgeted(
    client: Any, address: str, function_name: str, args: Optional[list] = None
) -> Any:
    """THE single choke point for every outbound genlayer-py RPC call made
    by this backend -- the indexer's poll loop and any request-time
    passthrough read (`read_contract_view` below) both funnel through here.
    Parallel to the contract's own `_send_gen` single choke point for fund
    movement (see repo-root memory.md): just as no path moves GEN without
    going through `_send_gen`, no path calls genlayer-py without going
    through this function first. It checks-and-increments the shared Redis
    hourly RPC budget (`app/services/rpc_budget.py`) before making the
    call; a `RpcBudgetExhaustedError` propagates to the caller, which is
    responsible for graceful degradation (indexer backoff, or a 503 for a
    live endpoint -- see the global exception handler in app/main.py)."""
    check_and_increment_rpc_budget(reason=f"{function_name}")
    return client.read_contract(address=address, function_name=function_name, args=args or [])


def read_contract_view(function_name: str, args: Optional[list] = None) -> Any:
    """Direct, uncached, live read against the deployed contract. Raises if
    CONTRACT_ADDRESS is not configured -- callers must handle that state
    explicitly rather than receiving fabricated data. Goes through the
    shared RPC budget choke point (`call_contract_view_budgeted`) -- can
    raise `app.services.rpc_budget.RpcBudgetExhaustedError` if the hourly
    GenLayer RPC budget is exhausted; see app/main.py's exception handler
    for how that becomes a typed 503."""
    settings = get_settings()
    if not settings.CONTRACT_ADDRESS:
        raise RuntimeError("CONTRACT_ADDRESS is not configured")
    client = get_client()
    return call_contract_view_budgeted(
        client, settings.CONTRACT_ADDRESS, function_name, args
    )
