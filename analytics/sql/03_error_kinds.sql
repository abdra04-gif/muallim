-- Какие типы ошибок находит система и как часто.
SELECT
    e.kind,
    COUNT(*) AS errors,
    COUNT(DISTINCT e.attempt_id) AS attempts_with_kind
FROM detected_errors e
JOIN attempts a ON a.id = e.attempt_id
WHERE a.model_version <> 'stub'
GROUP BY e.kind
ORDER BY errors DESC
