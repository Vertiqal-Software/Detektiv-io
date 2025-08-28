"""merge heads (2025-08-28)

Revision ID: 8782f557b2eb
Revises: 20250827_01_core_tables, e1f2a3b4c5d6
Create Date: 2025-08-28 15:04:48.244008

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8782f557b2eb"
down_revision: Union[str, Sequence[str], None] = (
    "20250827_01_core_tables",
    "e1f2a3b4c5d6",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
