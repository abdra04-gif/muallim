-- Активность учеников (только псевдонимы — без Telegram ID).
SELECT
    l.pseudonym,
    COUNT(a.id) AS attempts,
    COUNT(DISTINCT a.item_id) AS items_tried,
    ROUND(AVG(a.score), 1) AS avg_score,
    MIN(a.created_at) AS first_attempt,
    MAX(a.created_at) AS last_attempt
FROM learners l
JOIN attempts a ON a.learner_id = l.id
WHERE a.model_version <> 'stub'
GROUP BY l.pseudonym
ORDER BY attempts DESC
