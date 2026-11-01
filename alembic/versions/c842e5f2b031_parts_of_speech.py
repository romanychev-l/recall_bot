"""Part of speech preferences and per-translation dictionary metadata."""
from alembic import op
import sqlalchemy as sa

revision = "c842e5f2b031"
down_revision = "b731d4e1a920"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # All 14 categories, including unknown ones, preserve existing coverage.
    op.add_column("users", sa.Column("pos_filter", sa.Integer(), server_default="16383", nullable=False))
    op.add_column("user_cards", sa.Column("study_pos_filter", sa.Integer(), server_default="16383", nullable=False))
    op.create_table(
        "word_senses",
        sa.Column("word_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("translation", sa.Text(), nullable=False),
        sa.Column("pos_mask", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["word_id"], ["words.id"],
                                name="fk_word_senses_word_id_words", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("word_id", "position", name="pk_word_senses"),
    )


def downgrade() -> None:
    op.drop_table("word_senses")
    op.drop_column("user_cards", "study_pos_filter")
    op.drop_column("users", "pos_filter")
