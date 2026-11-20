-- Трудность карточек: сколько раз читали, средний балл, доля засчитанных — по вердикту («ещё раз» не засчитано, ADR-0088 п. 7).
SELECT
    item_id,
    COUNT(*) AS attempts,
    COUNT(DISTINCT learner_id) AS learners,
    ROUND(AVG(score), 1) AS avg_score,
    ROUND(100.0 * SUM(CASE WHEN verdict IN ('passed', 'excellent') THEN 1 ELSE 0 END) / COUNT(*), 1) AS pass_rate_pct
FROM attempts
WHERE model_version <> 'stub'
GROUP BY item_id
ORDER BY avg_score ASC, attempts DESC
