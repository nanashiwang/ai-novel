from app.core.schema import _POSTGRES_SCHEMA_FIXES


def test_runtime_schema_fixes_include_recent_generation_columns():
    statements = "\n".join(_POSTGRES_SCHEMA_FIXES)

    assert "generation_jobs ADD COLUMN IF NOT EXISTS dedupe_key" in statements
    assert "novel_specs ADD COLUMN IF NOT EXISTS continuity_rules" in statements
    assert "export_files ADD COLUMN IF NOT EXISTS content" in statements
    assert "export_files ADD COLUMN IF NOT EXISTS file_size" in statements
    assert "usage_events ADD COLUMN IF NOT EXISTS event_metadata" in statements
    assert "usage_events ADD COLUMN IF NOT EXISTS updated_at" in statements
    assert "model_calls ADD COLUMN IF NOT EXISTS metadata" in statements
    assert "scenes ADD COLUMN IF NOT EXISTS target_words" in statements
    assert "scenes ADD COLUMN IF NOT EXISTS beat_group_summary" in statements
    assert "monthly_generated_words" in statements
