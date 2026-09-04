# -*- coding: utf-8 -*-
"""Células em risco: para cada usina e mês da telemetria pública, quantas células da função (meia-hora do fotoperíodo)
não têm NENHUM ponto válido (ficariam vazias na função do ano seguinte) e quantas têm menos de 5 pontos (frágeis).
Lê publico_mensal.parquet (saída do 02) e grava celulas_risco_mes.parquet. Roda depois do 02, independente do 03."""
import os, sys, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from _caminhos import DADOS as D
except Exception:
    D = os.environ.get("RADAR_DADOS", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dados"))
LIMIAR_FP = 30      # W/m²: mesma régua do 03 (fotoperíodo típico)
MIN_PONTOS = 5      # abaixo disso a célula é "frágil"

pm = pd.read_parquet(os.path.join(D, "publico_mensal.parquet"))
pm["validos"] = pm.n - pm.n_irr_ruim
# fotoperíodo típico da própria usina: meias-horas em que a mediana da irradiância válida (todo o histórico) passa do limiar
fp = pm.groupby(["ceg7", "meia_hora"]).irr_mediana_valida.median().reset_index()
fp = fp[fp.irr_mediana_valida > LIMIAR_FP][["ceg7", "meia_hora"]]
pm = pm.merge(fp, on=["ceg7", "meia_hora"])
g = pm.groupby(["ceg7", "ano_mes"]).agg(cel=("meia_hora", "nunique"),
                                        vazias=("validos", lambda s: int((s <= 0).sum())),
                                        frageis=("validos", lambda s: int(((s > 0) & (s < MIN_PONTOS)).sum()))).reset_index()
g = g.rename(columns={"ceg7": "ceg"})
g.to_parquet(os.path.join(D, "celulas_risco_mes.parquet"), index=False)
print("celulas_risco_mes:", g.shape, "| usinas:", g.ceg.nunique(), "| meses:", g.ano_mes.min(), "a", g.ano_mes.max())
print("usinas com algum mês 100% vazio:", int((g.groupby("ceg").apply(lambda x: (x.vazias >= x.cel).any())).sum()))
