"""profile variants (role-tailored views of the master profile)

Revision ID: e5f9b2c7a1d8
Revises: c4e8a1b2d3f4
Create Date: 2026-07-26 07:30:00.000000

Adds `profile_variants` (role-tailored curated views of the master Profile) and an
`applications.variant_id` column recording which variant produced an application's docs.
Variants never store invented data — only overrides applied on top of the master.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f9b2c7a1d8'
down_revision: Union[str, Sequence[str], None] = 'c4e8a1b2d3f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'profile_variants',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('role_target', sa.String(), nullable=True),
        sa.Column('summary_override', sa.String(), nullable=True),
        sa.Column('emphasized_skills', sa.JSON(), nullable=True),
        sa.Column('hidden_sections', sa.JSON(), nullable=True),
        sa.Column('is_default', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_profile_variants_id'), 'profile_variants', ['id'], unique=False)
    with op.batch_alter_table('applications') as batch:
        batch.add_column(sa.Column('variant_id', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('applications') as batch:
        batch.drop_column('variant_id')
    op.drop_index(op.f('ix_profile_variants_id'), table_name='profile_variants')
    op.drop_table('profile_variants')
