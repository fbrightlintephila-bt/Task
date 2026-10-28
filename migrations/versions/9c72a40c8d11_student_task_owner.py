"""associate student-uploaded tasks with their owner

Revision ID: 9c72a40c8d11
Revises: 6029e7ebd4d2
Create Date: 2026-10-28 18:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "9c72a40c8d11"
down_revision = "6029e7ebd4d2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("assignment", schema=None) as batch_op:
        batch_op.add_column(sa.Column("origin_student_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_assignment_origin_student_id", ["origin_student_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_assignment_origin_student_id_user", "user", ["origin_student_id"], ["id"]
        )


def downgrade():
    with op.batch_alter_table("assignment", schema=None) as batch_op:
        batch_op.drop_constraint("fk_assignment_origin_student_id_user", type_="foreignkey")
        batch_op.drop_index("ix_assignment_origin_student_id")
        batch_op.drop_column("origin_student_id")