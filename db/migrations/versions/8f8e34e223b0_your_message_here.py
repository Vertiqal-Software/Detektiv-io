"""your message here

Revision ID: 8f8e34e223b0
Revises: 0001_create_users
Create Date: 2025-08-22 08:41:12.175991

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8f8e34e223b0"
down_revision: Union[str, Sequence[str], None] = "0001_create_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
