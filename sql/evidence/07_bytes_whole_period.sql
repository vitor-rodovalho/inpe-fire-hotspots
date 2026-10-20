-- Evidência do particionamento, parte 2 de 2: a mesma conta de
-- 06_bytes_one_day.sql, sem filtro de data. A view aceita porque já traz o
-- filtro da data de corte, mas lê todas as partições das duas Silvers.
--   DRY_RUN=1 bash sql/run_sql.sh sql/evidence/07_bytes_whole_period.sql
-- Direto na Silver, a mesma consulta sem filtro é recusada
-- (require_partition_filter):
--   bq query --use_legacy_sql=false 'SELECT COUNT(*) FROM focos.silver_focos_historico'

SELECT estado, origem, COUNT(*) AS focos
FROM `{{DATASET}}.vw_focos_unificada`
GROUP BY estado, origem
ORDER BY focos DESC;
