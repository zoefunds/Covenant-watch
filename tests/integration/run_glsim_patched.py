"""Launcher for `glsim` that works around a process-wide "only one contract
class per process" loader limitation (see tests/direct/conftest.py for the
identical bug as it manifests in direct mode, and tests/integration/
conftest.py's module docstring).

glsim internally reuses `gltest.direct.loader.load_contract_class` to load
contract source into Python classes for both real deploys and schema
introspection. That loader sets a process-wide
`genlayer.gl.genvm_contracts.__known_contract__` global the first time any
`gl.Contract` subclass is defined and never resets it. Since glsim is a
single long-lived server process, this means the SECOND distinct contract
file deployed against the same running glsim (e.g. this project's
`covenant_watch.py` AND `test_helpers/mock_signer_registry.py`, needed
together for the ONCHAIN cross-contract covenant check test) fails with a
misleading `"class is not marked for usage within storage"` error instead
of deploying.

Usage (replaces a bare `glsim` invocation):

    python tests/integration/run_glsim_patched.py --port 4123 --validators 5 \\
        --llm-provider openai:gpt-4o-mini

All CLI flags are forwarded unchanged to glsim's own argument parser. This
changes no contract behavior -- it only resets a same-process bookkeeping
global before each contract module load, matching how each contract
actually runs in its own isolated GenVM instance in production.
"""

import sys


def _patch_loader() -> None:
    try:
        import gltest.direct.loader as _loader
    except ImportError:  # pragma: no cover - glsim/gltest not installed
        return

    _orig_load_contract_class = _loader.load_contract_class

    def _clear_contract_registries() -> None:
        # SDK releases have used both spellings, and version-isolated SDK
        # modules are not guaranteed to be registered under the canonical
        # ``genlayer.gl.genvm_contracts`` name.  Clear every loaded registry,
        # not merely the first module imported by this launcher.
        for name, mod in list(sys.modules.items()):
            if "genvm_contracts" not in name:
                continue
            for attr in ("__known_contact__", "__known_contract__"):
                if hasattr(mod, attr):
                    setattr(mod, attr, None)

    def _reset_known_contract_and_load(contract_path, vm, sdk_version=None):
        _clear_contract_registries()
        return _orig_load_contract_class(contract_path, vm, sdk_version=sdk_version)

    _loader.load_contract_class = _reset_known_contract_and_load

    # ``glsim.engine`` binds loader functions at module import time and also
    # performs registry resets directly.  Import it after patching the loader,
    # then replace its reset helper with the same version-agnostic sweep.
    import glsim.engine as _engine

    _engine.load_contract_class = _reset_known_contract_and_load
    _engine.SimEngine._reset_contract_registry = staticmethod(
        _clear_contract_registries
    )


def main() -> None:
    _patch_loader()
    from glsim.__main__ import main as glsim_main

    glsim_main()


if __name__ == "__main__":
    main()
