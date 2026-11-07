-- Ошибки по когортам из анкеты: пол, возраст, намаз, опыт чтения, родной язык (FR-65, ADR-0081).
-- Для проверки гипотез и публикаций. Только агрегаты под псевдонимом, без имени и Telegram ID;
-- группы меньше 5 учеников скрыты — по маленькой группе можно узнать человека.
-- Только настоящая модель (не заглушка) и только ученики с согласием на исследование.
WITH people AS (
    SELECT l.id AS learner_id, 'gender' AS dimension, p.gender AS value
    FROM learners l JOIN learner_profiles p ON p.learner_id = l.id WHERE l.research_consent
    UNION ALL
    SELECT l.id, 'age_group', p.age_group
    FROM learners l JOIN learner_profiles p ON p.learner_id = l.id WHERE l.research_consent
    UNION ALL
    SELECT l.id, 'prayer', p.prayer
    FROM learners l JOIN learner_profiles p ON p.learner_id = l.id WHERE l.research_consent
    UNION ALL
    SELECT l.id, 'arabic_reading', p.arabic_reading
    FROM learners l JOIN learner_profiles p ON p.learner_id = l.id WHERE l.research_consent
    UNION ALL
    SELECT l.id, 'native_language', p.native_language
    FROM learners l JOIN learner_profiles p ON p.learner_id = l.id WHERE l.research_consent
)
SELECT
    pe.dimension,
    pe.value,
    COUNT(DISTINCT pe.learner_id) AS learners,
    COUNT(DISTINCT a.id) AS attempts,
    COUNT(e.id) AS errors,
    ROUND(1.0 * COUNT(e.id) / NULLIF(COUNT(DISTINCT a.id), 0), 2) AS errors_per_attempt
FROM people pe
JOIN attempts a ON a.learner_id = pe.learner_id AND a.model_version <> 'stub'
LEFT JOIN detected_errors e ON e.attempt_id = a.id
WHERE pe.value IS NOT NULL
GROUP BY pe.dimension, pe.value
HAVING COUNT(DISTINCT pe.learner_id) >= 5
ORDER BY pe.dimension, learners DESC
