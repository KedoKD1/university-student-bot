-- Read-only diagnostics. Run in Supabase SQL Editor; do not export student data.
-- The application already uses these tables/columns. Inspect schema first.
BEGIN TRANSACTION READ ONLY;

SELECT table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name IN ('summaries', 'drawings')
ORDER BY table_name, ordinal_position;

WITH content AS (
    SELECT 'summaries' AS kind, id, subject_id, section_type,
           is_active, deleted_at, telegram_file_id FROM public.summaries
    UNION ALL
    SELECT 'drawings', id, subject_id, section_type,
           is_active, deleted_at, telegram_file_id FROM public.drawings
)
SELECT kind, count(*) AS total_rows,
       count(*) FILTER (WHERE is_active = true) AS old_statistic,
       count(*) FILTER (WHERE is_active = true AND deleted_at IS NULL) AS corrected_statistic,
       count(*) FILTER (WHERE is_active = true AND deleted_at IS NOT NULL) AS active_but_deleted,
       count(*) FILTER (WHERE is_active = true AND deleted_at IS NULL
                        AND nullif(btrim(telegram_file_id), '') IS NULL) AS missing_media_reference
FROM content GROUP BY kind;

-- Candidates for manual review, not proof of duplicates: reusing the same media
-- may be intentional. Do not deduplicate across subjects or by name alone.
WITH content AS (
    SELECT 'summaries' AS kind, id, subject_id, section_type,
           telegram_file_id FROM public.summaries
    WHERE is_active = true AND deleted_at IS NULL
    UNION ALL
    SELECT 'drawings', id, subject_id, section_type,
           telegram_file_id FROM public.drawings
    WHERE is_active = true AND deleted_at IS NULL
)
SELECT kind, subject_id, section_type, count(*) AS candidate_rows, array_agg(id) AS row_ids
FROM content
WHERE nullif(btrim(telegram_file_id), '') IS NOT NULL
GROUP BY kind, subject_id, section_type, telegram_file_id
HAVING count(*) > 1;

ROLLBACK;
