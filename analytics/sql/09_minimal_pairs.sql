-- Пары «Обратите внимание» (минимальные пары Максуди): какие путают чаще всего.
SELECT
    page,
    line,
    item_text,
    COUNT(*) AS attempts,
    ROUND(AVG(score), 1) AS avg_score,
    SUM(errors) AS errors
FROM v_attempts
WHERE model_version <> 'stub' AND item_note LIKE 'Обратите внимание%'
GROUP BY page, line, item_text
ORDER BY avg_score ASC, errors DESC
