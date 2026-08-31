# -*- coding: utf-8 -*-
"""Etapa 1 do Radar das Funções de Produtividade Solar.

Lê TODAS as funções de produtividade publicadas pelo ONS (produto público "Funções de
Produtividade" do SINtegre): o lote do art. 4º (zips 202308..202402, vigência retroativa
set/23..mar/24) e as revisões vigentes (202403..202607 + Revisadas). Gera duas tabelas
Parquet no I:

  celulas.parquet  - 1 linha por (arquivo, mês, meia-hora): resumo da mini-curva
                     (vazia?, nº de degraus, MW em 200/400/600/800/1000 W/m², máximo,
                     irradiância do máximo, monotonicidade, saturação)
  curvas100.parquet- 1 linha por (arquivo, mês, meia-hora, irradiância de 100 em 100)
                     para desenhar as curvas no BI

Formato do CSV (memória fase03_reference_cache_curvas_ixp_solar): latin-1, sep ';',
linha 1 = nome do mês repetido por bloco de 31 colunas, linha 2 = 'Irrad' + meias-horas
05:00..20:00, demais linhas = irradiância (passo 10) x MW; célula vazia = fora do fotoperíodo.
"""
import os, re, sys, glob, zipfile, io
import numpy as np, pandas as pd

# Caminhos: defina em pipeline/_caminhos.py (arquivo local, fora do repositório) ou nas variáveis RADAR_*.
try:
    from _caminhos import ART4_DIR, VIG_DIR, DADOS as OUT
except ImportError:
    ART4_DIR = os.environ.get('RADAR_ART4_DIR', os.path.join('.', 'origem', 'art4'))        # zips do lote do art. 4º
    VIG_DIR = os.environ.get('RADAR_VIGENTES_DIR', os.path.join('.', 'origem', 'vigentes')) # zips 202403..202607
    OUT = os.environ.get('RADAR_DADOS', os.path.join('.', 'dados'))
os.makedirs(OUT, exist_ok=True)

MESES = {'jan': 1, 'fev': 2, 'mar': 3, 'abr': 4, 'mai': 5, 'jun': 6, 'jul': 7, 'ago': 8, 'set': 9, 'out': 10, 'nov': 11, 'dez': 12}
NIVEIS = [200, 400, 600, 800, 1000]
RX = re.compile(r'^(\d{6}-\d)_(.+?)_(\d{8})_(\d{8})_Funcao\.csv$', re.I)


def parse_csv(texto, meta):
    """Devolve (linhas_celulas, linhas_curvas) para um CSV."""
    linhas = [l.rstrip('\r\n') for l in texto.splitlines() if l.strip()]
    if len(linhas) < 3:
        return [], []
    cab_mes = linhas[0].split(';')
    cab_hora = linhas[1].split(';')
    ncol = len(cab_hora)
    # matriz irradiância x colunas
    irr = []; M = []
    for l in linhas[2:]:
        p = l.split(';')
        if not p[0].strip():
            continue
        try:
            irr.append(float(p[0].replace(',', '.')))
        except ValueError:
            continue
        row = []
        for v in p[1:ncol]:
            v = v.strip()
            row.append(np.nan if v == '' else float(v.replace(',', '.')))
        row += [np.nan] * (ncol - 1 - len(row))
        M.append(row)
    irr = np.array(irr); M = np.array(M)  # shape (n_irr, ncol-1)
    cel = []; cur = []
    for j in range(1, ncol):
        mes_txt = cab_mes[j].strip().lower()[:3] if j < len(cab_mes) else ''
        mes = MESES.get(mes_txt)
        hora = cab_hora[j].strip()
        if mes is None or not hora:
            continue
        col = M[:, j - 1]
        ok = ~np.isnan(col)
        n = int(ok.sum())
        base = dict(meta, mes=mes, meia_hora=hora)
        if n == 0:
            cel.append(dict(base, vazia=True, n_degraus=0, irr_max_grid=None, mw_max=None, irr_do_max=None,
                            mw200=None, mw400=None, mw600=None, mw800=None, mw1000=None,
                            quedas=None, queda_max_mw=None, irr_sat90=None))
            continue
        vi = irr[ok]; vm = col[ok]
        def em(x):
            if x < vi.min() or x > vi.max():
                return None
            return float(np.interp(x, vi, vm))
        imax = int(np.argmax(vm))
        d = np.diff(vm)
        quedas = int((d < -0.05).sum())
        queda_max = float(-d.min()) if len(d) else 0.0
        mwmax = float(vm[imax])
        sat = vi[np.argmax(vm >= 0.9 * mwmax)] if mwmax > 0 else None
        cel.append(dict(base, vazia=False, n_degraus=n, irr_max_grid=float(vi.max()), mw_max=mwmax, irr_do_max=float(vi[imax]),
                        mw200=em(200), mw400=em(400), mw600=em(600), mw800=em(800), mw1000=em(1000),
                        quedas=quedas, queda_max_mw=queda_max, irr_sat90=float(sat) if sat is not None else None))
        for x in range(0, int(vi.max()) + 1, 100):
            cur.append(dict(base, irr=x, mw=em(x)))
    return cel, cur


def processa_zip(zpath, lote):
    zf = zipfile.ZipFile(zpath)
    mes_arq = re.search(r'(\d{6})', os.path.basename(zpath)).group(1)
    rev = 'Revisadas' in os.path.basename(zpath)
    cels = []; curs = []; n = 0
    for name in zf.namelist():
        b = os.path.basename(name)
        m = RX.match(b)
        if not m:
            continue
        ceg, ident, data_arq, vig = m.groups()
        meta = dict(lote=lote, zip_mes=mes_arq, revisada=rev, ceg=ceg, ident=ident, data_arquivo=data_arq,
                    inicio_vigencia=vig, arquivo=b)
        try:
            texto = zf.read(name).decode('latin-1')
        except Exception as e:
            print('ERRO lendo', b, e); continue
        c, u = parse_csv(texto, meta)
        cels += c; curs += u; n += 1
    print(f'{os.path.basename(zpath)}: {n} funções, {len(cels)} células', flush=True)
    return cels, curs


if __name__ == '__main__':
    todos_c = []; todos_u = []
    for z in sorted(glob.glob(os.path.join(ART4_DIR, 'Funcoes Prod-*.zip'))):
        c, u = processa_zip(z, 'art4'); todos_c += c; todos_u += u
    for z in sorted(glob.glob(os.path.join(VIG_DIR, 'Funcoes*Prod*.zip'))):
        c, u = processa_zip(z, 'vigente'); todos_c += c; todos_u += u
    cel = pd.DataFrame(todos_c); cur = pd.DataFrame(todos_u)
    cel.to_parquet(os.path.join(OUT, 'celulas.parquet'), index=False)
    cur.to_parquet(os.path.join(OUT, 'curvas100.parquet'), index=False)
    print('celulas', cel.shape, 'curvas100', cur.shape)
    print(cel.groupby('lote').arquivo.nunique())
