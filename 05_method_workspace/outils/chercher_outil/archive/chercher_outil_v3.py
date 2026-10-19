"""
OUTIL: chercher_outil
VERSION: 3
RESUME: Première étape obligatoire avant de programmer quoi que ce soit (guide de création d'outils) : cherche dans le catalogue les outils existants qui font déjà, en tout ou en partie, ce qu'on veut faire ; classement par mots-clés (sans accents ni casse) sur le résumé, l'usage, les entrées, les sorties et la catégorie ; affiche le raccourci à lancer.
USAGE: python3 outils/chercher_outil.py <mots-clés …> [--n 8] [--json]
ENTREES: catalogue/catalogue_outils_vN.json (dernière version ; régénérer par outils/catalogue.py)
SORTIES: liste classée (outil, version, score, raccourci, résumé) ; événement dans journal/
CATEGORIE: memoire
BANC: tests/test_chercher_outil_v3.py
REMPLACE: chercher_outil_v2 (noms de dossiers de l'espace écrits en dur, remplacés par le registre central cc_lib_v4.chemin) ; v2 : chercher_outil_v1 (rapprochement par racine commune — « anonymiser » trouve « anonymisation » — et bonus quand un mot de la requête est le nom même de l'outil) ; v1 : -
"""
import sys, os, re, json, glob, unicodedata
H = os.path.dirname(os.path.abspath(__file__)); O = H
while os.path.basename(O) != 'outils' and os.path.dirname(O) != O: O = os.path.dirname(O)
RACINE_CC = os.path.dirname(O)
for _p in (os.path.join(O, '_compat'), O):
    if _p not in sys.path: sys.path.insert(0, _p)
from cc_lib_v4 import chemin                     # registre central des dossiers de l'espace
VIDES = set('le la les de des du un une et ou a au aux en pour par sur dans avec sans qui que est sont'.split())


def norm(t): return ''.join(c for c in unicodedata.normalize('NFKD', (t or '').lower()) if not unicodedata.combining(c))
def mots(t): return [m for m in re.findall(r'[a-z0-9]+', norm(t)) if m not in VIDES and len(m) > 1]


def racine(m, q):
    """Même racine : préfixe commun d'au moins 6 lettres, ou l'un est le début de l'autre (mots de plus de 3 lettres)."""
    if len(m) <= 3 or len(q) <= 3: return False
    if m.startswith(q) or q.startswith(m): return True
    n = 0
    for x, y in zip(m, q):
        if x != y: break
        n += 1
    return n >= 6


def catalogue():
    c = sorted(glob.glob(chemin('catalogue', 'catalogue_outils_v*.json', racine=RACINE_CC)), key=lambda f: int(re.search(r'_v(\d+)\.json$', f).group(1)))
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
                elif any(racine(m, q) for m in M): s += w / 2
        if any(q == norm(o['outil']) or q in norm(o['outil']).split('_') and len(q) > 5 for q in Q): s += 2.0
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
        from cc_lib_v4 import evenement; evenement('chercher_outil', 3, 'recherche', dict(requete=' '.join(req), resultats=len(R)))
    except Exception: pass


if __name__ == '__main__':
    main()
