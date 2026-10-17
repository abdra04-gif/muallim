-- Жалобы «бот ошибся»: какие карточки и причины чаще всего (ADR-0020).
SELECT
    a.item_id,
    r.reason,
    COUNT(*) AS reports,
    COUNT(DISTINCT r.learner_id) AS learners,
    ROUND(AVG(a.score), 1) AS avg_score_of_disputed
FROM learner_reports r
JOIN attempts a ON a.id = r.attempt_id
WHERE a.model_version <> 'stub'
GROUP BY a.item_id, r.reason
ORDER BY reports DESC
