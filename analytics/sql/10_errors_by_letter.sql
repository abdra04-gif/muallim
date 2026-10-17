-- Ошибки по буквам: сколько раз ошиблись на букве, у скольких учеников, на скольких строках книги.
SELECT
    expected,
    COUNT(*) AS errors,
    COUNT(DISTINCT pseudonym) AS learners,
    COUNT(DISTINCT item_id) AS lines,
    SUM(CASE WHEN kind = 'letter_substitution' THEN 1 ELSE 0 END) AS substitutions,
    SUM(CASE WHEN label IS NOT NULL THEN 1 ELSE 0 END) AS annotated
FROM v_errors
WHERE model_version <> 'stub'
GROUP BY expected
ORDER BY errors DESC
