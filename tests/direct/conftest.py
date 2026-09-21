import json
import sys

# ---------------------------------------------------------------------------
# Work around a genlayer-test/direct-mode loader limitation: the SDK's
# genvm_contracts module tracks a single process-wide `__known_contract__`
# global that is set the first time ANY `gl.Contract` subclass is defined and
# is never reset. Several of our tests deploy two distinct contract files in
# one test process (the production CovenantWatch contract plus
# helper_onchain_source.py's MockSignerRegistry, used to stand in for a real
# onchain covenant source). Without this reset, the second deploy in a test
# process raises "only one contract is allowed". This patch clears that
# global immediately before each contract module load so each deploy is
# evaluated independently, matching how each contract actually runs in its
# own isolated GenVM instance in production. It changes no contract
# behavior — it only works around a same-process test-harness artifact.
try:
    import gltest.direct.loader as _gltest_loader

    _orig_load_contract_class = _gltest_loader.load_contract_class

    def _reset_known_contract_and_load(contract_path, vm, sdk_version=None):
        for name, mod in list(sys.modules.items()):
            if name.endswith("genvm_contracts") and hasattr(mod, "__known_contract__"):
                mod.__known_contract__ = None
        return _orig_load_contract_class(contract_path, vm, sdk_version=sdk_version)

    _gltest_loader.load_contract_class = _reset_known_contract_and_load
except ImportError:  # pragma: no cover - loader internals unavailable
    pass

# ---------------------------------------------------------------------------
# Work around a second direct-mode harness limitation: gltest.direct.wasi_mock
# ._handle_llm_request "conveniently" auto-parses a JSON-string mock_llm
# response into a native Python dict before handing it back across the
# simulated WASI boundary via GenVM calldata encoding. GenVM calldata has no
# float type (by design — the whole point of the scaled-integer money/ratio
# pattern this contract uses), so any mocked observed_value containing a
# decimal (e.g. 1.2, 0.8 — exactly the realistic reserve-ratio values these
# tests need) makes that calldata.encode() call fail, the harness silently
# swallows the error, and the contract sees `raw = None` instead of the
# mocked verdict. This matches production more closely anyway: a real
# exec_prompt(response_format="json") call hands the contract the model's
# raw JSON text, which the contract parses itself via
# _sanitize_json_text/json.loads (see covenant_watch.py::_parse_json_object)
# — the contract was never written to expect a pre-parsed dict. So this
# patch keeps the mocked LLM response as the plain string it already is,
# rather than eagerly parsing it, letting it cross the calldata boundary as
# a string (always encodable) and exercising the exact same parsing path the
# real contract uses in production.
try:
    import gltest.direct.wasi_mock as _wasi_mock

    def _llm_request_no_autoparse(vm, data):
        prompt = data.get("prompt", "")
        response = vm._match_llm_mock(prompt)
        if response is not None:
            return {"ok": response}

        strict = getattr(vm, "_strict_mock_mode", False)
        if strict:
            registered = [p.pattern for p, _ in vm._llm_mocks]
            raise _wasi_mock.MockNotFoundError(
                f"[strict] No LLM mock for prompt: {prompt[:100]}...\n"
                f"  Registered: {registered or '(none)'}"
            )

        live_handler = getattr(vm, "_live_llm_handler", None)
        if live_handler is not None:
            return live_handler(data)

        registered = [p.pattern for p, _ in vm._llm_mocks]
        raise _wasi_mock.MockNotFoundError(
            f"No LLM mock for prompt: {prompt[:100]}...\n"
            f"  Registered: {registered or '(none)'}"
        )

    _wasi_mock._handle_llm_request = _llm_request_no_autoparse
except ImportError:  # pragma: no cover - wasi_mock internals unavailable
    pass

CONTRACT_PATH = "contracts/covenant_watch.py"


def warp_seconds(direct_vm, seconds: int) -> None:
    """Advance the VM's simulated clock by `seconds` relative to its current
    time. The harness only exposes an absolute `vm.warp(iso_timestamp)`
    cheatcode, so this computes the new ISO timestamp from the VM's current
    `_datetime` and calls that."""
    import datetime as _dt

    current = _dt.datetime.fromisoformat(direct_vm._datetime.replace("Z", "+00:00"))
    new_ts = current + _dt.timedelta(seconds=seconds)
    direct_vm.warp(new_ts.isoformat().replace("+00:00", "Z"))


def to_hex(addr) -> str:
    """Normalize a test-fixture address (direct_alice/bob/charlie/owner) to a
    0x-prefixed hex string for passing into contract calls.

    In this harness, the direct_* address fixtures are resolved before the
    first contract deploy sets up the SDK's sys.path, so `genlayer.py.types
    .Address` isn't importable yet at fixture-creation time and the fixture
    factory (gltest.direct.loader.create_address) silently falls back to
    returning raw bytes instead of an Address wrapper. This helper accepts
    either form so test code doesn't depend on that fixture-ordering detail."""
    if hasattr(addr, "as_hex"):
        return addr.as_hex
    if isinstance(addr, (bytes, bytearray)):
        return "0x" + addr.hex()
    return str(addr)

DAY = 24 * 60 * 60


def onchain_covenant(source_ref="0x" + "11" * 20, field="signer_count", op=">=", threshold=3,
                      tier1=500, tier2=5000):
    return {
        "source_type": "ONCHAIN",
        "source_ref": source_ref,
        "condition_field": field,
        "operator": op,
        "threshold": threshold,
        "description": "multisig signer count must stay at or above threshold",
        "tier1_interest_step_up_bps": tier1,
        "tier2_seizure_bps": tier2,
    }


def offchain_covenant(url="https://example.org/attestation", field="reserve_ratio", op=">=",
                       threshold=1.0, tier1=500, tier2=5000):
    return {
        "source_type": "OFFCHAIN",
        "source_ref": url,
        "condition_field": field,
        "operator": op,
        "threshold": threshold,
        "description": "published reserve attestation ratio must stay at or above threshold",
        "tier1_interest_step_up_bps": tier1,
        "tier2_seizure_bps": tier2,
    }


def covenants_json(*covs):
    return json.dumps(list(covs))


def mock_offchain_verdict(direct_vm, status="COMPLIANT", value=1.2, note="ok", url_pattern=".*example\\.org.*"):
    """Mocked LLM response for the OFFCHAIN evaluation path — labeled MOCKED,
    never a real live fetch/LLM call. Also mocks the underlying web render
    call so the fetch itself always 'succeeds' in these direct-mode tests."""
    direct_vm.clear_mocks()  # each call fully replaces the prior mocked verdict
    direct_vm.mock_web(url_pattern, {"status": 200, "body": "mocked attestation page content"})
    direct_vm.mock_llm(
        r".*neutral covenant-compliance inspector.*",
        json.dumps({"status": status, "observed_value": value, "observed_note": note}),
    )
