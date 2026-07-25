"""apply assistant: profile, application, generated_doc, answer_bank

Revision ID: c4e8a1b2d3f4
Revises: 2a3d01bcedc1
Create Date: 2026-07-25 12:10:00.000000

Adds the Apply Assistant tables (plan-apply.md, Phase A/B). All FKs
ON DELETE CASCADE so deleting an account wipes the master profile,
applications and their generated docs (matches the privacy policy).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e8a1b2d3f4'
down_revision: Union[str, Sequence[str], None] = '2a3d01bcedc1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'profiles',
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('sections_json', sa.JSON(), nullable=False),
        sa.Column('full_name', sa.String(), nullable=True),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id'),
    )
    op.create_table(
        'applications',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('company', sa.String(), nullable=True),
        sa.Column('job_title', sa.String(), nullable=True),
        sa.Column('job_url', sa.String(), nullable=True),
        sa.Column('jd_text', sa.String(), nullable=False),
        sa.Column('jd_skills_json', sa.JSON(), nullable=True),
        sa.Column('match_json', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_applications_id'), 'applications', ['id'], unique=False)
    op.create_table(
        'generated_docs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('application_id', sa.String(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('content_json', sa.JSON(), nullable=False),
        sa.Column('format', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_generated_docs_id'), 'generated_docs', ['id'], unique=False)
    op.create_table(
        'answer_bank',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('question', sa.String(), nullable=False),
        sa.Column('answer', sa.String(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_answer_bank_id'), 'answer_bank', ['id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_answer_bank_id'), table_name='answer_bank')
    op.drop_table('answer_bank')
    op.drop_index(op.f('ix_generated_docs_id'), table_name='generated_docs')
    op.drop_table('generated_docs')
    op.drop_index(op.f('ix_applications_id'), table_name='applications')
    op.drop_table('applications')
    op.drop_table('profiles')
