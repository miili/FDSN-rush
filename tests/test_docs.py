from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

from fdsn_rush.client import FDSNClient
from fdsn_rush.manager import FDSNDownloadManager
from fdsn_rush.writer import SDSWriter

CONFIGURATION_DOCS = (
    Path(__file__).parent.parent / "docs" / "reference" / "configuration.md"
)


@pytest.mark.skipif(
    not CONFIGURATION_DOCS.exists(), reason="docs are not part of the sdist"
)
@pytest.mark.parametrize("model", [FDSNDownloadManager, SDSWriter, FDSNClient])
def test_configuration_documented(model: type[BaseModel]) -> None:
    """Every config option has an entry in the configuration reference."""
    text = CONFIGURATION_DOCS.read_text()
    missing = [
        name
        for name, field in model.model_fields.items()
        if not field.exclude and f"`{name}`\n:" not in text
    ]
    assert not missing, f"Undocumented options in {CONFIGURATION_DOCS.name}"
