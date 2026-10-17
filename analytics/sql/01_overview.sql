-- Общая картина: сколько учеников, попыток, записей и разметки.
-- Попытки заглушки распознавания (model_version = 'stub') в исследование не входят.
SELECT
    (SELECT COUNT(*) FROM learners) AS learners,
    (SELECT COUNT(*) FROM learners WHERE research_consent) AS learners_with_consent,
    (SELECT COUNT(*) FROM attempts WHERE model_version <> 'stub') AS attempts,
    (SELECT COUNT(*) FROM attempts WHERE model_version <> 'stub' AND audio_sha256 IS NOT NULL)
        AS attempts_with_audio,
    (SELECT COUNT(DISTINCT attempt_id) FROM annotations) AS annotated_attempts
