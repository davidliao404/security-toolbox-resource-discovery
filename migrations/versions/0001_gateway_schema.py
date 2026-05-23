from __future__ import annotations

from alembic import op

from resource_discovery.db import metadata

revision = "0001_gateway_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in metadata.sorted_tables:
        columns = [column.copy() for column in table.columns]
        constraints = [constraint.copy() for constraint in list(table.constraints) if not constraint._type_bound]
        op.create_table(table.name, *columns, *constraints)
    for table in metadata.sorted_tables:
        for index in table.indexes:
            op.create_index(index.name, table.name, [column.name for column in index.columns], unique=index.unique)


def downgrade() -> None:
    for table in reversed(metadata.sorted_tables):
        op.drop_table(table.name)
