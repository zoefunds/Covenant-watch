from types import SimpleNamespace

from hexbytes import HexBytes

from app.services import base_sepolia


class _LoanCall:
    def call(self):
        return (
            "0x0000000000000000000000000000000000000001",
            "0x0000000000000000000000000000000000000002",
            1_000_000,
            1_500_000,
            0,
            0,
            0,
            0,
            500,
            500,
            1_800_000_000,
            1_799_000_000,
            86_400,
            0,
            1,
            1,
            5,
            True,
            HexBytes("0x" + "9e" * 32),
        )


class _Functions:
    def loans(self, _loan_id):
        return _LoanCall()


class _Contract:
    functions = _Functions()


class _Eth:
    def contract(self, **_kwargs):
        return _Contract()


def test_get_base_loan_serializes_bytes32_commitment_as_hex(monkeypatch):
    monkeypatch.setattr(
        base_sepolia,
        "get_settings",
        lambda: SimpleNamespace(
            BASE_ESCROW_ADDRESS="0x0000000000000000000000000000000000000003",
            BASE_SEPOLIA_RPC_URL="https://example.invalid",
        ),
    )
    monkeypatch.setattr(base_sepolia, "_web3", lambda: SimpleNamespace(eth=_Eth()))

    loan = base_sepolia.get_base_loan(2)

    assert loan["commitment"] == "0x" + "9e" * 32
