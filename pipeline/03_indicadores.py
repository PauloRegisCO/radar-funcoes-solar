# -*- coding: utf-8 -*-
"""Etapa 3 do Radar: indicadores por usina a partir de celulas.parquet, curvas100.parquet e dos
dados abertos. Tudo ONS x ONS ou ONS x cadastro; nenhum modelo próprio.

Regras de versão (aprendidas nos dados):
  * A mesma função pode estar em mais de um zip (ex.: 202512 e a revisão 202605): a chave de um
    arquivo é (zip, revisada, nome). Nunca juntar pelo nome sozinho.
  * No lote do art. 4º, usina madura tem UM arquivo (zip 202308) com set/23..mar/24; usina jovem tem
    UM ARQUIVO POR MÊS (zip 202308 cobre set, 202309 cobre out, ...). A "função do art. 4º" de uma
    usina é, portanto, COMPOSTA: para cada mês, o arquivo cuja vigência começa naquele mês; se não
    houver, o arquivo de vigência 01/09/2023.
  * Vigente 2024/2025/2026 = arquivo com início de vigência naquele ano, o mais recente
    (data do arquivo, depois revisada, depois zip).
Saídas: versoes, energia_versoes, celulas_status, tetos_mes, telemetria_mes, vies_publico,
indicadores_usina (todos .parquet em I:\...\radar_funcoes_solar\dados).
"""
import os, numpy as np, pandas as pd

try:
    from _caminhos import DADOS as D
except ImportError:
    D = os.environ.get('RADAR_DADOS', os.path.join('.', 'dados'))
cel = pd.read_parquet(os.path.join(D, 'celulas.parquet'))
cur = pd.read_parquet(os.path.join(D, 'curvas100.parquet'))
cad = pd.read_parquet(os.path.join(D, 'cadastro_ufv.parquet')).rename(columns={'ceg7': 'ceg'})
conj = pd.read_parquet(os.path.join(D, 'conjunto_ufv.parquet')).rename(columns={'ceg7': 'ceg'})
pub_m = pd.read_parquet(os.path.join(D, 'publico_mensal.parquet')).rename(columns={'ceg7': 'ceg'})
pub_c = pd.read_parquet(os.path.join(D, 'publico_celula.parquet')).rename(columns={'ceg7': 'ceg'})
perfil = pd.read_parquet(os.path.join(D, 'perfil_irr_uf.parquet'))
DIAS = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30, 7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}
MESES_ART4 = [9, 10, 11, 12, 1, 2, 3]
for df in (cel, cur):
    df['chave'] = df.zip_mes.astype(str) + np.where(df.revisada, 'R', '') + '|' + df.arquivo

# ---------- catálogo de arquivos
arq = cel.groupby(['chave', 'lote', 'zip_mes', 'revisada', 'ceg', 'ident', 'data_arquivo', 'inicio_vigencia']).size().reset_index(name='n_cel')
arq['ano_vig'] = arq.inicio_vigencia.str[:4].astype(int)
arq['mes_vig'] = arq.inicio_vigencia.str[4:6].astype(int)

# art. 4º composto: para cada (ceg, mes) escolhe o arquivo cuja vigência começa no mês; senão o de set/23
a4 = arq[arq.lote == 'art4']
base = a4[a4.inicio_vigencia == '20230901'][['ceg', 'chave']].rename(columns={'chave': 'chave_base'})
mensal = a4[['ceg', 'mes_vig', 'chave']].rename(columns={'mes_vig': 'mes', 'chave': 'chave_mes'})
grade = pd.MultiIndex.from_product([a4.ceg.unique(), MESES_ART4], names=['ceg', 'mes']).to_frame(index=False)
art4_map = grade.merge(base, on='ceg', how='left').merge(mensal, on=['ceg', 'mes'], how='left')
art4_map['chave'] = art4_map.chave_mes.fillna(art4_map.chave_base)
art4_map = art4_map.dropna(subset=['chave'])[['ceg', 'mes', 'chave']]
regime = a4.groupby('ceg').chave.nunique().rename('n_arquivos_art4').reset_index()
# regime pela MATURIDADE (NT-0030 item 6): menos de 12 meses de operação em 01/09/2023 -> função mensal
regime = regime.merge(cad[['ceg', 'entrada_op']], on='ceg', how='left')
regime['entrada_op'] = pd.to_datetime(regime.entrada_op, errors='coerce')
regime['regime'] = np.where(regime.entrada_op.isna(), np.where(regime.n_arquivos_art4 > 1, 'mensal', 'unica'),
                            np.where(regime.entrada_op > pd.Timestamp('2022-09-01'), 'mensal', 'unica'))
regime = regime.drop(columns=['entrada_op'])

# vigentes: arquivo mais recente por (ceg, ano de vigência)
vig = arq[arq.lote == 'vigente'].sort_values(['ceg', 'ano_vig', 'data_arquivo', 'revisada', 'zip_mes'])
vig_last = vig.groupby(['ceg', 'ano_vig']).tail(1)
vig_last = vig_last[vig_last.ano_vig.isin([2024, 2025, 2026])].assign(versao=lambda d: 'vig' + d.ano_vig.astype(str))
versoes = pd.concat([vig_last[['ceg', 'chave', 'versao', 'zip_mes', 'data_arquivo', 'inicio_vigencia', 'revisada']],
                     a4.assign(versao='art4_' + a4.zip_mes.astype(str))[['ceg', 'chave', 'versao', 'zip_mes', 'data_arquivo', 'inicio_vigencia', 'revisada']]])
versoes.to_parquet(os.path.join(D, 'versoes.parquet'), index=False)
art4_map.to_parquet(os.path.join(D, 'art4_composto.parquet'), index=False)

# ---------- cadastro e conjunto
conj = conj.sort_values(['ceg', 'dat_iniciorelacionamento'])
conj_atual = conj.groupby('ceg').tail(1)[['ceg', 'id_ons_usina', 'nom_conjunto', 'id_ons_conjunto']]
usinas = a4.groupby('ceg').ident.first().reset_index().merge(cad, on='ceg', how='left').merge(conj_atual, on='ceg', how='left').merge(regime, on='ceg', how='left')
usinas['nom_usina'] = usinas.nom_usina.fillna(usinas.ident)
# usina sem vínculo em usina_conjunto e com nom_conjuntousina vazio no dado público responde sozinha:
# o ONS trata a própria usina como o seu 'conjunto' — exibir o nome dela (pedido do Paulo, 31/08/2026)
usinas['nom_conjunto'] = usinas.nom_conjunto.fillna(usinas.nom_usina)

# ---------- perfil típico de irradiância
perfil_uf = perfil.groupby(['uf', 'mes', 'meia_hora']).irr_mediana.median().reset_index()
perfil_nac = perfil.groupby(['mes', 'meia_hora']).irr_mediana.median().reset_index().rename(columns={'irr_mediana': 'irr_nac'})


def avalia_vetorizado(cv, alvo, chaves_extra=()):
    """cv: curvas (ceg, versao, mes, meia_hora, irr, mw) passo 100; alvo: (ceg, mes, meia_hora, x, ...).
    Interpola linearmente entre os degraus de 100 que cercam x."""
    a = alvo.copy()
    a['irr_lo'] = (np.floor(a.x / 100) * 100).astype(int); a['irr_hi'] = a.irr_lo + 100
    lo = cv.rename(columns={'irr': 'irr_lo', 'mw': 'mw_lo'})
    hi = cv.rename(columns={'irr': 'irr_hi', 'mw': 'mw_hi'})
    k = ['ceg', 'mes', 'meia_hora']
    a = a.merge(lo, on=k + ['irr_lo'], how='inner').merge(hi, on=k + ['versao', 'irr_hi'], how='left')
    a['f'] = np.where(a.mw_hi.notna(), a.mw_lo + (a.mw_hi - a.mw_lo) * (a.x - a.irr_lo) / 100, np.where(a.x == a.irr_lo, a.mw_lo, np.nan))
    return a.dropna(subset=['f'])


# curvas por versão: art4_final (composto) + vigentes + mensais do lote
cur_a4 = cur.merge(art4_map, on=['ceg', 'mes', 'chave']).assign(versao='art4_final')
cur_v = pd.concat([cur_a4, cur.merge(versoes[['chave', 'versao']], on='chave')])
cur_v = cur_v[cur_v.mes.isin(MESES_ART4)].dropna(subset=['mw'])[['ceg', 'versao', 'mes', 'meia_hora', 'irr', 'mw']]

# ---------- energia normalizada por versão e mês
alvo = usinas[['ceg', 'uf']].merge(perfil_uf, on='uf', how='left').merge(perfil_nac, on=['mes', 'meia_hora'], how='left')
alvo['x'] = alvo.irr_mediana.fillna(alvo.irr_nac)
alvo = alvo.dropna(subset=['x'])[['ceg', 'mes', 'meia_hora', 'x']]
alvo = alvo[alvo.mes.isin(MESES_ART4)]
av = avalia_vetorizado(cur_v, alvo)
av['mwh'] = av.f * 0.5 * av.mes.map(DIAS)
energia = av.groupby(['ceg', 'versao', 'mes']).mwh.sum().reset_index()
energia.to_parquet(os.path.join(D, 'energia_versoes.parquet'), index=False)
# energia "pareada": art4 e cada vigente somadas SÓ nas células (mês, meia-hora) em que as duas têm curva
# (evita que uma vigente com muitas células vazias pareça "menos energética")
a4c = av[av.versao == 'art4_final'][['ceg', 'mes', 'meia_hora', 'mwh']].rename(columns={'mwh': 'a'})
pares = []
for v in ['vig2024', 'vig2025', 'vig2026']:
    b = av[av.versao == v][['ceg', 'mes', 'meia_hora', 'mwh']].rename(columns={'mwh': 'b'})
    m = a4c.merge(b, on=['ceg', 'mes', 'meia_hora'])
    s = m.groupby(['ceg', 'mes']).agg(a=('a', 'sum'), b=('b', 'sum'), n_cel=('meia_hora', 'nunique')).reset_index().assign(versao=v)
    pares.append(s)
energia_par = pd.concat(pares)
energia_par.to_parquet(os.path.join(D, 'energia_pareada.parquet'), index=False)
# completude de cada versão (fração de células vazias) para sinalizar vigente incompleta
compl = cel.groupby('chave').agg(n_cel=('mes', 'size'), n_vazias=('vazia', 'sum')).reset_index()
compl['frac_vazia'] = compl.n_vazias / compl.n_cel
versoes = versoes.merge(compl[['chave', 'frac_vazia']], on='chave', how='left')
versoes.to_parquet(os.path.join(D, 'versoes.parquet'), index=False)

# ---------- status das células do art. 4º composto
cf = cel.merge(art4_map, on=['ceg', 'mes', 'chave']).merge(usinas[['ceg', 'uf', 'pot_mw']], on='ceg', how='left')
cf = cf.merge(perfil_uf, on=['uf', 'mes', 'meia_hora'], how='left').merge(perfil_nac, on=['mes', 'meia_hora'], how='left')
cf['irr_tipica'] = cf.irr_mediana.fillna(cf.irr_nac)
LIMIAR_FP = 30  # W/m²: acima disso a meia-hora conta como "de dia" (30 em vez de 15 para as bordas do dia pesarem menos)
cf['no_fotoperiodo'] = cf.irr_tipica > LIMIAR_FP
v25 = cel.merge(vig_last[vig_last.versao == 'vig2025'][['chave']], on='chave')[['ceg', 'mes', 'meia_hora', 'vazia']].rename(columns={'vazia': 'vazia_vig2025'})
cf = cf.merge(v25, on=['ceg', 'mes', 'meia_hora'], how='left')
cf['status'] = np.select(
    [cf.vazia & cf.no_fotoperiodo, cf.vazia, cf.n_degraus.fillna(0).between(1, 5), cf.irr_max_grid.fillna(0) >= 1000],
    ['vazia_fotoperiodo', 'fora_fotoperiodo', 'poucos_degraus', 'completa'], 'normal')
cf['teto_pct'] = cf.mw_max / cf.pot_mw
cf = cf.sort_values(['ceg', 'mes', 'meia_hora'])
cf['mw600_ant'] = cf.groupby(['ceg', 'mes']).mw600.shift(1)
cf['salto_pct'] = (cf.mw600 - cf.mw600_ant).abs() / cf[['mw600', 'mw600_ant']].max(axis=1)
cf['nao_monotona'] = cf.quedas.fillna(0) > 0
cf['saturacao_precoce'] = (cf.irr_sat90.fillna(9999) < 600) & (cf.irr_max_grid.fillna(0) >= 800)
# valor alto em irradiância baixa: a 200 W/m² (um quinto do sol pleno) a curva já devolve mais de 50% do teto do mês
# (calibração com poucos pontos em sol baixo; uma curva normal fica em 20-35% nesse ponto)
teto_mes = cf.groupby(['ceg', 'mes']).mw_max.transform('max')
cf['alto_baixa_irr'] = (cf.mw200.fillna(0) > 0.50 * teto_mes.fillna(0)) & (teto_mes.fillna(0) > 0)
cf[['ceg', 'mes', 'meia_hora', 'chave', 'status', 'vazia', 'vazia_vig2025', 'n_degraus', 'mw_max', 'teto_pct', 'mw200', 'mw400', 'mw600', 'mw800', 'mw1000',
    'salto_pct', 'nao_monotona', 'saturacao_precoce', 'alto_baixa_irr', 'irr_sat90', 'irr_tipica']].to_parquet(os.path.join(D, 'celulas_status.parquet'), index=False)

tetos = cf.groupby(['ceg', 'mes']).agg(mw_max=('mw_max', 'max'), pot_mw=('pot_mw', 'first')).reset_index()
tetos['teto_pct'] = tetos.mw_max / tetos.pot_mw
tetos.to_parquet(os.path.join(D, 'tetos_mes.parquet'), index=False)

# ---------- regime mensal: salto entre meses consecutivos da função a 800 W/m² ao meio-dia (por MW)
m12 = cf[cf.meia_hora == '12:00'][['ceg', 'mes', 'mw800', 'pot_mw']].copy()
m12['ordem'] = m12.mes.map({m: i for i, m in enumerate(MESES_ART4)})
m12 = m12.sort_values(['ceg', 'ordem'])
m12['var'] = m12.groupby('ceg').mw800.pct_change()
var_mensal = m12.groupby('ceg').agg(var_max_abs=('var', lambda s: float(np.nanmax(np.abs(s))) if s.notna().any() else np.nan)).reset_index()
m12[['ceg', 'mes', 'mw800', 'var']].to_parquet(os.path.join(D, 'meio_dia_800.parquet'), index=False)

# ---------- telemetria pública: qualidade contada SÓ no fotoperíodo típico (o ONS marca inválida a irradiância da madrugada/anoitecer)
pub_fp = pub_m.drop(columns=['uf'], errors='ignore').merge(usinas[['ceg', 'uf']], on='ceg', how='left').merge(perfil_uf, on=['uf', 'mes', 'meia_hora'], how='left').merge(perfil_nac, on=['mes', 'meia_hora'], how='left')
pub_fp['irr_tipica'] = pub_fp.irr_mediana.fillna(pub_fp.irr_nac)
pub_dia = pub_fp[pub_fp.irr_tipica > LIMIAR_FP]
tele = pub_dia.groupby('ceg').agg(n=('n', 'sum'), inval=('n_irr_invalida', 'sum'), cong=('n_irr_congelada', 'sum'), ruim=('n_irr_ruim', 'sum')).reset_index()
tele = tele.merge(pub_m.groupby('ceg').agg(ger_ver_max_bruto=('ger_ver_max', 'max'), mwh_corte=('mwh_corte', 'sum'),
                                          n_ref_zero_dia=('n_ref_zero_dia', 'sum'), n_ref_zero_gerando=('n_ref_zero_gerando', 'sum'), n_dia_valido=('n_dia_valido', 'sum')).reset_index(), on='ceg', how='left')
rz = pub_m.groupby(['ceg', 'ano_mes']).agg(z=('n_ref_zero_dia', 'sum'), d=('n_dia_valido', 'sum')).reset_index()
rz = rz[(rz.d >= 100) & (rz.z >= 0.8 * rz.d)]
tele = tele.merge(rz.groupby('ceg').size().rename('n_meses_ref_zero').reset_index(), on='ceg', how='left')
# pico típico = mediana, entre os meses, do maior percentil 99 do mês (pub_m é por meia-hora: primeiro o máximo dentro do mês,
# depois a mediana entre meses); robusto aos meses com medição espúria (máximo bruto chega a 5x a potência)
pico_mes = pub_m.groupby(['ceg', 'ano_mes']).ger_ver_p99.max().reset_index()
tele = tele.merge(pico_mes.groupby('ceg').ger_ver_p99.median().rename('ger_ver_max').reset_index(), on='ceg', how='left')
tele['pct_irr_invalida'] = tele.inval / tele.n
tele['pct_irr_congelada'] = tele.cong / tele.n
tele['pct_irr_ruim'] = tele.ruim / tele.n   # união (inválida OU nula OU congelada), nunca passa de 100%
tele_mes = pub_dia.groupby(['ceg', 'ano_mes']).agg(n=('n', 'sum'), ruim=('n_irr_ruim', 'sum')).reset_index()
tele_mes = tele_mes.merge(pub_m.groupby(['ceg', 'ano_mes']).mwh_corte.sum().reset_index(), on=['ceg', 'ano_mes'], how='left')
tele_mes['pct_ruim'] = tele_mes.ruim / tele_mes.n
tele_mes.to_parquet(os.path.join(D, 'telemetria_mes.parquet'), index=False)

# ---------- função do art. 4º x nuvem pública
pc = pub_c[pub_c.n >= 8]
alvo_v = pc[pc.est_p50 > 0.5][['ceg', 'mes', 'meia_hora', 'irr_bin', 'n', 'ger_p50', 'ger_p90', 'est_p50']].copy()
alvo_v['x'] = alvo_v.irr_bin + 50
vies = avalia_vetorizado(cur_a4[['ceg', 'versao', 'mes', 'meia_hora', 'irr', 'mw']], alvo_v).rename(columns={'f': 'f_art4'})
vies = vies[['ceg', 'mes', 'meia_hora', 'irr_bin', 'n', 'ger_p50', 'ger_p90', 'est_p50', 'f_art4']]
vies.to_parquet(os.path.join(D, 'vies_publico.parquet'), index=False)
vies_u = vies.groupby('ceg').apply(lambda d: pd.Series({
    'vies_art4_vs_est_ons': float((d.f_art4 * d.n).sum() / (d.est_p50 * d.n).sum() - 1),
    'vies_art4_vs_p90': float((d.f_art4 * d.n).sum() / (d.ger_p90 * d.n).sum() - 1),
    'vies_est_ons_vs_p50': float((d.est_p50 * d.n).sum() / (d.ger_p50 * d.n).sum() - 1),
    'n_pontos_publico': int(d.n.sum())})).reset_index()


# ---------- consolidação
def delta_comum(v):
    """art4 x vigente v nas CÉLULAS em comum (mês e meia-hora com curva nas duas), exigindo ≥2 meses e ≥60 células."""
    s = energia_par[energia_par.versao == v].groupby('ceg').agg(a=('a', 'sum'), b=('b', 'sum'), n_meses=('mes', 'nunique'), n_cel=('n_cel', 'sum')).reset_index()
    s['delta_' + v] = np.where((s.n_meses >= 2) & (s.n_cel >= 60), s.a / s.b - 1, np.nan)
    return s[['ceg', 'delta_' + v]]
E = energia[energia.versao == 'art4_final'].groupby('ceg').mwh.sum().rename('mwh_art4').reset_index()
for v in ['vig2024', 'vig2025', 'vig2026']:
    E = E.merge(delta_comum(v), on='ceg', how='left')

g = cf.groupby('ceg').agg(
    n_cel_total=('vazia', 'size'), n_cel_cheias=('vazia', lambda s: int((~s).sum())),
    n_cel_fotoperiodo=('no_fotoperiodo', 'sum'),
    n_vazias_fotoperiodo=('status', lambda s: int((s == 'vazia_fotoperiodo').sum())),
    n_poucos_degraus=('status', lambda s: int((s == 'poucos_degraus').sum())),
    teto_pct_max=('teto_pct', 'max'),
    n_nao_monotona=('nao_monotona', 'sum'),
    n_saltos=('salto_pct', lambda s: int((s > 0.2).sum())),
    n_saturacao_precoce=('saturacao_precoce', 'sum'),
    n_alto_baixa_irr=('alto_baixa_irr', 'sum')).reset_index()
vz = cf[cf.vazia & (cf.vazia_vig2025 == False)].groupby('ceg').size().rename('n_vazia_mas_vig2025_cheia').reset_index()
meses_teto_baixo = tetos[tetos.teto_pct < 0.85].groupby('ceg').size().rename('n_meses_teto_baixo').reset_index()
ind = (usinas.merge(g, on='ceg', how='left').merge(vz, on='ceg', how='left').merge(meses_teto_baixo, on='ceg', how='left')
       .merge(E, on='ceg', how='left').merge(var_mensal, on='ceg', how='left')
       .merge(tele[['ceg', 'pct_irr_invalida', 'pct_irr_congelada', 'pct_irr_ruim', 'ger_ver_max', 'mwh_corte', 'n_ref_zero_dia', 'n_ref_zero_gerando', 'n_dia_valido', 'n_meses_ref_zero']], on='ceg', how='left')
       .merge(vies_u, on='ceg', how='left'))
for c in ['n_meses_teto_baixo', 'n_vazia_mas_vig2025_cheia']:
    ind[c] = ind[c].fillna(0).astype(int)
ind['ger_ver_max_pct'] = ind.ger_ver_max / ind.pot_mw
ind['n_versoes'] = ind.n_arquivos_art4


def sinal(cond2, cond1):
    return np.where(cond2, 2, np.where(cond1, 1, 0))
ind['funcao_vazia'] = ind.n_cel_cheias.fillna(0) == 0
ind['s_buracos'] = sinal(ind.n_vazias_fotoperiodo.fillna(0) >= 10, ind.n_vazias_fotoperiodo.fillna(0) >= 3)
ind['s_teto'] = sinal(ind.n_meses_teto_baixo >= 3, ind.n_meses_teto_baixo >= 1)
# limiares comparados com o valor ARREDONDADO como aparece na tela (3 casas = 0,1 pp), para -4,0% não ficar verde
d25r = ind.delta_vig2025.fillna(0).round(3); vmr = ind.var_max_abs.fillna(0).round(3)
ind['s_onsxons'] = sinal(d25r <= -0.08, d25r <= -0.04)
# Sinal de forma = só os defeitos que prejudicam o agente (curva que desce com mais sol; saltos entre meias-horas).
# Saturação precoce e valor alto com pouco sol aumentam a referência (favorecem o agente) ou são físicos
# (sobredimensionamento, sensor lendo baixo): ficam como informação na página 5, sem acender sinal (decisão de 31/08/2026).
ind['s_forma'] = sinal((ind.n_nao_monotona.fillna(0) >= 5) | (ind.n_saltos.fillna(0) >= 10),
                       (ind.n_nao_monotona.fillna(0) >= 1) | (ind.n_saltos.fillna(0) >= 4))
ind['s_versoes'] = np.where((ind.regime == 'mensal') & ind.var_max_abs.notna(), sinal(vmr >= 0.15, vmr >= 0.08), 0)
ind['s_telemetria'] = sinal(ind.pct_irr_ruim.fillna(0) >= 0.30, ind.pct_irr_ruim.fillna(0) >= 0.15)
vr = ind.vies_art4_vs_est_ons.fillna(0).round(3)
ind['s_vies'] = sinal(vr <= -0.10, vr <= -0.05)
S = [c for c in ind.columns if c.startswith('s_')]
ind['n_fortes'] = (ind[S] == 2).sum(axis=1); ind['n_atencao'] = (ind[S] == 1).sum(axis=1)
ind.to_parquet(os.path.join(D, 'indicadores_usina.parquet'), index=False)
pd.set_option('display.width', 230)
print('usinas sem cadastro:', int(ind.pot_mw.isna().sum()), '| regime:', ind.regime.value_counts().to_dict())
print(ind[S].apply(pd.Series.value_counts).fillna(0).astype(int))
print('usinas', len(ind), '| com >=1 sinal forte:', (ind.n_fortes >= 1).sum())
print(ind[['nom_usina', 'operador', 'pot_mw', 'regime', 'n_vazias_fotoperiodo', 'teto_pct_max', 'delta_vig2024', 'delta_vig2025', 'delta_vig2026', 'var_max_abs', 'pct_irr_invalida', 'vies_art4_vs_est_ons', 'vies_art4_vs_p90', 'n_fortes']].sort_values('n_fortes', ascending=False).head(20).to_string(index=False))
print(ind[['delta_vig2024', 'delta_vig2025', 'delta_vig2026', 'var_max_abs', 'vies_art4_vs_est_ons', 'vies_art4_vs_p90', 'teto_pct_max']].describe().round(3).to_string())
