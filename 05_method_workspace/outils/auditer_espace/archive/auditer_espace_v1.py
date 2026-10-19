"""
OUTIL: auditer_espace
VERSION: 1
RESUME: Audit déterministe complet des dossiers (espace de compétences et dossiers de travail) pour la revue quotidienne : artefacts produits que rien n'utilise (ex. .txt jamais référencés), doublons de contenu, fichiers vides ou temporaires restants, outils sans tests, scripts de travail répétés d'un travail à l'autre (à promouvoir en outils), catalogue ou registre périmés, tests, organisation, leçons et mémoire en attente d'approbation, croissance des dossiers d'essai, lots LM Studio en souffrance, classifieurs à réentraîner ; rapport classé par gravité.
USAGE: python3 outils/auditer_espace.py [--racine /home/claude] [--jours 30]
ENTREES: 00_competences_claude/ (outils, tests, journal, lecons, memoire, entrainement, catalogue) ; dossiers NN_* de la racine ; file LM Studio si présente
SORTIES: 00_competences_claude/revues/audit_<AAAAMMJJ_HHMMSS>.json et .md ; événement dans journal/ ; code 1 s'il existe un constat bloquant
CATEGORIE: qualite
BANC: tests/test_auditer_espace_v1.py
REMPLACE: -
"""
import sys, os, re, json, glob, time, hashlib, datetime, subprocess, collections
H = os.path.dirname(os.path.abspath(__file__)); O = H
while os.path.basename(O) != 'outils' and os.path.dirname(O) != O: O = os.path.dirname(O)
OUTILS = O; CC = os.path.dirname(O)
for p in (os.path.join(OUTILS, '_compat'), OUTILS):
    if p not in sys.path: sys.path.insert(0, p)
TEXTE = ('.py', '.md', '.json', '.jsonl', '.txt', '.js', '.ps1', '.cmd', '.csv')
IGNORES = re.compile(r'(__pycache__|_test_execution|/journal/|_copie_cloud|/\.|/archive/|/_compat/|/_essais/|/bancs/[^/]+/_execution/)')
def opt(a, k, d=None): return a[a.index(k) + 1] if k in a else d


def fichiers(racines):
    for r in racines:
        for d, sous, fs in os.walk(r):
            sous[:] = [s for s in sous if s not in ('__pycache__', '.git')]
            for f in fs: yield os.path.join(d, f)


def h(f):
    x = hashlib.sha256()
    with open(f, 'rb') as g:
        for b in iter(lambda: g.read(1 << 20), b''): x.update(b)
    return x.hexdigest()[:16]


def auditer(racine, jours):
    K = []
    def c(code, gravite, msg, chemin=None): K.append(dict(code=code, gravite=gravite, message=msg, chemin=chemin))
    travaux = sorted(d for d in glob.glob(os.path.join(racine, '[0-9][0-9]_*')) if os.path.isdir(d) and os.path.realpath(d) != os.path.realpath(CC))
    tous = [f for f in fichiers([CC] + travaux) if os.path.isfile(f)]
    # mentions de noms de fichiers dans les fichiers texte (pour les artefacts inutilisés)
    mentions = collections.Counter()
    for f in tous:
        if f.endswith(TEXTE) and os.path.getsize(f) < 2_000_000 and not IGNORES.search(f.replace(os.sep, '/')):
            try: t = open(f, encoding='utf-8', errors='ignore').read()
            except Exception: continue
            for m in set(re.findall(r'[\w.\-]+\.(?:txt|log|md|json|jsonl|csv|docx|xlsx|py)', t)): mentions[m] += 1
    for f in tous:
        p = f.replace(os.sep, '/'); b = os.path.basename(f)
        if IGNORES.search(p): continue
        if b.endswith(('.txt', '.log')) and mentions[b] == 0 and '/00_sources/' not in p and '/_sync' not in p:
            c('A01', 'mineur', f'artefact {b} : rien ne le lit ni ne le cite (utile ? sinon, l’outil qui le produit est à revoir)', os.path.relpath(f, racine))
        if os.path.getsize(f) == 0: c('A03', 'mineur', 'fichier vide', os.path.relpath(f, racine))
        if re.match(r'^(~\$|\.~lock)', b) or b.endswith(('.tmp', '.part', '.swp')): c('A04', 'mineur', 'fichier temporaire resté', os.path.relpath(f, racine))
    # doublons de contenu (hors archives, sources et copies de sauvegarde)
    par = collections.defaultdict(list)
    for f in tous:
        p = f.replace(os.sep, '/')
        if IGNORES.search(p) or '/00_sources/' in p or os.path.getsize(f) < 200 or '/98_livrables/' in p or '/99_livrables_modifiables/' in p: continue
        par[(os.path.getsize(f), h(f))].append(os.path.relpath(f, racine))
    for (_, hh), L in par.items():
        if len(L) > 1: c('A02', 'mineur', f'{len(L)} copies identiques : ' + ' ; '.join(L[:4]), L[0])
    # outils : tests, scripts de travail répétés
    tests = {re.match(r'test_(.+?)_v\d+\.py$', os.path.basename(f)).group(1) for f in glob.glob(os.path.join(CC, 'tests', 'test_*_v*.py'))}
    for d in sorted(os.listdir(OUTILS)):
        if os.path.isdir(os.path.join(OUTILS, d)) and not d.startswith('_') and d != '__pycache__' and glob.glob(os.path.join(OUTILS, d, f'{d}_v*.py')) and d not in tests:
            c('A06', 'majeur', f'outil {d} sans tests unitaires (guide : tout outil a ses tests)', f'outils/{d}')
    scripts = collections.defaultdict(set)
    for t in travaux:
        for f in glob.glob(os.path.join(t, '90_scripts', '*_v*.py')):
            scripts[re.sub(r'_v\d+\.py$', '', os.path.basename(f))].add(os.path.basename(t))
    for s, T in scripts.items():
        if len(T) > 1: c('A20', 'majeur', f'script de travail « {s} » présent dans {len(T)} travaux : à promouvoir en outil', ', '.join(sorted(T)))
    # fraîcheur du catalogue et du registre
    def dernier(motif):
        L = glob.glob(motif); return max(L, key=os.path.getmtime) if L else None
    t_outils = max((os.path.getmtime(f) for f in glob.glob(os.path.join(OUTILS, '*', '*_v*.*'))), default=0)
    for nom, motif in (('catalogue', os.path.join(CC, 'catalogue', 'catalogue_outils_v*.json')), ('registre', os.path.join(OUTILS, '_gestion', 'registre_outils_v*.json'))):
        f = dernier(motif)
        if not f or os.path.getmtime(f) < t_outils - 1: c('A08', 'mineur', f'{nom} plus ancien que le dernier outil : le régénérer', f and os.path.relpath(f, racine))
    # tests, organisation
    r = dernier(os.path.join(CC, 'tests', 'rapports', 'rapport_tests_*.json'))
    if not r: c('A16', 'majeur', 'aucun rapport de tests')
    else:
        R = json.load(open(r, encoding='utf-8')); age = (time.time() - os.path.getmtime(r)) / 3600
        if R.get('verdict') != 'conforme': c('A16', 'bloquant', f"derniers tests en échec : {R['unitaires']['echecs']} unitaire(s), {R['fumee']['echecs']} fumée", os.path.relpath(r, racine))
        if age > 24: c('A16', 'mineur', f'derniers tests vieux de {age:.0f} h', os.path.relpath(r, racine))
    v = subprocess.run([sys.executable, os.path.join(OUTILS, 'organiser_outils.py'), 'verifier'], capture_output=True, text=True)
    if v.returncode != 0: c('A17', 'majeur', 'organisation des outils non conforme : ' + v.stdout.strip()[-300:])
    # approbations en attente
    for f in glob.glob(os.path.join(CC, 'lecons', 'LC-*_v*.json')):
        L = json.load(open(f, encoding='utf-8'))
        if L.get('statut') == 'proposee' and f == max(glob.glob(os.path.join(CC, 'lecons', L['id'] + '_v*.json')), key=lambda x: int(re.search(r'_v(\d+)', x).group(1))):
            c('A10', 'info', f"leçon {L['id']} proposée, en attente de l'approbation de l'utilisateur", os.path.relpath(f, racine))
    st = glob.glob(os.path.join(CC, 'memoire', 'statut', 'v*_approbation.json'))
    if not st: c('A11', 'majeur', "aucune version du mémoire n'est approuvée : la rappeler à l'utilisateur")
    # croissance
    n_ess = sum(1 for _ in fichiers([os.path.join(CC, 'tests', '_test_execution')])) if os.path.isdir(os.path.join(CC, 'tests', '_test_execution')) else 0
    if n_ess > 3000: c('A12', 'info', f'tests/_test_execution : {n_ess} fichiers (archiver les anciens essais ?)')
    n_j = len(glob.glob(os.path.join(CC, 'journal', '*', '*.json')))
    if n_j > 20000: c('A12', 'info', f'journal : {n_j} événements (compresser par mois ?)')
    # outils non utilisés
    usage = collections.Counter()
    lim = time.time() - jours * 86400
    for f in glob.glob(os.path.join(CC, 'journal', '*', '*.json')):
        if os.path.getmtime(f) >= lim:
            m = re.match(r'^\d{8}_\d{6}_(.+?)_v\d+_', os.path.basename(f))
            if m: usage[m.group(1)] += 1
    for d in sorted(os.listdir(OUTILS)):
        if os.path.isdir(os.path.join(OUTILS, d)) and not d.startswith('_') and glob.glob(os.path.join(OUTILS, d, f'{d}_v*.py')) and not usage[d] and d not in ('cc_lib', 'appliquer_suivi', 'moteur_revision_multi', 'docx_couches'):
            c('A07', 'info', f'outil {d} sans exécution consignée depuis {jours} j', f'outils/{d}')
    # file LM Studio (si présente : sur le PC)
    fl = os.path.join(os.path.dirname(CC), '00_espace_cloud_claude', 'file_lmstudio')
    for f in glob.glob(os.path.join(fl, 'entree', '*.jsonl')) + glob.glob(os.path.join(fl, 'encours', '*.jsonl')):
        if time.time() - os.path.getmtime(f) > 86400: c('A18', 'majeur', 'lot LM Studio en attente depuis plus de 24 h (ouvrier arrêté ?)', os.path.relpath(f, os.path.dirname(CC)))
    # classifieurs
    for t in glob.glob(os.path.join(CC, 'entrainement', 'taches', '*_v*.json')):
        tache = re.sub(r'_v\d+\.json$', '', os.path.basename(t))
        mods = glob.glob(os.path.join(CC, 'entrainement', 'modeles', tache, '*', 'modele.npz'))
        lots = glob.glob(os.path.join(CC, 'entrainement', 'donnees', tache, 'lot_*.jsonl'))
        if lots and (not mods or max(map(os.path.getmtime, lots)) > max(map(os.path.getmtime, mods))):
            c('A22', 'info', f'classifieur « {tache} » : données plus récentes que le dernier modèle, réentraîner et repasser au banc', f'entrainement/{tache}')
    # dossiers de travail
    for t in travaux:
        r = subprocess.run([sys.executable, os.path.join(OUTILS, 'evaluer_travail.py'), t, '--sans-xsd', '--sans-manifeste'], capture_output=True, text=True)
        l = (r.stdout.strip().splitlines() or ['?'])[-1]
        if 'NON CONFORME' in l or 'CONFORME' not in l: c('A13', 'majeur', f'dossier de travail non conforme : {l[:200]}', os.path.basename(t))
    return K, len(tous), len(travaux)


def main():
    a = sys.argv[1:]; racine = opt(a, '--racine', os.path.dirname(CC)); jours = int(opt(a, '--jours', 30))
    t0 = time.time(); K, n, nt = auditer(racine, jours)
    ordre = {'bloquant': 0, 'majeur': 1, 'mineur': 2, 'info': 3}; K.sort(key=lambda k: (ordre[k['gravite']], k['code'], k['chemin'] or ''))
    cpt = collections.Counter(k['gravite'] for k in K); ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    R = dict(date=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), racine=racine, fichiers=n, travaux=nt,
             duree_s=round(time.time() - t0, 1), par_gravite=dict(cpt), par_code=dict(collections.Counter(k['code'] for k in K)), constats=K)
    d = os.path.join(CC, 'revues'); os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f'audit_{ts}.json'), 'x', encoding='utf-8') as g: json.dump(R, g, ensure_ascii=False, indent=1)
    md = [f"# Audit de l'espace — {R['date']}", '', f"{n} fichiers, {nt} dossiers de travail, {R['duree_s']} s. Constats : " + ', '.join(f'{v} {k}' for k, v in sorted(cpt.items(), key=lambda x: ordre[x[0]])), '']
    for g in ('bloquant', 'majeur', 'mineur', 'info'):
        L = [k for k in K if k['gravite'] == g]
        if not L: continue
        md += [f'## {g.capitalize()} ({len(L)})', ''] + [f"- **{k['code']}** {k['message']}" + (f" — `{k['chemin']}`" if k['chemin'] else '') for k in L[:200]] + ['']
    with open(os.path.join(d, f'audit_{ts}.md'), 'x', encoding='utf-8') as g: g.write('\n'.join(md) + '\n')
    try:
        from cc_lib_v1 import evenement; evenement('auditer_espace', 1, 'audit', dict(fichiers=n, par_gravite=dict(cpt), par_code=R['par_code']))
    except Exception: pass
    print('\n'.join(md[:3])); print(f'rapport : revues/audit_{ts}.md')
    sys.exit(1 if cpt.get('bloquant') else 0)


if __name__ == '__main__':
    main()
