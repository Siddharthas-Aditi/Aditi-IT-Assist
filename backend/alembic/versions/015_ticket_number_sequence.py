"""Generate ticket numbers with a database-owned atomic sequence.

Revision ID: 015_ticket_number_sequence
Revises: 014_ticket_categories
Create Date: 2026-08-31
"""

from alembic import op

revision = "015_ticket_number_sequence"
down_revision = "014_ticket_categories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE ticket_number_sequence START WITH 1")
    op.execute(
        """
        DO $$
        DECLARE
            current_max bigint;
        BEGIN
            SELECT COALESCE(
                MAX((substring(ticket_number FROM '^ITA-([0-9]+)$'))::bigint),
                0
            )
            INTO current_max
            FROM tickets
            WHERE ticket_number ~ '^ITA-[0-9]+$';

            IF current_max > 0 THEN
                PERFORM setval('ticket_number_sequence', current_max, true);
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP SEQUENCE ticket_number_sequence")
