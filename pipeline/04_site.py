# -*- coding: utf-8 -*-
"""Etapa 4 do Radar: exporta os dados para o site estático (JSON) e copia a página.

Saída: <repo>/site/  ->  index.html, data/index.json, data/usinas/<ceg>.json
O site é publicado no GitHub Pages (repositório radar-funcoes-solar).
"""
import os, json, shutil, numpy as np, pandas as pd

try:
    from _caminhos import DADOS as D
except ImportError:
    D = os.environ.get('RADAR_DADOS', os.path.join('.', 'dados'))
HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(os.path.dirname(HERE), 'site')
os.makedirs(os.path.join(SITE, 'data', 'usinas'), exist_ok=True)

ind = pd.read_parquet(os.path.join(D, 'indicadores_usina.parquet'))
cs = pd.read_parquet(os.path.join(D, 'celulas_status.parquet'))
tet = pd.read_parquet(os.path.join(D, 'tetos_mes.parquet'))
en = pd.read_parquet(os.path.join(D, 'energia_versoes.parquet'))
enp = pd.read_parquet(os.path.join(D, 'energia_pareada.parquet'))
ver = pd.read_parquet(os.path.join(D, 'versoes.parquet'))
cur = pd.read_parquet(os.path.join(D, 'curvas100.parquet'))
tele = pd.read_parquet(os.path.join(D, 'telemetria_mes.parquet'))
try:
    risco = pd.read_parquet(os.path.join(D, 'celulas_risco_mes.parquet'))
except Exception:
    risco = pd.DataFrame(columns=['ceg', 'ano_mes', 'cel', 'vazias', 'frageis'])
nuv = pd.read_parquet(os.path.join(D, 'publico_nuvem.parquet')).rename(columns={'ceg7': 'ceg'})
vies = pd.read_parquet(os.path.join(D, 'vies_publico.parquet'))

HORAS = [f'{h:02d}:{m}' for h in range(5, 21) for m in ('00', '30')][:-1]  # 05:00 .. 20:00 (31)
MESES_ART4 = [9, 10, 11, 12, 1, 2, 3]


def r(x, nd=2):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    return round(float(x), nd)


def iv(x):
    try:
        return 0 if x is None or (isinstance(x, float) and np.isnan(x)) else int(x)
    except (TypeError, ValueError):
        return 0


def sinais(row):
    return {k[2:]: int(row[k]) for k in row.index if k.startswith('s_')}


def limpa(o):
    """Troca NaN/NA por None em qualquer estrutura (JSON válido para o navegador)."""
    if isinstance(o, dict):
        return {k: limpa(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [limpa(v) for v in o]
    if isinstance(o, float) and np.isnan(o):
        return None
    if o is pd.NA or o is pd.NaT:
        return None
    return o


def dump(obj, path):
    json.dump(limpa(obj), open(path, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'), allow_nan=False)


# ---------- index.json
idx = []
for row in ind.sort_values(['nom_conjunto', 'nom_usina']).itertuples():
    d = row._asdict()
    idx.append({
        'ceg': d['ceg'], 'usina': d['nom_usina'], 'id_ons': d.get('id_ons_usina'), 'conjunto': d['nom_conjunto'], 'regime': d.get('regime'),
        'funcao_vazia': bool(d.get('funcao_vazia')), 'n_cel_total': iv(d.get('n_cel_total')),
        'uf': d.get('uf'), 'mw': r(d.get('pot_mw'), 1), 'entrada': str(d.get('entrada_op'))[:10] if d.get('entrada_op') is not None else None,
        'sinais': sinais(ind.loc[row.Index]),
        'fortes': iv(d['n_fortes']), 'atencao': iv(d['n_atencao']),
        'm': {
            'vazias': iv(d.get('n_vazias_fotoperiodo')), 'cel_fp': iv(d.get('n_cel_fotoperiodo')),
            'poucos': iv(d.get('n_poucos_degraus')), 'vazia_vig25': iv(d.get('n_vazia_mas_vig2025_cheia')),
            'teto_max': r(d.get('teto_pct_max'), 3), 'meses_teto_baixo': iv(d.get('n_meses_teto_baixo')),
            'd24': r(d.get('delta_vig2024'), 4), 'd25': r(d.get('delta_vig2025'), 4), 'd26': r(d.get('delta_vig2026'), 4),
            'nao_mono': iv(d.get('n_nao_monotona')), 'saltos': iv(d.get('n_saltos')), 'sat': iv(d.get('n_saturacao_precoce')),
            'versoes': int(d.get('n_versoes') or 1), 'var_max': r(d.get('var_max_abs'), 4),
            'irr_inv': r(d.get('pct_irr_invalida'), 4), 'irr_cong': r(d.get('pct_irr_congelada'), 4), 'irr_ruim': r(d.get('pct_irr_ruim'), 4),
            'ger_max_pct': r(d.get('ger_ver_max_pct'), 3), 'mwh_corte': r(d.get('mwh_corte'), 0),
            'vies_art4': r(d.get('vies_art4_vs_est_ons'), 4), 'vies_p90': r(d.get('vies_art4_vs_p90'), 4), 'vies_est': r(d.get('vies_est_ons_vs_p50'), 4), 'n_pub': iv(d.get('n_pontos_publico')),
            'ref_zero_dia': iv(d.get('n_ref_zero_dia')), 'ref_zero_gerando': iv(d.get('n_ref_zero_gerando')), 'ref_zero_meses': iv(d.get('n_meses_ref_zero')),
            'alto_baixa': iv(d.get('n_alto_baixa_irr')),
        }})
meta = {
    'gerado_em': pd.Timestamp.now().strftime('%d/%m/%Y'), 'n_usinas': len(idx), 'n_conjuntos': int(ind.nom_conjunto.nunique()),
    'n_operadores': int(ind.operador.nunique()), 'prazo': '10/09/2026',
    'total_fortes': int((ind.n_fortes >= 1).sum()),
    'por_sinal': {k[2:]: {'forte': int((ind[k] == 2).sum()), 'atencao': int((ind[k] == 1).sum())} for k in ind.columns if k.startswith('s_')},
}
dump({'meta': meta, 'usinas': idx}, os.path.join(SITE, 'data', 'index.json'))
print('index.json', len(idx))

# ---------- por usina
cur['chave'] = cur.zip_mes.astype(str) + np.where(cur.revisada, 'R', '') + '|' + cur.arquivo
a4map = pd.read_parquet(os.path.join(D, 'art4_composto.parquet'))
m12 = pd.read_parquet(os.path.join(D, 'meio_dia_800.parquet'))
cur_a4 = cur.merge(a4map, on=['ceg', 'mes', 'chave']).assign(versao='art4_final')
ver_sel = ver[ver.versao.isin(['vig2024', 'vig2025', 'vig2026'])]
cur_sel = pd.concat([cur_a4, cur.merge(ver_sel[['chave', 'versao']], on='chave')])
cur_sel = cur_sel[cur_sel.mes.isin(MESES_ART4)]
n_ok = 0
for ceg, g in cs.groupby('ceg'):
    out = {'ceg': ceg}
    # grade de status: mês -> lista de 31 [status, teto_pct, n_degraus]
    grade = {}
    for mes in MESES_ART4:
        gm = g[g.mes == mes].set_index('meia_hora')
        sem_arquivo = len(gm) == 0   # mês sem função no lote (usina ainda não operava)
        grade[mes] = [[gm.loc[h, 'status'], r(gm.loc[h, 'teto_pct'], 3), int(gm.loc[h, 'n_degraus'] or 0), r(gm.loc[h, 'irr_tipica'], 0)] if h in gm.index else [('sem_funcao' if sem_arquivo else 'fora_fotoperiodo'), None, 0, None] for h in HORAS]
    out['grade'] = grade
    # tetos por mês
    out['tetos'] = {int(t.mes): {'mw': r(t.mw_max), 'pct': r(t.teto_pct, 3)} for t in tet[tet.ceg == ceg].itertuples()}
    # energia por versão e mês (todas as células de cada versão) e pareada (só células em comum com o art. 4º)
    e = en[en.ceg == ceg]
    out['energia'] = {v: {int(t.mes): r(t.mwh, 1) for t in e[e.versao == v].itertuples()} for v in e.versao.unique()}
    ep = enp[enp.ceg == ceg]
    out['energia_par'] = {v: {int(t.mes): [r(t.a, 1), r(t.b, 1), int(t.n_cel)] for t in ep[ep.versao == v].itertuples()} for v in ep.versao.unique()}
    vv = ver[(ver.ceg == ceg) & ver.versao.str.startswith('vig')]
    out['versoes'] = {t.versao: {'arquivo': t.chave.split('|')[1], 'zip': t.chave.split('|')[0], 'vigencia': t.inicio_vigencia, 'frac_vazia': r(t.frac_vazia, 3)} for t in vv.itertuples()}
    # curvas (passo 100) por versão, mês, meia-hora
    c = cur_sel[cur_sel.ceg == ceg]
    curvas = {}
    for (v, mes, mh), gc in c.groupby(['versao', 'mes', 'meia_hora']):
        gc = gc.sort_values('irr')
        curvas.setdefault(v, {}).setdefault(int(mes), {})[mh] = [r(x, 2) for x in gc.mw.tolist()]
    out['curvas'] = curvas
    out['curva_irr'] = list(range(0, 1500, 100))
    # forma: células com problemas
    out['forma'] = {
        'nao_mono': [[int(t.mes), t.meia_hora] for t in g[g.nao_monotona].itertuples()],
        'saltos': [[int(t.mes), t.meia_hora, r(t.salto_pct, 3)] for t in g[g.salto_pct > 0.2].itertuples()],
        'sat': [[int(t.mes), t.meia_hora, r(t.irr_sat90, 0)] for t in g[g.saturacao_precoce].itertuples()],
        'alto': [[int(t.mes), t.meia_hora, r(t.mw200, 1)] for t in g[g.alto_baixa_irr].itertuples()],
    }
    # regime mensal: MW a 800 W/m² ao meio-dia por mês, e variação
    out['meio_dia'] = [[int(t.mes), r(t.mw800), r(t.var, 4)] for t in m12[m12.ceg == ceg].itertuples()]
    # telemetria mensal
    tm = tele[tele.ceg == ceg].sort_values('ano_mes')
    out['tele'] = [[int(t.ano_mes), r(t.pct_ruim, 4), r(t.mwh_corte, 0)] for t in tm.itertuples()]
    # células em risco (mês x meia-hora do fotoperíodo sem ponto válido / com menos de 5)
    rk = risco[risco.ceg == ceg].sort_values('ano_mes')
    out['risco'] = [[int(t.ano_mes), int(t.cel), int(t.vazias), int(t.frageis)] for t in rk.itertuples()]
    # nuvem pública (mês x irr_bin)
    nv = nuv[nuv.ceg == ceg]
    out['nuvem'] = {int(m): [[int(t.irr_bin), int(t.n), r(t.ger_p10), r(t.ger_p50), r(t.ger_p90), r(t.est_p50)] for t in gm.sort_values('irr_bin').itertuples()] for m, gm in nv.groupby('mes')}
    # viés por célula (mês x meia-hora): soma ponderada
    vv = vies[vies.ceg == ceg]
    if len(vv):
        agg = vv.groupby(['mes', 'meia_hora']).apply(lambda d: pd.Series({'f': (d.f_art4 * d.n).sum() / d.n.sum(), 'p': (d.ger_p50 * d.n).sum() / d.n.sum(), 'e': (d.est_p50 * d.n).sum() / d.n.sum(), 'n': d.n.sum()})).reset_index()
        out['vies'] = [[int(t.mes), t.meia_hora, r(t.f), r(t.p), r(t.e), int(t.n)] for t in agg.itertuples()]
    else:
        out['vies'] = []
    dump(out, os.path.join(SITE, 'data', 'usinas', f'{ceg}.json'))
    n_ok += 1
print('usinas exportadas', n_ok)
tam = sum(os.path.getsize(os.path.join(SITE, 'data', 'usinas', f)) for f in os.listdir(os.path.join(SITE, 'data', 'usinas')))
print('tamanho total usinas/', round(tam / 1e6, 1), 'MB')

# ---------- pré-visualização com dados embutidos (para revisão como artefato, sem servidor)
# inclui o índice completo e o detalhe das usinas com sinal forte + os 3 conjuntos com mais usinas, até ~9 MB
import sys
PREVIEW_CEGS = sys.argv[1:]  # opcional: CEGs extras
sel = ind.sort_values(['n_fortes', 'n_atencao'], ascending=False)
cegs = list(dict.fromkeys(PREVIEW_CEGS + list(sel[sel.n_fortes >= 1].ceg)))
emb = {'index': json.load(open(os.path.join(SITE, 'data', 'index.json'), encoding='utf-8')), 'usinas': {}}
tot = 0
for c in cegs:
    p = os.path.join(SITE, 'data', 'usinas', f'{c}.json')
    if not os.path.exists(p):
        continue
    s = open(p, encoding='utf-8').read()
    if tot + len(s) > 9_000_000:
        break
    emb['usinas'][c] = json.loads(s); tot += len(s)
html = open(os.path.join(SITE, 'index.html'), encoding='utf-8').read()
html = html.replace('<script>\n(function(){', '<script>window.RADAR_EMBED=' + json.dumps(emb, ensure_ascii=False, separators=(',', ':')) + ';</script>\n<script>\n(function(){', 1)
# o artefato embrulha a página: tira doctype/html/head/body e deixa title+style no topo
import re as _re
corpo = _re.search(r'<title>.*?</title>', html, _re.S).group(0) + '\n' + _re.search(r'<link[^>]+fonts[^>]+>', html).group(0) + '\n' + _re.search(r'<style>.*?</style>', html, _re.S).group(0) + '\n' + _re.search(r'<body>(.*)</body>', html, _re.S).group(1)
prev = os.path.join(os.path.dirname(HERE), 'preview_embed.html')
open(prev, 'w', encoding='utf-8').write(corpo)
print('preview:', prev, round(os.path.getsize(prev) / 1e6, 1), 'MB, usinas embutidas:', len(emb['usinas']))
