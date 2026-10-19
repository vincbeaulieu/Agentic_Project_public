"""
OUTIL: organiser_outils
VERSION: 2
RESUME: Organisation et versions des outils (bonnes pratiques) : un dossier par outil (outils/<outil>/ ne contient que la version courante, les précédentes sont dans outils/<outil>/archive/) ; dossier principal sans doublon, avec des raccourcis de contenu constant (outils/<outil>.py exécute ou importe la version courante ; outils/_compat/<outil>_vN.py garde les anciens imports valides) ; gestion dans outils/_gestion/ (registre, journal des changements, décisions d'adoption, plans) ; plan de déplacements revu puis appliqué, rejouable tel quel sur le PC ; vérification automatique des règles d'organisation.
USAGE: python3 organiser_outils_v2.py plan                 (écrit _gestion/plans/plan_organisation_<ts>.json, ne déplace rien)
       python3 organiser_outils_v1.py appliquer <plan.json>  (déplace ; refuse d'écraser ; rejouable, aussi sur le PC)
       python3 organiser_outils_v1.py raccourcis            (crée les raccourcis manquants ; n'en réécrit aucun)
       python3 organiser_outils_v1.py registre              (_gestion/registre_outils_vN.json, _gestion/CHANGELOG_outils_vN.md)
       python3 organiser_outils_v1.py verifier              (code 0 si l'organisation est conforme)
ENTREES: outils/ (ancienne organisation à plat ou nouvelle) ; _gestion/adoption_outils_vN.json ; tests/rapports/ (état des tests)
SORTIES: déplacements ; raccourcis ; registre ; journal des changements ; constats de vérification ; événement dans journal/
CATEGORIE: memoire
BANC: tests/test_organiser_outils_v1.py
REMPLACE: organiser_outils_v1 (dossiers vides tolérés et retirés quand c'est permis ; raccourcis d'un outil sans version courante déplacés dans _gestion/raccourcis_retires/ au lieu de rester) ; v1 remplaçait ranger_outils_v2 (organisation à plat)
"""
import sys, os, re, json, glob, datetime, collections
H = os.path.dirname(os.path.abspath(__file__)); O = H
while os.path.basename(O) != 'outils' and os.path.dirname(O) != O: O = os.path.dirname(O)
OUTILS = O; RACINE_CC = os.path.dirname(OUTILS); GEST = os.path.join(OUTILS, '_gestion'); COMPAT = os.path.join(OUTILS, '_compat')
for p in (COMPAT, OUTILS):
    if p not in sys.path: sys.path.insert(0, p)
RX = re.compile(r'^(?P<base>[A-Za-z_][A-Za-z0-9_]*?)_v(?P<v>\d+)\.(?P<ext>py|ps1|cmd|md|json)$')
GESTION = ('registre_outils', 'CHANGELOG_outils', 'adoption_outils')
SPECIAUX = {'_gestion', '_compat', '_raccourci', '__pycache__', 'archive'}
def opt(a, k, d=None): return a[a.index(k) + 1] if k in a else d


def journal(type_, donnees):
    try:
        from cc_lib_v1 import evenement; evenement('organiser_outils', 2, type_, donnees)
    except Exception: pass


def versionne(dossier, base, ext, contenu):
    os.makedirs(dossier, exist_ok=True)
    vs = sorted(int(m.group(1)) for f in os.listdir(dossier) for m in [re.match(re.escape(base) + r'_v(\d+)\.' + ext + '$', f)] if m)
    if vs and open(os.path.join(dossier, f'{base}_v{vs[-1]}.{ext}'), encoding='utf-8').read() == contenu: return os.path.join(dossier, f'{base}_v{vs[-1]}.{ext}')
    f = os.path.join(dossier, f'{base}_v{(vs[-1] if vs else 0) + 1}.{ext}')
    with open(f, 'x', encoding='utf-8') as g: g.write(contenu)
    return f


def adoption():
    c = sorted(glob.glob(os.path.join(GEST, 'adoption_outils_v*.json')) + glob.glob(os.path.join(OUTILS, 'adoption_outils_v*.json')),
               key=lambda f: int(re.search(r'_v(\d+)\.json$', f).group(1)))
    return json.load(open(c[-1], encoding='utf-8'))['decisions'] if c else {}


def inventaire():
    """[(base, version, ext, chemin)] de toutes les versions, quelle que soit l'organisation (à plat, archive/<outil>, <outil>/, <outil>/archive)."""
    L = []
    def voir(d):
        if not os.path.isdir(d): return
        for f in sorted(os.listdir(d)):
            m = RX.match(f)
            if m and os.path.isfile(os.path.join(d, f)): L.append((m.group('base'), int(m.group('v')), m.group('ext'), os.path.join(d, f)))
    voir(OUTILS)
    for d in sorted(os.listdir(OUTILS)):
        p = os.path.join(OUTILS, d)
        if not os.path.isdir(p) or d in ('__pycache__', '_compat'): continue
        if d == 'archive':
            for b in sorted(os.listdir(p)):
                if b != 'plans': voir(os.path.join(p, b))
        elif d == '_gestion': voir(p)
        else: voir(p); voir(os.path.join(p, 'archive'))
    return L


def cible(base, v, ext, courants):
    if base in GESTION: return os.path.join(GEST, f'{base}_v{v}.{ext}')
    if base == '_raccourci':
        return os.path.join(OUTILS, f'{base}_v{v}.{ext}') if v == courants.get((base, ext)) else os.path.join(OUTILS, '_raccourci', 'archive', f'{base}_v{v}.{ext}')
    if v == courants.get((base, ext)): return os.path.join(OUTILS, base, f'{base}_v{v}.{ext}')
    return os.path.join(OUTILS, base, 'archive', f'{base}_v{v}.{ext}')


def courants_de(L):
    A = adoption(); C = {}
    for b, v, e, f in L:
        C[(b, e)] = max(C.get((b, e), 0), v)
    for b, d in A.items():
        for e in ('py', 'ps1', 'cmd', 'md'):
            if (b, e) in C and 'courant' in d: C[(b, e)] = d['courant']
    return C


def plan(a):
    L = inventaire(); C = courants_de(L); M = []
    for b, v, e, f in L:
        c = cible(b, v, e, C)
        if os.path.abspath(f) != os.path.abspath(c): M.append(dict(source=os.path.relpath(f, RACINE_CC), destination=os.path.relpath(c, RACINE_CC)))
    for f in sorted(glob.glob(os.path.join(OUTILS, 'archive', 'plans', '*.json'))):
        M.append(dict(source=os.path.relpath(f, RACINE_CC), destination=os.path.relpath(os.path.join(GEST, 'plans', os.path.basename(f)), RACINE_CC)))
    P = dict(date=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), deplacements=M,
             courants={f'{b}.{e}': v for (b, e), v in sorted(C.items(), key=lambda x: (x[0][0], x[0][1])) if v})
    os.makedirs(os.path.join(GEST, 'plans'), exist_ok=True)
    f = os.path.join(GEST, 'plans', f"plan_organisation_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(f, 'x', encoding='utf-8') as g: json.dump(P, g, ensure_ascii=False, indent=1)
    print(os.path.relpath(f, RACINE_CC), ':', len(M), 'déplacement(s)')


def appliquer(a):
    P = json.load(open(a[0], encoding='utf-8')); fait, saute = 0, []
    for m in P['deplacements']:
        s, d = os.path.join(RACINE_CC, m['source']), os.path.join(RACINE_CC, m['destination'])
        if not os.path.exists(s): saute.append((m['source'], 'absent')); continue
        if os.path.exists(d): saute.append((m['destination'], 'existe déjà')); continue
        os.makedirs(os.path.dirname(d), exist_ok=True); os.rename(s, d); fait += 1
    vides(retirer=True)
    journal('appliquer', dict(plan=os.path.basename(a[0]), deplaces=fait, sautes=len(saute)))
    print(f'{fait} déplacé(s) ; {len(saute)} sauté(s)'); [print('  sauté :', *x) for x in saute[:30]]


def vides(retirer=False):
    """Dossiers vides (récursivement) sous outils/ ; retirés si possible (rmdir n'enlève qu'un dossier vide ; refusé sur le PC sans permission)."""
    V = []
    for d, sous, fich in os.walk(OUTILS, topdown=False):
        if d == OUTILS: continue
        if not os.listdir(d):
            V.append(d)
            if retirer:
                try: os.rmdir(d)
                except OSError: pass
    return [d for d in V if os.path.isdir(d)]


def retirer_raccourcis_perimes():
    """Raccourcis du dossier principal dont l'outil n'a plus de version courante : déplacés (jamais supprimés)."""
    E = attendus(); dest = os.path.join(GEST, 'raccourcis_retires', datetime.datetime.now().strftime('%Y%m%d_%H%M%S')); n = 0
    for f in sorted(os.listdir(OUTILS)):
        p = os.path.join(OUTILS, f)
        if os.path.isfile(p) and (f.endswith('.lien.txt') or (f.endswith('.py') and not RX.match(f))) and p not in E and not f.startswith('_raccourci'):
            os.makedirs(dest, exist_ok=True); os.rename(p, os.path.join(dest, f)); n += 1
    return n


def moteur():
    c = sorted((int(m.group(1)), f) for f in os.listdir(OUTILS) for m in [re.match(r'^_raccourci_v(\d+)\.py$', f)] if m)
    if not c: raise SystemExit('moteur des raccourcis absent (outils/_raccourci_vN.py)')
    return f'_raccourci_v{c[-1][0]}'


def texte_raccourci(base, mot):
    return (f"# Raccourci vers la version courante de l'outil « {base} » : contenu constant, généré par organiser_outils, ne pas éditer.\n"
            f"# Version courante = l'unique fichier {base}_vN.py de outils/{base}/ ; versions précédentes : outils/{base}/archive/.\n"
            "import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n"
            f"from {mot} import charger; charger(__name__, '{base}')\n")


def texte_compat(base, v, mot):
    return (f"# Raccourci de compatibilité vers {base}_v{v} (où qu'il soit rangé) : contenu constant, généré par organiser_outils.\n"
            "import os, sys; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n"
            f"from {mot} import charger; charger(__name__, '{base}', version={v})\n")


def texte_lien(base, ext):
    return (f"Raccourci (texte) vers la version courante de « {base} » ({ext}) : l'unique fichier {base}_vN.{ext} du dossier outils\\{base}\\ ;\n"
            f"versions précédentes : outils\\{base}\\archive\\. Contenu constant, généré par organiser_outils.\n")


def attendus():
    """{chemin: contenu} de tous les raccourcis attendus dans l'organisation actuelle."""
    mot = moteur(); E = {}
    for b, v, e, f in inventaire():
        if b in GESTION or b == '_raccourci': continue
        if e == 'py': E[os.path.join(COMPAT, f'{b}_v{v}.py')] = texte_compat(b, v, mot)
        if os.path.dirname(f) == os.path.join(OUTILS, b):
            if e == 'py': E[os.path.join(OUTILS, f'{b}.py')] = texte_raccourci(b, mot)
            else: E[os.path.join(OUTILS, f'{b}.{e}.lien.txt')] = texte_lien(b, e)
    return E


def raccourcis(a):
    crees, differents = 0, []
    for f, t in sorted(attendus().items()):
        if os.path.exists(f):
            if open(f, encoding='utf-8').read() != t: differents.append(os.path.relpath(f, RACINE_CC))
            continue
        os.makedirs(os.path.dirname(f), exist_ok=True)
        with open(f, 'x', encoding='utf-8') as g: g.write(t)
        crees += 1
    retires = retirer_raccourcis_perimes()
    journal('raccourcis', dict(crees=crees, differents=len(differents), retires=retires))
    if retires: print(f'{retires} raccourci(s) périmé(s) déplacé(s) dans _gestion/raccourcis_retires/')
    print(f'{crees} raccourci(s) créé(s)' + (f' ; {len(differents)} différent(s) de l’attendu (non réécrits) : {differents}' if differents else ''))


def entete(f):
    E = {}
    for l in open(f, encoding='utf-8', errors='replace').read(6000).splitlines()[:40]:
        m = re.match(r'^\s*#?\s*(OUTIL|VERSION|RESUME|USAGE|CATEGORIE|BANC|REMPLACE):\s*(.*)$', l)
        if m and m.group(1) not in E: E[m.group(1)] = m.group(2).strip()
    return E


def etat_tests():
    c = sorted(glob.glob(os.path.join(RACINE_CC, 'tests', 'rapports', 'rapport_tests_*.json')))
    if not c: return {}, None
    r = json.load(open(c[-1], encoding='utf-8')); return r.get('par_outil', {}), os.path.basename(c[-1])


def registre(a):
    L = inventaire(); C = courants_de(L); A = adoption(); T, rap = etat_tests(); R = {}
    par = collections.defaultdict(list)
    for b, v, e, f in L:
        if b not in GESTION: par[b].append((v, e, f))
    lignes = ['# Journal des changements des outils', '', 'Généré par `organiser_outils registre` à partir des en-têtes (REMPLACE). Ne pas éditer.', '']
    for b in sorted(par):
        cur = [(v, e, f) for v, e, f in par[b] if v == C.get((b, e)) and not f.endswith(os.sep + 'archive' + os.sep + os.path.basename(f))]
        cur = [x for x in cur if os.path.basename(os.path.dirname(x[2])) != 'archive']
        e0 = entete(cur[0][2]) if cur else {}
        R[b] = dict(courant={e: v for v, e, f in cur}, fichiers=[os.path.relpath(f, RACINE_CC) for v, e, f in cur],
                    statut=A.get(b, {}).get('statut', 'courant' if cur else 'abandonné'), categorie=e0.get('CATEGORIE'),
                    resume=(e0.get('RESUME') or '')[:200], archivees=sorted({v for v, e, f in par[b] if os.path.basename(os.path.dirname(f)) == 'archive'}),
                    tests=T.get(b), note=A.get(b, {}).get('note'))
        lignes.append(f"## `{b}` — courant : {', '.join(f'v{v}.{e}' for v, e, f in cur) or 'aucun (' + R[b]['statut'] + ')'}")
        for v, e, f in sorted(par[b], reverse=True): lignes.append(f"- v{v} ({e}) : {entete(f).get('REMPLACE', '—')}")
        lignes.append('')
    p1 = versionne(GEST, 'registre_outils', 'json', json.dumps(dict(outils=R, rapport_tests=rap), ensure_ascii=False, indent=1, sort_keys=True) + '\n')
    p2 = versionne(GEST, 'CHANGELOG_outils', 'md', '\n'.join(lignes) + '\n')
    journal('registre', dict(outils=len(R), fichier=os.path.basename(p1)))
    print(os.path.relpath(p1, RACINE_CC), os.path.relpath(p2, RACINE_CC), len(R), 'outils')


def constats():
    P = []; L = inventaire(); E = attendus()
    for b, v, e, f in L:
        d = os.path.dirname(f)
        if d == OUTILS and b != '_raccourci': P.append(f'version dans le dossier principal : {os.path.basename(f)}')
    par = collections.Counter((b, e) for b, v, e, f in L if os.path.dirname(f) == os.path.join(OUTILS, b))
    P += [f'{b} : {n} versions courantes ({e})' for (b, e), n in par.items() if n > 1]
    for f, t in E.items():
        if not os.path.exists(f): P.append(f'raccourci manquant : {os.path.relpath(f, OUTILS)}')
        elif open(f, encoding='utf-8').read() != t: P.append(f'raccourci modifié : {os.path.relpath(f, OUTILS)}')
    permis = {os.path.basename(f) for f in E if os.path.dirname(f) == OUTILS} | {'_gestion', '_compat', '__pycache__', moteur() + '.py', '_raccourci'}
    permis |= {os.path.relpath(f, OUTILS).split(os.sep)[0] for b, v, e, f in L if os.sep in os.path.relpath(f, OUTILS)}
    vd = {os.path.relpath(d, OUTILS).split(os.sep)[0] for d in vides() if os.path.dirname(d) == OUTILS}
    P += [f'entrée inattendue dans outils/ : {x}' for x in sorted(os.listdir(OUTILS)) if x not in permis and x not in vd]
    return P


def verifier(a):
    P = constats(); journal('verifier', dict(constats=len(P)))
    print('ORGANISATION CONFORME' if not P else f'ORGANISATION NON CONFORME : {len(P)} constat(s)'); [print('  ', x) for x in P[:40]]
    sys.exit(1 if P else 0)


if __name__ == '__main__':
    {'plan': plan, 'appliquer': appliquer, 'raccourcis': raccourcis, 'registre': registre, 'verifier': verifier}[sys.argv[1]](sys.argv[2:])
