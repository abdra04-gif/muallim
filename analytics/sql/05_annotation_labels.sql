-- Разметка: согласие разметчиков с ботом — последняя метка каждого разметчика (docs/data/annotation-guide.md).
-- agree — бот услышал верно, fix — разметчик исправил; прежние метки разметчика — история, не считаются.
-- source — откуда метка: excel (пакет tasks.csv) или telegram (FR-17); секунды на запись — только Telegram.
WITH latest AS (
    SELECT
        an.attempt_id,
        an.annotator,
        an.label,
        COALESCE(an.source, 'excel') AS source,
        an.seconds_spent,
        ROW_NUMBER() OVER (
            PARTITION BY an.attempt_id, an.annotator ORDER BY an.created_at DESC, an.id DESC
        ) AS rn
    FROM annotations an
    WHERE an.label IN ('agree', 'fix', 'audio_unusable', 'off_task')  -- метки руководства 2.0
)
SELECT
    l.annotator,
    l.source,
    l.label,
    a.verdict AS bot_verdict,
    COUNT(*) AS attempts,
    ROUND(AVG(l.seconds_spent), 1) AS avg_seconds
FROM latest l
JOIN attempts a ON a.id = l.attempt_id
WHERE l.rn = 1 AND a.model_version <> 'stub'
GROUP BY l.annotator, l.source, l.label, a.verdict
ORDER BY l.annotator, l.source, l.label, a.verdict
