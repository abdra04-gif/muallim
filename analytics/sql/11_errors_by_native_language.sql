-- Ошибки по родному языку и опыту чтения из анкеты (FR-44, H2.1, ADR-0038); только агрегаты, без Telegram ID.
SELECT
    COALESCE(p.native_language, 'нет анкеты') AS native_language,
    COALESCE(p.arabic_reading, 'нет анкеты') AS arabic_reading,
    COUNT(DISTINCT l.id) AS learners,
    COUNT(DISTINCT a.id) AS attempts,
    COUNT(e.id) AS errors,
    ROUND(1.0 * COUNT(e.id) / NULLIF(COUNT(DISTINCT a.id), 0), 2) AS errors_per_attempt
FROM learners l
JOIN attempts a ON a.learner_id = l.id
LEFT JOIN learner_profiles p ON p.learner_id = l.id
LEFT JOIN detected_errors e ON e.attempt_id = a.id
WHERE a.model_version <> 'stub'
GROUP BY COALESCE(p.native_language, 'нет анкеты'), COALESCE(p.arabic_reading, 'нет анкеты')
ORDER BY learners DESC
