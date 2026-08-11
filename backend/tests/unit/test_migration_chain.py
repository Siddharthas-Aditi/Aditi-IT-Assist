"""Guards on the Alembic revision graph.

Both failures these cover are silent at author time and only surface when
someone actually runs `alembic upgrade head`:

* a `down_revision` naming a revision id that doesn't exist breaks the graph
  (``KeyError``), so no migration past that point can ever run;
* a revision id longer than 32 characters cannot be recorded, because Alembic
  creates ``alembic_version.version_num`` as ``VARCHAR(32)`` — the upgrade
  applies its DDL and then dies inserting the stamp.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

# Alembic's hardcoded width for alembic_version.version_num.
VERSION_NUM_MAX_LENGTH = 32

BACKEND_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def script_directory() -> ScriptDirectory:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("version_locations", str(BACKEND_ROOT / "alembic" / "versions"))
    return ScriptDirectory.from_config(config)


def test_revision_graph_resolves(script_directory: ScriptDirectory) -> None:
    """Every down_revision points at a revision that exists."""
    revisions = list(script_directory.walk_revisions())
    assert revisions, "no migrations discovered — check version_locations"

    known = {rev.revision for rev in revisions}
    dangling = {
        rev.revision: rev.down_revision
        for rev in revisions
        if rev.down_revision is not None
        and not set(
            rev.down_revision if isinstance(rev.down_revision, tuple) else (rev.down_revision,)
        ).issubset(known)
    }
    assert not dangling, f"down_revision(s) reference missing revisions: {dangling}"


def test_single_head(script_directory: ScriptDirectory) -> None:
    """A branched history would make `upgrade head` ambiguous."""
    heads = script_directory.get_heads()
    assert len(heads) == 1, f"expected exactly one head, got {heads}"


def test_revision_ids_fit_version_table(script_directory: ScriptDirectory) -> None:
    """Revision ids must fit alembic_version.version_num (VARCHAR(32))."""
    too_long = {
        rev.revision: len(rev.revision)
        for rev in script_directory.walk_revisions()
        if len(rev.revision) > VERSION_NUM_MAX_LENGTH
    }
    assert not too_long, (
        f"revision ids exceed {VERSION_NUM_MAX_LENGTH} chars and cannot be stamped: {too_long}"
    )
