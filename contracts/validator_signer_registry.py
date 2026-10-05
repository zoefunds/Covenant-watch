# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""A minimal immutable ONCHAIN covenant source for Covenant Watch samples.

It deliberately exposes the exact public view used by the Autofill covenant:
``get_validator_signer_count()``. There are no write methods, so a sample
loan cannot have its source value changed after deployment.
"""

from genlayer import *


class ValidatorSignerRegistry(gl.Contract):
    def __init__(self):
        pass

    @gl.public.view
    def get_validator_signer_count(self) -> int:
        return 5
