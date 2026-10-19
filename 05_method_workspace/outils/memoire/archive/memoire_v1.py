"""
OUTIL: memoire
VERSION: 1
RESUME: Gestion versionnée du mémoire de méthodologie : proposer une version, consigner l'approbation explicite de l'utilisateur (citation mot pour mot, empreinte figée), donner la dernière version approuvée en vérifiant que son contenu n'a pas changé depuis l'approbation ; aucune version non approuvée n'est jamais « courante ».
USAGE: python3 memoire_v1.py etat | courant | proposer <MEMOIRE_METHODOLOGIE_vN.md> | approuver <N> --citation "<réponse de l'utilisateur>"
ENTREES: memoire/MEMOIRE_METHODOLOGIE_vN.md
SORTIES: memoire/statut/vN_proposition.json, memoire/statut/vN_approbation.json (immuables) ; chemin de la version courante ; événement dans journal/
CATEGORIE: memoire
BANC: -
REMPLACE: -
"""
import sys, os, re, json, glob, datetime
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
from cc_lib_v1 import RACINE_CC, sha256, evenement
D = os.path.join(RACINE_CC, 'memoire'); ST = os.path.join(D, 'statut')
def maintenant(): return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def versions():
    out = {}
    for f in glob.glob(os.path.join(D, 'MEMOIRE_METHODOLOGIE_v*.md')):
        m = re.search(r'_v(\d+)\.md$', f)
        if m: out[int(m.group(1))] = f
    return dict(sorted(out.items()))


def statut(n):
    a, p = os.path.join(ST, f'v{n}_approbation.json'), os.path.join(ST, f'v{n}_proposition.json')
    if os.path.exists(a): return 'approuvée', json.load(open(a, encoding='utf-8'))
    if os.path.exists(p): return 'proposée', json.load(open(p, encoding='utf-8'))
    return 'non enregistrée', None


def ecrire(chemin, obj):
    os.makedirs(ST, exist_ok=True)
    with open(chemin, 'x', encoding='utf-8') as f: json.dump(obj, f, ensure_ascii=False, indent=1)


def main():
    c = sys.argv[1] if len(sys.argv) > 1 else 'etat'
    V = versions()
    if c == 'etat':
        for n, f in V.items():
            s, info = statut(n); print(f'v{n} : {s}' + (f" le {info.get('date')}" if info else '') + f' — {os.path.basename(f)}')
        if not V: print('aucune version')
    elif c == 'courant':
        app = [n for n in V if statut(n)[0] == 'approuvée']
        if not app: print('AUCUNE VERSION APPROUVÉE : appliquer les consignes de l’utilisateur et demander l’approbation de la dernière proposition'); sys.exit(1)
        n = app[-1]; info = statut(n)[1]
        if sha256(V[n]) != info['sha256']: print(f'ALERTE : v{n} a changé depuis son approbation (empreinte différente)'); sys.exit(2)
        print(V[n])
    elif c == 'proposer':
        f = os.path.abspath(sys.argv[2]); m = re.search(r'_v(\d+)\.md$', f); n = int(m.group(1))
        if os.path.dirname(f) != D: raise SystemExit('le mémoire doit se trouver dans ' + D)
        ecrire(os.path.join(ST, f'v{n}_proposition.json'), dict(version=n, fichier=os.path.basename(f), sha256=sha256(f), date=maintenant()))
        evenement('memoire', 1, 'proposition', dict(version=n)); print(f'v{n} proposée')
    elif c == 'approuver':
        n = int(sys.argv[2]); cit = sys.argv[sys.argv.index('--citation') + 1] if '--citation' in sys.argv else ''
        if not cit.strip(): raise SystemExit('citation de l’approbation de l’utilisateur obligatoire')
        s, info = statut(n)
        if s != 'proposée': raise SystemExit(f'v{n} : {s} (proposer d’abord)')
        if sha256(V[n]) != info['sha256']: raise SystemExit(f'v{n} a changé depuis sa proposition : proposer une nouvelle version')
        ecrire(os.path.join(ST, f'v{n}_approbation.json'), dict(version=n, fichier=os.path.basename(V[n]), sha256=info['sha256'], date=maintenant(), citation=cit))
        evenement('memoire', 1, 'approbation', dict(version=n)); print(f'v{n} approuvée')


if __name__ == '__main__':
    main()
