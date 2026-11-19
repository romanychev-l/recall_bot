"""Correct the shipped don verb without rewriting custom content or progress."""
from alembic import op
import sqlalchemy as sa

revision = 'e064a7b4d253'
down_revision = 'd953f6a3c142'
branch_labels = None
depends_on = None

OLD_TRANSLATION = 'надевать; надеть; дон'
NEW_TRANSLATION = 'надевать; надеть'
OLD_EXAMPLE = (
    "I don' think Tom expected to be here for so long.\n"
    'I would like to nominate Don Jones as chairman.'
)
NEW_EXAMPLE = (
    'Please don your coat before going outside.\n'
    'The workers don protective gloves before starting work.'
)


def upgrade() -> None:
    connection = op.get_bind()
    words = sa.table('words', sa.column('id'), sa.column('english'),
                     sa.column('pos'), sa.column('translation'), sa.column('example'))
    senses = sa.table('word_senses', sa.column('word_id'), sa.column('translation'))
    shipped = (words.c.english == 'don') & (words.c.pos == 'verb')
    corrected_ids = list(connection.execute(sa.select(words.c.id).where(
        shipped, words.c.translation == OLD_TRANSLATION
    )).scalars())
    if corrected_ids:
        connection.execute(words.update().where(words.c.id.in_(corrected_ids))
                           .values(translation=NEW_TRANSLATION))
        connection.execute(senses.delete().where(senses.c.word_id.in_(corrected_ids),
                                                 senses.c.translation == 'дон'))
    connection.execute(words.update().where(shipped, words.c.example == OLD_EXAMPLE)
                       .values(example=NEW_EXAMPLE))


def downgrade() -> None:
    # Content corrections are retained; a downgrade must not restore bad data
    # or overwrite content that has since been edited by an owner.
    pass
