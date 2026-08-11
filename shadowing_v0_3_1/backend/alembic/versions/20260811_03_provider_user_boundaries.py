"""Persist user-declared provider capability and format boundaries."""
from alembic import op
import sqlalchemy as sa

revision = "20260811_03"
down_revision = "20260715_02"
branch_labels = None
depends_on = None

_TARGETS = {
    ("llm", "openai_compatible"): ("openai_chat_compatible", '["generate_json", "generate_text"]', '["response_format"]'),
    ("llm", "openai_chat_compatible"): ("openai_chat_compatible", '["generate_json", "generate_text"]', '["response_format"]'),
    ("tts", "openai_compatible"): ("openai_audio_tts", '["synthesize"]', '["mp3"]'),
    ("tts", "openai_audio_tts"): ("openai_audio_tts", '["synthesize"]', '["mp3"]'),
    ("tts", "mimo_tts"): ("mimo_tts", '["synthesize"]', '["wav"]'),
    ("asr", "openai_whisper_asr"): ("openai_audio_asr", '["transcribe", "word_timestamps"]', '[]'),
    ("asr", "openai_audio_asr"): ("openai_audio_asr", '["transcribe", "word_timestamps"]', '[]'),
    ("asr", "mimo_asr"): ("mimo_asr", '["transcribe"]', '[]'),
}

def upgrade():
    op.add_column("ai_providers", sa.Column("enabled_capabilities", sa.String(), nullable=False, server_default="[]"))
    op.add_column("ai_providers", sa.Column("enabled_formats", sa.String(), nullable=False, server_default="[]"))
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, capability, provider_type FROM ai_providers")).mappings()
    for row in rows:
        key = (row["capability"], str(row["provider_type"]).lower().replace("-", "_"))
        target = _TARGETS.get(key)
        if target:
            bind.execute(sa.text("UPDATE ai_providers SET provider_type=:kind, enabled_capabilities=:caps, enabled_formats=:formats WHERE id=:id"), {"kind": target[0], "caps": target[1], "formats": target[2], "id": row["id"]})
        else:
            bind.execute(sa.text("UPDATE ai_providers SET is_enabled=0, is_default=0 WHERE id=:id"), {"id": row["id"]})
    op.alter_column("ai_providers", "enabled_capabilities", server_default=None)
    op.alter_column("ai_providers", "enabled_formats", server_default=None)

def downgrade():
    op.drop_column("ai_providers", "enabled_formats")
    op.drop_column("ai_providers", "enabled_capabilities")
