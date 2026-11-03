"""Independent chat usage credit, without changing cards or review history."""
from alembic import op
import sqlalchemy as sa
from bot.db.models import UtcDateTime

revision = 'd953f6a3c142'
down_revision = 'c842e5f2b031'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'chat_practice',
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('word_id', sa.Integer(), nullable=False),
        sa.Column('practice_day', sa.String(10), nullable=False),
        sa.Column('chat_id', sa.BigInteger(), nullable=False),
        sa.Column('message_id', sa.Integer(), nullable=False),
        sa.Column('study_state', sa.String(8), nullable=False),
        sa.Column('used_at', UtcDateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_chat_practice_user_id_users', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['word_id'], ['words.id'], name='fk_chat_practice_word_id_words', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'word_id', 'practice_day', name='pk_chat_practice'),
        sa.UniqueConstraint('chat_id', 'message_id', 'word_id', name='uq_chat_practice_message_word'),
    )
    op.create_index('ix_chat_practice_user_id_used_at', 'chat_practice', ['user_id', 'used_at'])
    op.create_index('ix_chat_practice_chat_id_used_at', 'chat_practice', ['chat_id', 'used_at'])
    op.create_table(
        'chat_practice_praise',
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('chat_id', sa.BigInteger(), nullable=False),
        sa.Column('last_praised_at', UtcDateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_chat_practice_praise_user_id_users', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'chat_id', name='pk_chat_practice_praise'),
    )


def downgrade() -> None:
    op.drop_table('chat_practice_praise')
    op.drop_index('ix_chat_practice_chat_id_used_at', table_name='chat_practice')
    op.drop_index('ix_chat_practice_user_id_used_at', table_name='chat_practice')
    op.drop_table('chat_practice')
