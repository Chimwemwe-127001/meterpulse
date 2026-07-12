"""Create meters, readings, and alerts tables

These tables previously existed only via Base.metadata.create_all() at
startup, outside migration history. Alembic is now the single schema
authority.

Revision ID: 002_meters_readings_alerts
Revises: 001_initial
Create Date: 2026-07-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '002_meters_readings_alerts'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'meters',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('meter_code', sa.String(50), nullable=False),
        sa.Column('location', sa.Text(), nullable=False),
        sa.Column('utility_type', sa.String(30), nullable=False),
        sa.Column('unit', sa.String(10), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id']),
    )
    op.create_index('ix_meters_meter_code', 'meters', ['meter_code'], unique=True)
    op.create_index('ix_meters_owner_id', 'meters', ['owner_id'])

    op.create_table(
        'readings',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('meter_id', sa.Uuid(), nullable=False),
        sa.Column('value', sa.Numeric(12, 3), nullable=False),
        sa.Column('consumption', sa.Numeric(12, 3), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('submitted_by', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['meter_id'], ['meters.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['submitted_by'], ['users.id']),
    )
    op.create_index('ix_readings_meter_id', 'readings', ['meter_id'])
    op.create_index('ix_readings_meter_id_recorded_at', 'readings', ['meter_id', 'recorded_at'])

    op.create_table(
        'alerts',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('meter_id', sa.Uuid(), nullable=False),
        sa.Column('reading_id', sa.Uuid(), nullable=False),
        sa.Column('alert_type', sa.String(30), nullable=False),
        sa.Column('severity', sa.String(10), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('resolved', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('resolved_by', sa.Uuid(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['meter_id'], ['meters.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reading_id'], ['readings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['resolved_by'], ['users.id']),
    )
    op.create_index('ix_alerts_meter_id', 'alerts', ['meter_id'])
    op.create_index('ix_alerts_meter_id_created_at', 'alerts', ['meter_id', 'created_at'])
    op.create_index('ix_alerts_alert_type', 'alerts', ['alert_type'])
    op.create_index('ix_alerts_severity', 'alerts', ['severity'])


def downgrade() -> None:
    op.drop_table('alerts')
    op.drop_table('readings')
    op.drop_table('meters')
