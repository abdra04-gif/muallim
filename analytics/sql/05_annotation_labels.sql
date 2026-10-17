-- Разметка: насколько вердикт модели совпал с мнением разметчика (docs/data/annotation-guide.md).
SELECT
    an.label,
    a.verdict AS model_verdict,
    COUNT(*) AS attempts
FROM annotations an
JOIN attempts a ON a.id = an.attempt_id
WHERE an.detected_error_id IS NULL
GROUP BY an.label, a.verdict
ORDER BY an.label, a.verdict
