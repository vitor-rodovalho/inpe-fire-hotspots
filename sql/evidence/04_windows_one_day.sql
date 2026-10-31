-- Evidência: as janelas de 1 hora seguem o horário da detecção, não o da chegada.
-- Escolhe o estado e o dia com mais focos e mostra as janelas desse dia, uma
-- por hora. As janelas são horas reais de fogo, mas calculado_em é o dia do
-- replay. Vale a gravação mais recente de cada janela e estado.
-- Executar: bash sql/run_sql.sh sql/evidence/04_windows_one_day.sql

WITH ultima_gravacao AS (
  SELECT *
  FROM `{{DATASET}}.gold_agregados_janela`
  WHERE DATE(inicio_janela) >= DATE '{{DATA_CORTE}}'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY inicio_janela, estado ORDER BY calculado_em DESC) = 1
),
dia_com_mais_focos AS (
  SELECT DATE(inicio_janela) AS dia, estado
  FROM ultima_gravacao
  GROUP BY dia, estado
  ORDER BY SUM(qtd_focos) DESC
  LIMIT 1
)
SELECT
  u.inicio_janela,
  u.fim_janela,
  u.estado,
  u.qtd_focos,
  u.qtd_sem_frp,
  ROUND(u.frp_medio, 1) AS frp_medio,
  u.calculado_em
FROM ultima_gravacao AS u
JOIN dia_com_mais_focos AS d
  ON DATE(u.inicio_janela) = d.dia AND u.estado = d.estado
ORDER BY u.inicio_janela;
