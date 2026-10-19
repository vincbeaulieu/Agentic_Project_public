"""
OUTIL: chercher_outil
VERSION: 1
RESUME: Première étape obligatoire avant de programmer quoi que ce soit (guide de création d'outils) : cherche dans le catalogue les outils existants qui font déjà, en tout ou en partie, ce qu'on veut faire ; classement par mots-clés (sans accents ni casse) sur le résumé, l'usage, les entrées, les sorties et la catégorie ; affiche le raccourci à lancer.
USAGE: python3 outils/chercher_outil.py <mots-clés …> [--n 8] [--json]
ENTREES: catalogue/catalogue_outils_vN.json (dernière version ; régénérer par outils/catalogue.py)
SORTIES: liste classée (outil, version, score, raccourci, résumé) ; événement dans journal/
CATEGORIE: memoire
BANC: tests/test_chercher_outil_v1.py
REMPLACE: -
"""
import sys, os, re, json, glob, unicodedata
H = os.path.dirname(os.path.abspath(__file__)); O = H
while os.path.basename(O) != 'outils' and os.path.dirname(O) != O: O = os.path.dirname(O)
RACINE_CC = os.path.dirname(O)
VIDES = set('le la les de des du un une et ou a au aux en pour par sur dans avec sans qui que est sont'.split())


def norm(t): return ''.join(c for c in unicodedata.normalize('NFKD', (t or '').lower()) if not unicodedata.combining(c))
def mots(t): return [m for m in re.findall(r'[a-z0-9]+', norm(t)) if m not in VIDES and len(m) > 1]


def catalogue():
    c = sorted(glob.glob(os.path.join(RACINE_CC, 'catalogue', 'catalogue_outils_v*.json')), key=lambda f: int(re.search(r'_v(\d+)\.json$', f).group(1)))
    if not c: raise SystemExit('catalogue absent : lancer outils/catalogue.py')
    return json.load(open(c[-1], encoding='utf-8'))


def chercher(requete, C):
    Q = mots(' '.join(requete)); R = []
    for o in C:
        champs = {'outil': 3.0, 'resume': 2.0, 'categorie': 1.5, 'usage': 1.0, 'entrees': 1.0, 'sorties': 1.0}
        s = 0.0
        for k, w in champs.items():
            M = mots(o.get(k) or '')
            for q in Q:
                if q in M: s += w
                elif any(m.startswith(q) or q.startswith(m) for m in M if len(m) > 3 and len(q) > 3): s += w / 2
        if s: R.append((round(s, 1), o))
    return sorted(R, key=lambda x: (-x[0], x[1]['outil']))


def main():
    a = sys.argv[1:]; n = int(a[a.index('--n') + 1]) if '--n' in a else 8
    req = [x for i, x in enumerate(a) if not x.startswith('--') and (i == 0 or a[i - 1] != '--n')]
    R = chercher(req, catalogue())[:n]
    if '--json' in a: print(json.dumps([dict(score=s, outil=o['outil'], version=o['version'], raccourci=o.get('raccourci')) for s, o in R], ensure_ascii=False))
    else:
        if not R: print('aucun outil existant ne correspond : en créer un (guide de création d’outils)')
        for s, o in R: print(f"{s:5}  {o['outil']} v{o['version']}  → {o.get('raccourci')}\n       {(o.get('resume') or '')[:160]}")
    try:
        sys.path.insert(0, os.path.join(O, '_compat')); sys.path.insert(0, O)
        from cc_lib_v1 import evenement; evenement('chercher_outil', 1, 'recherche', dict(requete=' '.join(req), resultats=len(R)))
    except Exception: pass


if __name__ == '__main__':
    main()
