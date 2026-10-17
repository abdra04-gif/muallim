-- Трудные строки книги: страница и строка, сколько читали, средний балл, ошибок (топ-40).
SELECT
    page,
    line,
    item_id,
    item_text,
    COUNT(*) AS attempts,
    COUNT(DISTINCT pseudonym) AS learners,
    ROUND(AVG(score), 1) AS avg_score,
    SUM(errors) AS errors,
    ROUND(100.0 * SUM(CASE WHEN score >= 80 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pass_rate_pct
FROM v_attempts
WHERE model_version <> 'stub'
GROUP BY page, line, item_id, item_text
ORDER BY avg_score ASC, errors DESC, attempts DESC
LIMIT 40
