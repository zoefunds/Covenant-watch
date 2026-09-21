# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""Minimal helper contract deployed by the integration tests to stand in for
a real onchain covenant source (e.g. a multisig config contract) that
exposes a `get_<condition_field>` view — the documented integration surface
for ONCHAIN covenants (see `_evaluate_onchain` in covenant_watch.py).

Deployed for real against GLSim/Studio/testnet by these tests, exercising
the genuine `gl.get_contract_at(...)` cross-contract read path that
tests/direct/ could not cover (no CallContract support in direct mode —
see memory.md). Never part of the production Covenant Watch protocol."""

from genlayer import *


class MockSignerRegistry(gl.Contract):
    signer_count: u32

    def __init__(self, initial_signer_count: int):
        self.signer_count = u32(initial_signer_count)

    @gl.public.write
    def set_signer_count(self, value: int) -> None:
        self.signer_count = u32(value)

    @gl.public.view
    def get_signer_count(self) -> int:
        return int(self.signer_count)
