# -*- coding: utf-8 -*-
"""Etapa 2 do Radar: dados ABERTOS do ONS (portal dados.ons.org.br, bucket S3 público),
lidos direto com DuckDB. Gera no I:

  cadastro_ufv.parquet   - usinas fotovoltaicas ativas: operador, SPE, UF, subsistema, entrada, MW
  conjunto_ufv.parquet   - vínculo usina x conjunto (usina_conjunto)
  publico_mensal.parquet - restricao_coff_fotovoltaica_detail agregado por usina x mês x meia-hora
                           (qualidade da irradiância, geração verificada/estimada, cortes)
  publico_nuvem.parquet  - nuvem irradiância x geração por usina x mês x faixa de 50 W/m² (quantis)
  publico_celula.parquet - mediana da geração verificada por usina x mês x meia-hora x faixa de 100 W/m²
  perfil_irr_uf.parquet  - perfil típico de irradiância por UF x mês x meia-hora (mediana pública)
"""
import os, duckdb

try:
    from _caminhos import DADOS as OUT_FINAL
except ImportError:
    OUT_FINAL = os.environ.get('RADAR_DADOS', os.path.join('.', 'dados'))
# escreve primeiro em disco local (o Google Drive é lento para arquivos grandes e trava o COPY do DuckDB), depois copia
OUT = os.path.join(os.environ.get('LOCALAPPDATA', r'C:\Temp'), 'radar_funcoes_solar', 'dados')
os.makedirs(OUT, exist_ok=True); os.makedirs(OUT_FINAL, exist_ok=True)
S3 = 's3://ons-aws-prod-opendata/dataset'
con = duckdb.connect()
con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region='sa-east-1';")
con.execute("SET threads TO 4; SET memory_limit='6GB';")


def salva(nome, sql):
    p = os.path.join(OUT, nome).replace('\\', '/')
    con.execute(f"COPY ({sql}) TO '{p}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    n = con.execute(f"SELECT count(*) FROM read_parquet('{p}')").fetchone()[0]
    print(f'{nome}: {n} linhas', flush=True)


salva('cadastro_ufv.parquet', f"""
SELECT regexp_extract(ceg, '([0-9]{{6}}-[0-9])') AS ceg7,
       any_value(ceg) AS ceg_completo, any_value(nom_usina) AS nom_usina,
       any_value(nom_agenteoperador) AS operador, any_value(nom_agenteproprietario) AS proprietario,
       any_value(id_estado) AS uf, any_value(id_subsistema) AS subsistema,
       any_value(nom_modalidadeoperacao) AS modalidade,
       min(dat_entradaoperacao) AS entrada_op, round(sum(val_potenciaefetiva), 2) AS pot_mw,
       count(*) AS n_ug
FROM read_parquet('{S3}/capacidade-geracao/*.parquet', union_by_name=true)
WHERE nom_tipousina = 'FOTOVOLTAICA' AND dat_desativacao IS NULL
GROUP BY 1""")

salva('conjunto_ufv.parquet', f"""
SELECT regexp_extract(ceg, '([0-9]{{6}}-[0-9])') AS ceg7, ceg AS ceg_completo, id_ons_usina, nom_usina,
       id_ons_conjunto, nom_conjunto, id_subsistema, estad_id AS uf,
       dat_iniciorelacionamento, dat_fimrelacionamento
FROM read_parquet('{S3}/usina_conjunto/*.parquet', union_by_name=true)
WHERE id_tipousina = 'UFV'""")

BASE = f"""
SELECT regexp_extract(ceg, '([0-9]{{6}}-[0-9])') AS ceg7, id_ons, nom_usina, nom_conjuntousina, id_estado AS uf,
       din_instante, year(din_instante)*100 + month(din_instante) AS ano_mes, month(din_instante) AS mes,
       strftime(din_instante, '%H:%M') AS meia_hora,
       val_irradianciaverificado AS irr, flg_dadoirradianciainvalido AS irr_invalida,
       val_geracaoestimada AS ger_est, val_geracaoverificada AS ger_ver,
       lag(val_irradianciaverificado) OVER (PARTITION BY ceg ORDER BY din_instante) AS irr_ant
FROM read_parquet('{S3}/restricao_coff_fotovoltaica_detail_tm/*.parquet', union_by_name=true)
"""

salva('publico_mensal.parquet', f"""
WITH b AS ({BASE})
SELECT ceg7, any_value(id_ons) AS id_ons, any_value(nom_usina) AS nom_usina, any_value(nom_conjuntousina) AS nom_conjunto,
       any_value(uf) AS uf, ano_mes, mes, meia_hora,
       count(*) AS n,
       sum(CASE WHEN irr_invalida THEN 1 ELSE 0 END) AS n_irr_invalida,
       sum(CASE WHEN irr IS NULL THEN 1 ELSE 0 END) AS n_irr_nula,
       sum(CASE WHEN irr > 50 AND irr = irr_ant THEN 1 ELSE 0 END) AS n_irr_congelada,
       sum(CASE WHEN irr_invalida OR irr IS NULL OR (irr > 50 AND irr = irr_ant) THEN 1 ELSE 0 END) AS n_irr_ruim,
       avg(CASE WHEN NOT irr_invalida THEN irr END) AS irr_media_valida,
       quantile_cont(CASE WHEN NOT irr_invalida THEN irr END, 0.5) AS irr_mediana_valida,
       avg(ger_ver) AS ger_ver_media, max(ger_ver) AS ger_ver_max,
       quantile_cont(ger_ver, 0.99) AS ger_ver_p99,
       avg(ger_est) AS ger_est_media, max(ger_est) AS ger_est_max,
       sum(CASE WHEN ger_est - ger_ver > 0.05 * ger_est AND ger_est > 0.5 THEN 1 ELSE 0 END) AS n_corte,
       sum(CASE WHEN NOT irr_invalida AND irr > 200 AND coalesce(ger_est, 0) < 0.01 THEN 1 ELSE 0 END) AS n_ref_zero_dia,
       sum(CASE WHEN NOT irr_invalida AND irr > 200 AND coalesce(ger_est, 0) < 0.01 AND ger_ver > 0.5 THEN 1 ELSE 0 END) AS n_ref_zero_gerando,
       sum(CASE WHEN NOT irr_invalida AND irr > 200 THEN 1 ELSE 0 END) AS n_dia_valido,
       sum(greatest(ger_est - ger_ver, 0)) * 0.5 AS mwh_corte
FROM b GROUP BY ceg7, ano_mes, mes, meia_hora""")

salva('publico_nuvem.parquet', f"""
WITH b AS ({BASE})
SELECT ceg7, mes, cast(floor(irr / 50) * 50 AS INTEGER) AS irr_bin,
       count(*) AS n,
       quantile_cont(ger_ver, 0.1) AS ger_p10, quantile_cont(ger_ver, 0.5) AS ger_p50, quantile_cont(ger_ver, 0.9) AS ger_p90,
       quantile_cont(ger_est, 0.5) AS est_p50, max(ger_ver) AS ger_max
FROM b WHERE NOT irr_invalida AND irr >= 0 AND irr <= 1400
      AND NOT (irr > 50 AND irr = irr_ant)  -- descarta leitura congelada (sensor travado marca sol de madrugada)
GROUP BY ceg7, mes, irr_bin""")

salva('publico_celula.parquet', f"""
WITH b AS ({BASE})
SELECT ceg7, mes, meia_hora, cast(floor(irr / 100) * 100 AS INTEGER) AS irr_bin,
       count(*) AS n, quantile_cont(ger_ver, 0.5) AS ger_p50, quantile_cont(ger_ver, 0.9) AS ger_p90,
       quantile_cont(ger_est, 0.5) AS est_p50
FROM b WHERE NOT irr_invalida AND irr >= 0 AND irr <= 1400
GROUP BY ceg7, mes, meia_hora, irr_bin""")

salva('perfil_irr_uf.parquet', f"""
WITH b AS ({BASE})
SELECT uf, mes, meia_hora, count(*) AS n,
       quantile_cont(irr, 0.5) AS irr_mediana, avg(irr) AS irr_media, quantile_cont(irr, 0.9) AS irr_p90
FROM b WHERE NOT irr_invalida AND irr >= 0 AND irr <= 1400 AND NOT (irr > 50 AND irr = irr_ant)
GROUP BY uf, mes, meia_hora""")
import shutil
for f in os.listdir(OUT):
    if f.endswith('.parquet'):
        shutil.copy2(os.path.join(OUT, f), os.path.join(OUT_FINAL, f))
print('fim (copiado para o I:)')
