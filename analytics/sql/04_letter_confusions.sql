-- Матрица путаниц: какую букву ученики произносят вместо нужной (топ-30).
SELECT
    e.expected,
    e.heard,
    COUNT(*) AS times,
    COUNT(DISTINCT a.learner_id) AS learners
FROM detected_errors e
JOIN attempts a ON a.id = e.attempt_id
WHERE e.kind = 'letter_substitution' AND a.model_version <> 'stub'
GROUP BY e.expected, e.heard
ORDER BY times DESC
LIMIT 30
