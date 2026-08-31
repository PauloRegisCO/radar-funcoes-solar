"""Regenera só o preview_embed.html (artefato de revisão) a partir de site/, sem rodar o 04 inteiro.
Uso: python pipeline/preview.py [CEG extra ...]
Embute o índice completo e o detalhe das usinas com pelo menos um sinal forte (+ CEGs extras), até ~9 MB."""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(os.path.dirname(HERE), 'site')
idx = json.load(open(os.path.join(SITE, 'data', 'index.json'), encoding='utf-8'))
fortes = sorted([u for u in idx['usinas'] if (u.get('fortes') or 0) >= 1 or u.get('funcao_vazia')], key=lambda u: (-(u.get('fortes') or 0), -(u.get('atencao') or 0)))
cegs = list(dict.fromkeys(sys.argv[1:] + [u['ceg'] for u in fortes]))
emb = {'index': idx, 'usinas': {}}
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
corpo = re.search(r'<title>.*?</title>', html, re.S).group(0) + '\n' + re.search(r'<link[^>]+fonts[^>]+>', html).group(0) + '\n' + re.search(r'<style>.*?</style>', html, re.S).group(0) + '\n' + re.search(r'<body>(.*)</body>', html, re.S).group(1)
prev = os.path.join(os.path.dirname(HERE), 'preview_embed.html')
open(prev, 'w', encoding='utf-8').write(corpo)
print('preview:', prev, round(os.path.getsize(prev) / 1e6, 1), 'MB, usinas embutidas:', len(emb['usinas']))
