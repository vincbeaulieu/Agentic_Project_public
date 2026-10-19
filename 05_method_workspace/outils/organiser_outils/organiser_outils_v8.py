"""
OUTIL: organiser_outils
VERSION: 8
RESUME: Organisation et versions des outils (bonnes pratiques) : un dossier par outil (outils/<outil>/ ne contient que la version courante, les précédentes sont dans outils/<outil>/archive/) ; dossier principal sans doublon, avec des raccourcis de contenu constant (outils/<outil>.py exécute ou importe la version courante ; outils/_compat/<outil>_vN.py garde les anciens imports valides) ; gestion dans outils/_gestion/ (registre, journal des changements, décisions d'adoption, plans) ; plan de déplacements revu puis appliqué, rejouable tel quel sur le PC ; vérification automatique des règles d'organisation.
USAGE: python3 organiser_outils.py preparer <outil>              (copie la version courante en candidat/<outil>_v(N+1) : brouillon à modifier, jamais pris pour la version courante ; VERSION et REMPLACE préparés)
       python3 organiser_outils.py adopter <outil> [--sans-tests]  (candidate de candidat/ mise en place, tests — remise dans candidat/ s'ils échouent —, archivage des anciennes versions, raccourcis, registre)
       python3 organiser_outils.py rejouer                (applique tous les déplacements consignés absents de cette copie : à lancer sur le PC après une sauvegarde ; source et destination identiques présentes : source rangée dans _gestion/doublons_rejouer/)
       python3 organiser_outils.py consigner <source> <destination>   (consigne un déplacement déjà fait, chemins relatifs à 00_competences_claude)
       python3 organiser_outils.py plan                 (écrit _gestion/plans/plan_organisation_<ts>.json, ne déplace rien)
       python3 organiser_outils.py appliquer <plan.json>  (déplace ; refuse d'écraser ; rejouable, aussi sur le PC)
       python3 organiser_outils.py raccourcis            (crée les raccourcis manquants ; ceux d'un ancien moteur sont retirés vers _gestion/raccourcis_retires/ puis régénérés, et l'ancien moteur rangé dans _raccourci/archive/)
       python3 organiser_outils.py registre              (_gestion/registre_outils_vN.json, _gestion/CHANGELOG_outils_vN.md)
       python3 organiser_outils.py verifier              (code 0 si l'organisation est conforme)
ENTREES: outils/ (ancienne organisation à plat ou nouvelle) ; _gestion/adoption_outils_vN.json ; tests/rapports/ (état des tests)
SORTIES: déplacements ; raccourcis ; registre ; journal des changements ; constats de vérification ; événement dans journal/
CATEGORIE: memoire
BANC: tests/test_organiser_outils_v8.py
REMPLACE: organiser_outils_v7 (le catalogue n'était pas régénéré après une adoption : le 16 oct. 2026, la v14 annonçait evaluer_travail v8 alors que la v12 était en service, et la recherche d'outils se trompait ; adopter régénère désormais le catalogue et le dit, ou dit pourquoi il ne l'a pas fait) ; v7 : organiser_outils_v6 (brouillons dans outils/<outil>/candidat/ — les raccourcis n'exécutent plus une version en cours d'écriture — ; doublons identiques rangés par rejouer ; changement de moteur des raccourcis géré ; dossier des tests par le registre central des chemins ; message d'usage sans argument) ; v6 : organiser_outils_v5 (plus de pointeurs « .lien.txt » pour les outils non Python : fichiers inutilisables — ni exécutables ni importables —, retirés vers _gestion/raccourcis_retires/ ; le dossier de l'outil et le registre suffisent) ; v5 : organiser_outils_v4 (chaque déplacement est consigné dans _gestion/deplacements/ ; « rejouer » applique sur une autre copie — le PC — tous les déplacements consignés, sans écraser ; « consigner » enregistre un déplacement fait à la main) ; v4 : organiser_outils_v3 (+ cycle de version automatisé : « preparer » crée la version suivante à partir de la courante, « adopter » la teste comme candidate puis l'adopte — anciennes versions archivées, raccourcis, registre) ; v3 remplaçait organiser_outils_v2 (dossier « vide » = sans aucun fichier, même s'il contient des sous-dossiers vides ; sur le PC, où rmdir est refusé, ces dossiers sont déplacés dans _gestion/dossiers_vides/ au lieu de rester) ; v2 remplaçait organiser_outils_v1 (dossiers vides tolérés et retirés quand c'est permis ; raccourcis d'un outil sans version courante déplacés dans _gestion/raccourcis_retires/ au lieu de rester) ; v1 remplaçait ranger_outils_v2 (organisation à plat)
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
DEPL = os.path.join(GEST, 'deplacements')


def consigner_deplacements(op, M):
    """Consigne une liste de déplacements [(source, destination)] relatifs à 00_competences_claude (un fichier immuable par opération)."""
    if not M: return
    os.makedirs(DEPL, exist_ok=True)
    f = os.path.join(DEPL, f"{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{op}.json")
    with open(f, 'x', encoding='utf-8') as g: json.dump(dict(operation=op, deplacements=[dict(source=s, destination=d) for s, d in M]), g, ensure_ascii=False, indent=1)


def deplacer(s, d, M):
    os.makedirs(os.path.dirname(d), exist_ok=True); os.rename(s, d); M.append((os.path.relpath(s, RACINE_CC), os.path.relpath(d, RACINE_CC)))


def journal(type_, donnees):
    try:
        from cc_lib_v4 import evenement; evenement('organiser_outils', 8, type_, donnees)
    except Exception: pass


def dossier(cle):
    """Dossier de l'espace désigné par sa clé logique (registre central _gestion/chemins_vN.json de cet espace, sinon la clé)."""
    V = sorted(glob.glob(os.path.join(GEST, 'chemins_v*.json')), key=lambda f: int(re.search(r'_v(\d+)\.json$', f).group(1)))
    C = json.load(open(V[-1], encoding='utf-8')).get('chemins', {}) if V else {}
    return os.path.join(RACINE_CC, C.get(cle, cle))


def h(f):
    import hashlib
    with open(f, 'rb') as g: return hashlib.sha256(g.read()).hexdigest()


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
    P = json.load(open(a[0], encoding='utf-8')); fait, saute, Mf = 0, [], []
    for m in P['deplacements']:
        s, d = os.path.join(RACINE_CC, m['source']), os.path.join(RACINE_CC, m['destination'])
        if not os.path.exists(s): saute.append((m['source'], 'absent')); continue
        if os.path.exists(d): saute.append((m['destination'], 'existe déjà')); continue
        deplacer(s, d, Mf); fait += 1
    consigner_deplacements('appliquer', Mf)
    vides(retirer=True)
    journal('appliquer', dict(plan=os.path.basename(a[0]), deplaces=fait, sautes=len(saute)))
    print(f'{fait} déplacé(s) ; {len(saute)} sauté(s)'); [print('  sauté :', *x) for x in saute[:30]]


def vides(retirer=False):
    """Dossiers vides (récursivement) sous outils/ ; retirés si possible (rmdir n'enlève qu'un dossier vide ; refusé sur le PC sans permission)."""
    V = []
    for d in sorted(os.listdir(OUTILS)):
        p = os.path.join(OUTILS, d)
        if os.path.isdir(p) and d not in ('_gestion', '_compat') and not any(f for _, _, f in os.walk(p)): V.append(p)
    if retirer:
        dest = os.path.join(GEST, 'dossiers_vides', datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
        for p in V:
            for r, sous, _ in os.walk(p, topdown=False):
                try: os.rmdir(r)
                except OSError: pass
            if os.path.isdir(p): os.makedirs(dest, exist_ok=True); os.rename(p, os.path.join(dest, os.path.basename(p)))
    return [p for p in V if os.path.isdir(p)]


def retirer_raccourcis_perimes():
    """Raccourcis du dossier principal dont l'outil n'a plus de version courante : déplacés (jamais supprimés)."""
    E = attendus(); dest = os.path.join(GEST, 'raccourcis_retires', datetime.datetime.now().strftime('%Y%m%d_%H%M%S')); n = 0; Mr = []
    for f in sorted(os.listdir(OUTILS)):
        p = os.path.join(OUTILS, f)
        if os.path.isfile(p) and (f.endswith('.lien.txt') or (f.endswith('.py') and not RX.match(f))) and p not in E and not f.startswith('_raccourci'):
            deplacer(p, os.path.join(dest, f), Mr); n += 1
    consigner_deplacements('raccourcis_retires', Mr)
    return n


def moteur():
    c = sorted((int(m.group(1)), f) for f in os.listdir(OUTILS) for m in [re.match(r'^_raccourci_v(\d+)\.py$', f)] if m)
    if not c: raise SystemExit('moteur des raccourcis absent (outils/_raccourci_vN.py)')
    return f'_raccourci_v{c[-1][0]}'


def anciens_moteurs():
    return sorted(f[:-3] for f in os.listdir(OUTILS) if re.match(r'^_raccourci_v\d+\.py$', f) and f[:-3] != moteur())


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
    return E


def raccourcis(a):
    crees, differents, regeneres = 0, [], 0; anciens = anciens_moteurs()
    dest = os.path.join(GEST, 'raccourcis_retires', datetime.datetime.now().strftime('%Y%m%d_%H%M%S_moteur')); Mm = []
    for f, t in sorted(attendus().items()):
        if os.path.exists(f):
            s = open(f, encoding='utf-8').read()
            if s != t:
                if any(s == t.replace(moteur(), m) for m in anciens):          # raccourci généré pour un ancien moteur : retiré puis régénéré
                    deplacer(f, os.path.join(dest, os.path.relpath(f, OUTILS)), Mm); regeneres += 1
                else:
                    differents.append(os.path.relpath(f, RACINE_CC)); continue
            else: continue
        os.makedirs(os.path.dirname(f), exist_ok=True)
        with open(f, 'x', encoding='utf-8') as g: g.write(t)
        crees += 1
    consigner_deplacements('raccourcis_moteur', Mm)
    if anciens and not differents and not any(open(p, encoding='utf-8').read().find(f'from {m} import') >= 0 for p in glob.glob(os.path.join(OUTILS, '*.py')) + glob.glob(os.path.join(COMPAT, '*.py')) if not os.path.basename(p).startswith('_raccourci') for m in anciens):
        Ma = []
        for m in anciens: deplacer(os.path.join(OUTILS, m + '.py'), os.path.join(OUTILS, '_raccourci', 'archive', m + '.py'), Ma)
        consigner_deplacements('moteur_archive', Ma)
    retires = retirer_raccourcis_perimes()
    journal('raccourcis', dict(crees=crees, differents=len(differents), retires=retires, regeneres=regeneres))
    if regeneres: print(f'{regeneres} raccourci(s) de l’ancien moteur régénéré(s) (anciens dans _gestion/raccourcis_retires/)')
    if retires: print(f'{retires} raccourci(s) périmé(s) déplacé(s) dans _gestion/raccourcis_retires/')
    print(f'{crees} raccourci(s) créé(s)' + (f' ; {len(differents)} différent(s) de l’attendu (non réécrits) : {differents}' if differents else ''))


def entete(f):
    E = {}
    for l in open(f, encoding='utf-8', errors='replace').read(6000).splitlines()[:40]:
        m = re.match(r'^\s*#?\s*(OUTIL|VERSION|RESUME|USAGE|CATEGORIE|BANC|REMPLACE):\s*(.*)$', l)
        if m and m.group(1) not in E: E[m.group(1)] = m.group(2).strip()
    return E


def etat_tests():
    c = sorted(glob.glob(os.path.join(dossier('tests'), 'rapports', 'rapport_tests_*.json')))
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


def versions_dossier(outil, ext):
    d = os.path.join(OUTILS, outil)
    return sorted((int(m.group(1)), os.path.join(d, f)) for f in (os.listdir(d) if os.path.isdir(d) else [])
                  for m in [re.match(re.escape(outil) + r'_v(\d+)\.' + ext + '$', f)] if m)


def candidats_dossier(outil, ext):
    d = os.path.join(OUTILS, outil, 'candidat')
    return sorted((int(m.group(1)), os.path.join(d, f)) for f in (os.listdir(d) if os.path.isdir(d) else [])
                  for m in [re.match(re.escape(outil) + r'_v(\d+)\.' + ext + '$', f)] if m)


def preparer(a):
    outil = a[0]; ext = opt(a, '--ext', 'py'); V = versions_dossier(outil, ext)
    if not V: raise SystemExit(f'aucune version de {outil} dans outils/{outil}/')
    if len(V) > 1 or candidats_dossier(outil, ext): raise SystemExit(f'{outil} : une version candidate existe déjà ; l’adopter ou la terminer d’abord')
    n, f = V[-1]; s = open(f, encoding='utf-8').read()
    s = re.sub(r'(?m)^(\s*#?\s*VERSION:\s*)\d+', lambda m: m.group(1) + str(n + 1), s, count=1)
    s = re.sub(r'(?m)^(\s*#?\s*REMPLACE:\s*)(.*)$', lambda m: m.group(1) + f'{outil}_v{n} (À DÉCRIRE : ce qui change) ; v{n} : ' + m.group(2), s, count=1)
    s = re.sub(re.escape(outil) + r'_v' + str(n) + r'\.' + ext, f'{outil}_v{n + 1}.{ext}', s)
    s = s.replace(f"evenement('{outil}', {n},", f"evenement('{outil}', {n + 1},")
    c = os.path.join(OUTILS, outil, 'candidat', f'{outil}_v{n + 1}.{ext}'); os.makedirs(os.path.dirname(c), exist_ok=True)
    with open(c, 'x', encoding='utf-8') as g: g.write(s)
    journal('preparer', dict(outil=outil, version=n + 1)); print('brouillon :', os.path.relpath(c, RACINE_CC))


def adopter(a):
    import subprocess
    outil = a[0]; ext = opt(a, '--ext', 'py'); Cd = candidats_dossier(outil, ext); Mc = []
    if Cd:                                                   # brouillon de candidat/ : mis en place le temps des tests
        n, f = Cd[-1]; s = open(f, encoding='utf-8').read()
        if re.search(r'(?m)^\s*#?\s*REMPLACE:.*À DÉCRIRE', s): raise SystemExit('en-tête REMPLACE à compléter (« À DÉCRIRE ») avant l’adoption')
        place = os.path.join(OUTILS, outil, os.path.basename(f))
        if os.path.exists(place): raise SystemExit(f'existe déjà : {place}')
        deplacer(f, place, Mc)
    V = versions_dossier(outil, ext)
    if not V: raise SystemExit(f'aucune version de {outil}')
    n, f = V[-1]; s = open(f, encoding='utf-8').read()
    if re.search(r'(?m)^\s*#?\s*REMPLACE:.*À DÉCRIRE', s): raise SystemExit('en-tête REMPLACE à compléter (« À DÉCRIRE ») avant l’adoption')
    if '--sans-tests' not in a and ext == 'py':
        r = subprocess.run([sys.executable, os.path.join(OUTILS, 'tester_outils.py'), '--candidat', f'{outil}={n}'], capture_output=True, text=True)
        print(r.stdout.strip()[-1200:])
        if r.returncode != 0:
            if Mc: os.rename(os.path.join(RACINE_CC, Mc[0][1]), os.path.join(RACINE_CC, Mc[0][0]))   # remise dans candidat/
            raise SystemExit(f'adoption refusée : tests en échec pour {outil}_v{n}')
    if Mc:
        consigner_deplacements('adopter_candidat', Mc)
        try: os.rmdir(os.path.join(OUTILS, outil, 'candidat'))
        except OSError: pass
    deplaces, Ma = 0, []
    for v, g in V[:-1]:
        d = os.path.join(OUTILS, outil, 'archive', os.path.basename(g))
        if os.path.exists(d): raise SystemExit(f'archive existante : {d}')
        deplacer(g, d, Ma); deplaces += 1
    consigner_deplacements('adopter', Ma)
    raccourcis([]); registre([])
    cat = os.path.join(OUTILS, 'catalogue.py')                # v8 : catalogue régénéré à chaque adoption
    if os.path.exists(cat):
        rc_ = subprocess.run([sys.executable, cat], capture_output=True, text=True)
        print('catalogue :', ((rc_.stdout.strip().splitlines() or ['—'])[-1]) if rc_.returncode == 0 else 'ÉCHEC de la régénération : ' + (rc_.stdout + rc_.stderr).strip()[-300:])
    else: print('catalogue : outil absent de cet espace, non régénéré')
    journal('adopter', dict(outil=outil, version=n, archivees=deplaces)); print(f'{outil}_v{n} adopté ; {deplaces} version(s) archivée(s)')


def rejouer(a):
    fait, deja, absents, doublons = 0, 0, [], 0
    for f in sorted(glob.glob(os.path.join(DEPL, '*.json'))):
        for m in json.load(open(f, encoding='utf-8'))['deplacements']:
            src, dst = os.path.join(RACINE_CC, m['source']), os.path.join(RACINE_CC, m['destination'])
            if os.path.exists(dst) and not os.path.exists(src): deja += 1; continue
            if not os.path.exists(src): absents.append(m['source']); continue
            if os.path.exists(dst):
                if os.path.isfile(src) and h(src) == h(dst):          # même contenu des deux côtés : la source est rangée, jamais supprimée
                    r = os.path.join(GEST, 'doublons_rejouer', datetime.datetime.now().strftime('%Y%m%d'), m['source'])
                    if not os.path.exists(r): os.makedirs(os.path.dirname(r), exist_ok=True); os.rename(src, r); doublons += 1; continue
                absents.append(m['destination'] + ' (existe des deux côtés : à vérifier)'); continue
            os.makedirs(os.path.dirname(dst), exist_ok=True); os.rename(src, dst); fait += 1
    vides(retirer=True)
    journal('rejouer', dict(deplaces=fait, deja=deja, absents=len(absents), doublons=doublons))
    print(f'{fait} déplacement(s) rejoué(s) ; {deja} déjà faits ; {doublons} doublon(s) identique(s) rangé(s) ; {len(absents)} non applicables'); [print('  ', x) for x in absents[:20]]


def consigner(a):
    s, d = a[0], a[1]
    if not os.path.exists(os.path.join(RACINE_CC, d)): raise SystemExit('destination absente : le déplacement doit déjà être fait')
    consigner_deplacements('manuel', [(s, d)]); print('consigné :', s, '->', d)


def verifier(a):
    if '--ranger-vides' in a: vides(retirer=True)
    P = constats(); journal('verifier', dict(constats=len(P)))
    print('ORGANISATION CONFORME' if not P else f'ORGANISATION NON CONFORME : {len(P)} constat(s)'); [print('  ', x) for x in P[:40]]
    sys.exit(1 if P else 0)


if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] not in ('preparer', 'adopter', 'rejouer', 'consigner', 'plan', 'appliquer', 'raccourcis', 'registre', 'verifier'):
        print(__doc__.split('USAGE: ')[1].split('ENTREES:')[0].rstrip()); sys.exit(2)
    {'preparer': preparer, 'adopter': adopter, 'rejouer': rejouer, 'consigner': consigner, 'plan': plan, 'appliquer': appliquer, 'raccourcis': raccourcis, 'registre': registre, 'verifier': verifier}[sys.argv[1]](sys.argv[2:])
