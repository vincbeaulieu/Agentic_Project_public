"""
OUTIL: ranger_outils
VERSION: 2
RESUME: Gestion des versions des outils selon les bonnes pratiques : outils/ ne garde que la version courante (adoptée) de chaque outil et les versions dont une version courante dépend encore (épinglées) ; les autres versions sont déplacées (jamais supprimées) dans outils/archive/<outil>/ ; plan de rangement revu avant application, rejouable tel quel sur le PC ; registre des outils (version courante, dépendances, épinglages, archives) et journal des changements générés depuis les en-têtes.
USAGE: python3 ranger_outils_v2.py plan [--racines /home/claude]     (écrit outils/archive/plans/plan_rangement_<ts>.json, ne déplace rien)
       python3 ranger_outils_v2.py appliquer <plan.json>             (déplace ; refuse d'écraser ; fonctionne aussi sur le PC)
       python3 ranger_outils_v2.py registre                          (registre_outils_vN.json, CHANGELOG_outils_vN.md)
ENTREES: outils/*_vN.(py|ps1|cmd|md), outils/archive/*/ ; outils/adoption_outils_vN.json (décisions d'adoption qui dérogent à « la plus haute version ») ; scripts courants des dossiers de travail (NN_*/90_scripts) pour les dépendances
SORTIES: plan de rangement JSON ; déplacements ; registre_outils_vN.json ; CHANGELOG_outils_vN.md ; événement dans journal/
CATEGORIE: memoire
BANC: -
REMPLACE: ranger_outils_v1 (dépendances : seules les références de code comptent — import, from … import, __import__, chemin <outil>_vN.py|ps1|cmd — hors en-tête et commentaires ; v1 prenait toute mention, y compris REMPLACE et les fichiers de données)
"""
import sys, os, re, json, glob, datetime, collections
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
from cc_lib_v1 import RACINE_CC, evenement, ecrire_versionne, derniere_version
OUTILS = os.path.join(RACINE_CC, 'outils'); ARCH = os.path.join(OUTILS, 'archive')
RX = re.compile(r'^(?P<base>[A-Za-z][A-Za-z0-9_]*?)_v(?P<v>\d+)\.(?P<ext>py|ps1|cmd|md)$')
GENERES = ('registre_outils', 'CHANGELOG_outils', 'adoption_outils')
def opt(a, k, d=None): return a[a.index(k) + 1] if k in a else d


def inventaire():
    I = collections.defaultdict(dict)                       # base -> {version: chemin}
    for d in [OUTILS] + sorted(glob.glob(os.path.join(ARCH, '*'))):
        if not os.path.isdir(d) or os.path.basename(d) == 'plans': continue
        for f in sorted(os.listdir(d)):
            m = RX.match(f)
            if m and m.group('base') not in GENERES: I[m.group('base')].setdefault(int(m.group('v')), os.path.join(d, f))
    return I


def adoption():
    f = derniere_version(OUTILS, 'adoption_outils', 'json')
    return json.load(open(f, encoding='utf-8'))['decisions'] if f else {}


def entete(f):
    E = {}
    for l in open(f, encoding='utf-8', errors='replace').read(6000).splitlines()[:40]:
        m = re.match(r'^\s*#?\s*(OUTIL|VERSION|RESUME|USAGE|CATEGORIE|BANC|REMPLACE):\s*(.*)$', l)
        if m and m.group(1) not in E: E[m.group(1)] = m.group(2).strip()
    return E


def calculer(racines):
    I = inventaire(); A = adoption(); cour = {}
    for b, vs in I.items():
        d = A.get(b, {})
        cour[b] = d['courant'] if 'courant' in d else max(vs)
    B = '(' + '|'.join(sorted(map(re.escape, I), key=len, reverse=True)) + ')'
    refs = [re.compile(r'\bimport\s+' + B + r'_v(\d+)\b'), re.compile(r'\bfrom\s+' + B + r'_v(\d+)\s+import\b'),
            re.compile(r"__import__\(\s*['\"]" + B + r"_v(\d+)['\"]"), re.compile(r'\b' + B + r'_v(\d+)\.(?:py|ps1|cmd)\b')]
    def code(f):                                            # sans l'en-tête ni les commentaires : seules les références réelles comptent
        t = open(f, encoding='utf-8', errors='replace').read()
        if f.endswith('.py'): t = re.sub(r'^\s*(?:#![^\n]*\n)?\s*[rRuU]?"""(.*?)"""', '', t, count=1, flags=re.S); t = re.sub(r'(?m)^\s*#.*$', '', t)
        elif f.endswith('.ps1'): t = re.sub(r'(?m)^\s*#.*$', '', t)
        elif f.endswith('.cmd'): t = re.sub(r'(?im)^\s*rem\b.*$', '', t)
        return t
    def deps(f):
        t = code(f); base = RX.match(os.path.basename(f)); propre = base.group('base') if base else None
        return {(m.group(1), int(m.group(2))) for r in refs for m in r.finditer(t) if m.group(1) != propre}
    a_voir = [I[b][v] for b, v in cour.items() if v is not None and v in I[b]]
    for r in racines:                                       # scripts courants des dossiers de travail
        par = collections.defaultdict(dict)
        for f in glob.glob(os.path.join(r, '[0-9][0-9]_*', '90_scripts', '*.py')):
            m = re.match(r'^(.*)_v(\d+)\.py$', os.path.basename(f))
            if m: par[(os.path.dirname(f), m.group(1))][int(m.group(2))] = f
        a_voir += [vs[max(vs)] for vs in par.values()]
    gardes = {(b, v): 'courant' for b, v in cour.items() if v is not None}; dep = collections.defaultdict(set)
    vus = set()
    while a_voir:
        f = a_voir.pop()
        if f in vus: continue
        vus.add(f); src = os.path.basename(f)
        for b, v in deps(f):
            if v not in I.get(b, {}): continue
            dep[src].add(f'{b}_v{v}')
            if (b, v) not in gardes: gardes[(b, v)] = 'épinglé par ' + src; a_voir.append(I[b][v])
            elif gardes[(b, v)].startswith('épinglé') and src not in gardes[(b, v)]: gardes[(b, v)] += ', ' + src
    return I, cour, gardes, dep


def plan(a):
    racines = (opt(a, '--racines') or os.path.dirname(RACINE_CC)).split(',')
    I, cour, gardes, dep = calculer(racines); M = []
    for b in sorted(I):
        for v, f in sorted(I[b].items()):
            if (b, v) in gardes or os.path.dirname(f) != OUTILS: continue
            M.append(dict(source=os.path.relpath(f, RACINE_CC), destination=os.path.relpath(os.path.join(ARCH, b, os.path.basename(f)), RACINE_CC)))
    ep = {f'{b}_v{v}': g for (b, v), g in sorted(gardes.items()) if g != 'courant'}
    P = dict(date=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), deplacements=M, epingles=ep,
             courants={b: v for b, v in sorted(cour.items())})
    os.makedirs(os.path.join(ARCH, 'plans'), exist_ok=True)
    f = os.path.join(ARCH, 'plans', f"plan_rangement_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(f, 'x', encoding='utf-8') as g: json.dump(P, g, ensure_ascii=False, indent=1)
    print(os.path.relpath(f, RACINE_CC)); print(f'{len(M)} version(s) à archiver ; {len(ep)} version(s) ancienne(s) gardée(s) car épinglée(s) :')
    for k, g in ep.items(): print('  ', k, '←', g)


def appliquer(a):
    P = json.load(open(a[0], encoding='utf-8')); fait, saute = 0, []
    for m in P['deplacements']:
        s, d = os.path.join(RACINE_CC, m['source']), os.path.join(RACINE_CC, m['destination'])
        if not os.path.exists(s): saute.append((m['source'], 'absent')); continue
        if os.path.exists(d): saute.append((m['destination'], 'existe déjà')); continue
        os.makedirs(os.path.dirname(d), exist_ok=True); os.rename(s, d); fait += 1
    evenement('ranger_outils', 2, 'appliquer', dict(plan=os.path.basename(a[0]), deplaces=fait, sautes=len(saute)))
    print(f'{fait} déplacé(s) ; {len(saute)} sauté(s)'); [print('  sauté :', *x) for x in saute]


def registre(a):
    I, cour, gardes, dep = calculer([os.path.dirname(RACINE_CC)]); A = adoption(); R = {}; L = ['# Journal des changements des outils', '',
        'Généré par `outils/ranger_outils_v2.py registre` à partir des en-têtes (champ REMPLACE). Ne pas éditer à la main.', '']
    for b in sorted(I):
        vs = I[b]; c = cour[b]; e = entete(vs[c]) if c in vs else {}
        R[b] = dict(courant=c, statut=A.get(b, {}).get('statut', 'courant' if c else 'abandonné'), fichier=os.path.relpath(vs[c], RACINE_CC) if c in vs else None,
                    categorie=e.get('CATEGORIE'), resume=(e.get('RESUME') or '')[:200], dependances=sorted(dep.get(os.path.basename(vs[c]), [])) if c in vs else [],
                    epinglees={str(v): gardes[(b, v)] for v in vs if (b, v) in gardes and gardes[(b, v)] != 'courant'},
                    archivees=sorted(v for v, f in vs.items() if os.path.dirname(f) != OUTILS), note=A.get(b, {}).get('note'))
        L.append(f"## `{b}` — courant : {'v' + str(c) if c else 'aucun (' + R[b]['statut'] + ')'}")
        for v in sorted(vs, reverse=True):
            L.append(f"- v{v} : {entete(vs[v]).get('REMPLACE', '—')}")
        L.append('')
    p1, _ = ecrire_versionne(OUTILS, 'registre_outils', 'json', json.dumps(dict(outils=R), ensure_ascii=False, indent=1, sort_keys=True) + '\n')
    p2, _ = ecrire_versionne(OUTILS, 'CHANGELOG_outils', 'md', '\n'.join(L) + '\n')
    evenement('ranger_outils', 2, 'registre', dict(outils=len(R), fichier=os.path.basename(p1)))
    print(os.path.relpath(p1, RACINE_CC), os.path.relpath(p2, RACINE_CC), len(R), 'outils')


if __name__ == '__main__':
    {'plan': plan, 'appliquer': appliquer, 'registre': registre}[sys.argv[1]](sys.argv[2:])
