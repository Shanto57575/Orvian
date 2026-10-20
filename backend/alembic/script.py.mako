"""${message}

Revision ID: ${up_revision}
% if down_revision:
Revises: ${down_revision | comma,n}
% else:
Revises:
% endif
Create Date: ${create_date}

"""

from collections.abc import Sequence
% if imports:

${imports}
% else:

% endif
import sqlalchemy as sa  # noqa: F401

from alembic import op  # noqa: F401

# revision identifiers, used by Alembic.
revision: str = "${up_revision}"
% if down_revision:
down_revision: str | None = "${down_revision}"
% else:
down_revision: str | None = None
% endif
% if branch_labels:
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
% else:
branch_labels: str | Sequence[str] | None = None
% endif
% if depends_on:
depends_on: str | Sequence[str] | None = ${repr(depends_on)}
% else:
depends_on: str | Sequence[str] | None = None
% endif


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
