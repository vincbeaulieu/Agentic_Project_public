"""
OUTIL: detecter_noms
VERSION: 1
RESUME: Détecteur déterministe de noms de personnes dans mes propres documents (règle E13 du mémoire) : compare l'empreinte de chaque mot (minuscules, sans accents) aux empreintes de regles/noms_proteges_vN.json, sans jamais stocker ni afficher les noms en clair ; lit md, txt, json, py, csv et le texte des docx et xlsx.
USAGE: python3 detecter_noms_v1.py <chemin> [<chemin> …] [--exclure <motif>] [--json <sortie>]
ENTREES: fichiers ou dossiers ; regles/noms_proteges_vN.json (dernière version)
SORTIES: liste des fichiers contenant des noms protégés (nombre d'occurrences, jamais les noms) ; code 0 si aucun, 1 sinon ; événement dans journal/
CATEGORIE: confidentialite
BANC: -
REMPLACE: -
"""
import sys, os, re, json, zipfile, hashlib, unicodedata, fnmatch, glob
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
from cc_lib_v1 import RACINE_CC, evenement, derniere_version
EXT = ('.md', '.txt', '.json', '.jsonl', '.py', '.csv', '.js', '.mmd', '.docx', '.xlsx')
MOT = re.compile(r'[A-Za-zÀ-ÖØ-öø-ÿ]+')


def norm(t): return ''.join(c for c in unicodedata.normalize('NFKD', t.lower()) if not unicodedata.combining(c))
def emp(t): return hashlib.sha256(('cc-noms|' + norm(t)).encode()).hexdigest()[:16]


def texte(f):
    if f.endswith(('.docx', '.xlsx')):
        try:
            z = zipfile.ZipFile(f)
            return ' '.join(re.sub(r'<[^>]+>', ' ', z.read(n).decode('utf-8', 'ignore')) for n in z.namelist() if n.endswith('.xml'))
        except Exception: return ''
    try: return open(f, encoding='utf-8', errors='ignore').read()
    except Exception: return ''


def main():
    a = sys.argv[1:]
    excl = [a[i + 1] for i, x in enumerate(a) if x == '--exclure']
    jout = a[a.index('--json') + 1] if '--json' in a else None
    chemins = [x for i, x in enumerate(a) if not x.startswith('--') and (i == 0 or a[i - 1] not in ('--exclure', '--json'))]
    proteges = set(json.load(open(derniere_version(os.path.join(RACINE_CC, 'regles'), 'noms_proteges', 'json'), encoding='utf-8'))['empreintes'])
    fichiers = []
    for c in chemins:
        if os.path.isdir(c):
            for r, ds, fs in os.walk(c):
                ds[:] = [d for d in ds if d not in ('__pycache__', '.config')]
                fichiers += [os.path.join(r, f) for f in fs if f.endswith(EXT)]
        else: fichiers.append(c)
    res = {}
    for f in sorted(fichiers):
        if any(fnmatch.fnmatch(f, p) for p in excl): continue
        n = sum(1 for m in MOT.finditer(texte(f)) if emp(m.group(0)) in proteges)
        if n: res[f] = n
    for f, n in res.items(): print(f'{n:5d}  {f}')
    print(f'{len(res)} fichier(s) avec des noms protégés sur {len(fichiers)} examinés')
    if jout:
        with open(jout, 'x', encoding='utf-8') as fo: json.dump(res, fo, ensure_ascii=False, indent=1)
    evenement('detecter_noms', 1, 'detection', dict(fichiers_examines=len(fichiers), fichiers_avec_noms=len(res)))
    return 1 if res else 0


if __name__ == '__main__':
    sys.exit(main())
