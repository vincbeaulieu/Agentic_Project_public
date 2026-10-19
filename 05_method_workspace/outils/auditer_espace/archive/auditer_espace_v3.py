"""
OUTIL: auditer_espace
VERSION: 3
RESUME: Audit déterministe et incrémental des dossiers pour la revue quotidienne : arbre des fichiers (taille, date, empreinte) comparé à l'arbre précédent du même espace (ajouts, suppressions, modifications, déplacements) ; seuls les fichiers, outils et dossiers de travail modifiés depuis l'audit précédent sont réexaminés, les constats des éléments inchangés sont repris ; contrôles : artefacts que rien n'utilise, doublons, fichiers vides ou temporaires, structure de chaque outil selon les conventions (une version courante, en-tête complet, tests présents et à jour, pas de chemin absolu figé), scripts à promouvoir, outils inutilisés, croissance des essais et du journal, catalogue et registre périmés, tests à relancer, organisation, approbations en attente, file LM Studio, classifieurs ; suivi d'un audit à l'autre (nouveaux, persistants depuis telle date, résolus) et recommandations avec la commande à lancer.
USAGE: python3 outils/auditer_espace.py [--racine <Revision ou /home/claude>] [--espace <nom>] [--jours 30] [--complet]   (--complet : tout réexaminer ; --espace : par défaut le nom du dossier racine, « Revision » sur le PC, « claude » dans le cloud)
ENTREES: 00_competences_claude/ et dossiers NN_* de la racine ; revues/etat/etat_audit_<espace>_*.json (audit précédent du même espace) ; revues/config_audit_v*.json (facultatif : intouchables, ne_pas_juger) ; tests/ et tests/rapports/ ; outils/_gestion/adoption_outils_v*.json ; journal/ ; file LM Studio si présente
SORTIES: 00_competences_claude/revues/ : arbres/arbre_<espace>_<ts>.json, etat/etat_audit_<espace>_<ts>.json, audit_<espace>_<ts>.json, audit_<espace>_<ts>.md ; événement dans journal/ ; code 1 s'il existe un constat bloquant
CATEGORIE: qualite
BANC: tests/test_auditer_espace_v3.py
REMPLACE: auditer_espace_v2 (dernier rapport de tests et dernier état choisis par l'horodatage du nom, non par la date du fichier : sur le PC, la sauvegarde donne à tous les fichiers la date de la copie ; tests à relancer (A25) déduits des changements de code entre deux audits et suivis jusqu'à un rapport de tests postérieur) ; v2 : auditer_espace_v1 (tout réexaminé à chaque fois ; pas d'arbre ni de comparaison avec l'audit précédent ; pas de suivi des constats ; structure des outils non contrôlée ; dossiers « 00_* » et intouchables évalués comme dossiers de travail)
"""
import sys, os, re, json, glob, time, hashlib, datetime, subprocess, collections
H = os.path.dirname(os.path.abspath(__file__)); O = H
while os.path.basename(O) != 'outils' and os.path.dirname(O) != O: O = os.path.dirname(O)
OUTILS = O; CC = os.path.dirname(O); REV = os.path.join(CC, 'revues')
for p in (os.path.join(OUTILS, '_compat'), OUTILS):
    if p not in sys.path: sys.path.insert(0, p)
VERSION = 3
TEXTE = ('.py', '.md', '.json', '.jsonl', '.txt', '.js', '.ps1', '.cmd', '.csv')
EXCLUS = re.compile(r'(^|/)(__pycache__|_test_execution|journal|\.git|_execution|_sync|paquets)(/|$)')
NE_PAS_JUGER = r'(^|/)(archive|_compat|_essais[^/]*|_copie_cloud[^/]*|00_sources|98_livrables|99_livrables_modifiables)(/|$)|^00_espace_cloud_claude/(racine|scratchpad_session[^/]*|scripts_racine)(/|$)'
INTOUCHABLES = ['10_revision_01.1']           # dossiers de l'utilisateur : dans l'arbre, jamais jugés ni évalués
GRAV = {'bloquant': 0, 'majeur': 1, 'mineur': 2, 'info': 3}
ENTETE = ('OUTIL', 'VERSION', 'RESUME', 'USAGE', 'ENTREES', 'SORTIES', 'CATEGORIE', 'BANC', 'REMPLACE')
SANS_EXEC = ('cc_lib', 'appliquer_suivi', 'moteur_revision_multi', 'docx_couches', 'detecteurs_rapport', 'README_file_lmstudio', 'worker_lmstudio', 'lancer_worker_lmstudio')
RECO = {'A01': "Ouvrir l'outil qui produit ce fichier : supprimer cette sortie, ou la rendre consommable (format lu par un autre outil) ; nouvelle version par « organiser_outils.py preparer <outil> ».",
        'A02': "Garder une seule source et la référencer ; si un outil recopie, le corriger (preparer/adopter).",
        'A03': "Fichier vide : trouver l'outil qui l'a créé et corriger la sortie.",
        'A04': "Fichier temporaire resté : vérifier qu'un outil n'a pas été interrompu ; le ranger hors des dossiers suivis.",
        'A06': "Créer tests/test_<outil>_v1.py (guide de création d'outils, § 3), puis « tester_outils.py ».",
        'A07': "Outil inutilisé : le généraliser s'il doit servir, ou le marquer abandonné dans _gestion/adoption_outils.",
        'A08': "Régénérer : « catalogue.py » et « organiser_outils.py registre ».",
        'A10': "Rappeler à l'utilisateur la leçon en attente d'approbation.",
        'A11': "Rappeler à l'utilisateur l'approbation du mémoire (« memoire.py etat »).",
        'A12': "Archiver les anciens essais ou événements (outil à créer si cela se répète).",
        'A13': "Lancer « evaluer_travail.py <dossier> » pour le détail, corriger par les outils.",
        'A16': "Relancer « tester_outils.py --complet » et corriger les échecs avant tout autre travail.",
        'A17': "Lancer « organiser_outils.py verifier --ranger-vides » puis corriger ou « rejouer ».",
        'A18': "Vérifier l'ouvrier LM Studio (procédure, § 1) et demander à l'utilisateur de le relancer.",
        'A20': "Promouvoir en outil : outils/<outil>/<outil>_v1.py + tests, puis remplacer les copies (guide, § 3).",
        'A22': "Réentraîner : « entrainer_classifieur.py entrainer <tache> --nom … --base … », puis comparer au banc.",
        'A23': "Mettre l'outil aux conventions (une seule version courante, en-tête complet, pas de chemin absolu) : preparer/adopter.",
        'A24': "Nouvelle version d'outil sans nouveaux tests : ajouter tests/test_<outil>_v(K+1).py pour ses ajouts.",
        'A25': "Relancer « tester_outils.py » : des outils ou des tests ont changé depuis le dernier rapport."}


def opt(a, k, d=None): return a[a.index(k) + 1] if k in a else d


def h16(f):
    x = hashlib.sha256()
    with open(f, 'rb') as g:
        for b in iter(lambda: g.read(1 << 20), b''): x.update(b)
    return x.hexdigest()[:16]


def dernier(motif):
    """Fichier le plus récent d'après l'horodatage ou la version de son nom (AAAAMMJJ_HHMMSS, _vN), puis d'après sa date."""
    L = glob.glob(motif)
    return max(L, key=lambda f: (re.findall(r'\d{8}_\d{6}(?:_\d+)?', os.path.basename(f))[-1:], num_v(f), os.path.getmtime(f))) if L else None


def ts_nom(f):
    m = re.findall(r'\d{8}_\d{6}', os.path.basename(f or '')); return m[-1] if m else ''


def num_v(f):
    m = re.search(r'_v(\d+)\.[^.]+$', f); return int(m.group(1)) if m else -1


def config():
    """Réglages facultatifs (dernière version de revues/config_audit_v*.json) : {"intouchables": [...], "ne_pas_juger": [regex...]}."""
    f = max(glob.glob(os.path.join(REV, 'config_audit_v*.json')), key=num_v, default=None)
    c = charger(f) if f else {}
    npj = NE_PAS_JUGER + ''.join('|' + r for r in c.get('ne_pas_juger', []))
    intou = list(dict.fromkeys(INTOUCHABLES + c.get('intouchables', [])))
    npj += ''.join(f'|^{re.escape(i)}(/|$)' for i in intou)
    return re.compile(npj), intou


def arbre(racine, precedent, exclus_rel=()):
    """{chemin relatif: [taille, mtime en ms, empreinte]} ; l'empreinte n'est recalculée que si taille ou date ont changé."""
    P = precedent or {}; A = {}; ex = tuple(e.rstrip('/') + '/' for e in exclus_rel)
    racines = [CC] + sorted(d for d in glob.glob(os.path.join(racine, '[0-9][0-9]_*')) if os.path.isdir(d) and os.path.realpath(d) != os.path.realpath(CC))
    for r in racines:
        for d, sous, fs in os.walk(r):
            rel_d = os.path.relpath(d, racine).replace(os.sep, '/')
            sous[:] = sorted(s for s in sous if not EXCLUS.search(rel_d + '/' + s) and not (rel_d + '/' + s + '/').startswith(ex))
            for f in fs:
                p = os.path.join(d, f); rel = os.path.relpath(p, racine).replace(os.sep, '/')
                try: st = os.stat(p)
                except OSError: continue
                t, m = st.st_size, st.st_mtime_ns // 1_000_000
                old = P.get(rel)
                try: A[rel] = [t, m, old[2] if old and old[0] == t and old[1] == m else h16(p)]
                except OSError: continue                          # fichier verrouillé : au passage suivant
    return A


def comparer(A, B):
    if B is None: return dict(premier=True, ajoutes=sorted(A), supprimes=[], modifies=[], deplaces=[])
    aj = sorted(set(A) - set(B)); su = sorted(set(B) - set(A)); mo = sorted(p for p in set(A) & set(B) if A[p][2] != B[p][2])
    par_h = collections.defaultdict(list)
    for p in aj: par_h[A[p][2]].append(p)
    dep = []
    for p in su:
        if par_h.get(B[p][2]): dep.append([p, par_h[B[p][2]].pop(0)])
    da = {d for _, d in dep}; ds = {s for s, _ in dep}
    return dict(premier=False, ajoutes=[p for p in aj if p not in da], supprimes=[p for p in su if p not in ds], modifies=mo, deplaces=dep)


def resume_arbre(A, detail=('00_competences_claude',)):
    """Répartition par dossier de premier niveau ; un niveau de plus pour les dossiers de « detail » (fichiers posés à la racine : « (racine) »)."""
    c = collections.Counter(); t = collections.Counter()
    for p, (s, _, _) in A.items():
        q = p.split('/'); k = q[0] + '/' + (q[1] + '/' if len(q) > 2 else '(racine)') if q[0] in detail else q[0] + '/'
        c[k] += 1; t[k] += s
    return [f'{k} — {c[k]} fichiers, {t[k] / 1e6:.1f} Mo' for k in sorted(c)]


def charger(f):
    with open(f, encoding='utf-8') as g: return json.load(g)


def lire(f):
    with open(f, encoding='utf-8', errors='ignore') as g: return g.read()


def mentions_de(chemin):
    try: t = lire(chemin)
    except Exception: return []
    return sorted(set(re.findall(r'[\w.\-]+\.(?:txt|log|md|json|jsonl|csv|docx|xlsx|py)', t)))


def controles_fichier(rel, info, mentions, npj):
    K = []; b = rel.rsplit('/', 1)[-1]
    if npj.search(rel): return K
    if b.endswith(('.txt', '.log')) and mentions[b] == 0:
        K.append(('A01', 'mineur', f'artefact {b} : rien ne le lit ni ne le cite'))
    if info[0] == 0: K.append(('A03', 'mineur', 'fichier vide'))
    if re.match(r'^(~\$|\.~lock)', b) or b.endswith(('.tmp', '.part', '.swp')): K.append(('A04', 'mineur', 'fichier temporaire resté'))
    return K


def outils_courants():
    """{outil: fichier de la version courante} : dossiers outils/<outil>/ (hors _*, abandonnés et remplacés)."""
    f = max(glob.glob(os.path.join(OUTILS, '_gestion', 'adoption_outils_v*.json')), key=num_v, default=None)
    hors = {k for k, v in (charger(f).get('decisions', {}) if f else {}).items() if v.get('statut') in ('abandonné', 'remplacé')}
    R = {}
    for d in sorted(os.listdir(OUTILS)):
        if not os.path.isdir(os.path.join(OUTILS, d)) or d.startswith('_') or d in hors: continue
        cur = sorted(glob.glob(os.path.join(OUTILS, d, f'{d}_v*.*')), key=num_v)
        if cur: R[d] = cur
    return R


def couverture(outils):
    """{outil: [fichiers de tests]} : test_<outil>_vK.py, ou suite qui cite l'outil dans son code."""
    T = collections.defaultdict(list)
    for f in glob.glob(os.path.join(CC, 'tests', 'test_*_v*.py')):
        m = re.match(r'test_(.+?)_v\d+\.py$', os.path.basename(f)); txt = lire(f)
        for d in outils:
            if m.group(1) == d or re.search(r"""['"]""" + re.escape(d) + r"""['"]|\b""" + re.escape(d) + r'_v\d', txt): T[d].append(f)
    return T


def controles_outil(d, fichiers, tests):
    K = []
    if len(fichiers) > 1: K.append(('A23', 'majeur', f'{len(fichiers)} versions dans outils/{d}/ : une candidate à adopter ou à ranger'))
    f = fichiers[-1]; ext = os.path.splitext(f)[1]
    if ext in ('.py', '.ps1'):
        t = lire(f)
        manq = [c for c in ENTETE if not re.search(r'(?m)^\s*#?\s*' + c + r':', t[:8000])]
        if manq: K.append(('A23', 'majeur', 'en-tête incomplet : ' + ', '.join(manq)))
        code = re.sub(r'(?s)^\s*"""(.*?)"""', '', t, count=1)
        if re.search(r"['\"]/home/claude/", code): K.append(('A23', 'mineur', 'chemin absolu figé (/home/claude/…) : outil non portable vers le PC'))
    if ext == '.md': return K                                       # README : pas de tests
    T = tests.get(d, [])
    if not T: K.append(('A06', 'majeur' if ext in ('.py', '.ps1') else 'mineur', f'outil {d} sans tests unitaires'))
    else:                                                           # nouvelle version : une suite ajoutée ou modifiée depuis la version précédente
        prec = [x for x in glob.glob(os.path.join(OUTILS, d, 'archive', f'{d}_v*{ext}')) + fichiers[:-1] if num_v(x) < num_v(f)]
        if prec and max(map(os.path.getmtime, T)) < os.path.getmtime(max(prec, key=num_v)):
            K.append(('A24', 'mineur', f'{os.path.basename(f)} : aucune suite de tests ajoutée ou modifiée depuis la version précédente'))
    return K


def etat_precedent(espace, complet):
    if complet: return {}
    f = dernier(os.path.join(REV, 'etat', f'etat_audit_{espace}_*.json'))
    return charger(f) if f else {}


def auditer(racine, jours, complet, espace, ts):
    npj, intou = config()
    E0 = etat_precedent(espace, complet)
    A0 = charger(os.path.join(REV, 'arbres', E0['arbre'])) if E0.get('arbre') else None
    rel_rev = os.path.relpath(REV, racine).replace(os.sep, '/')
    A = arbre(racine, A0, [rel_rev]); D = comparer(A, A0)
    change = set(D['ajoutes']) | set(D['modifies']) | set(D['supprimes']) | {x for c in D['deplaces'] for x in c}
    pre_out = os.path.relpath(OUTILS, racine).replace(os.sep, '/') + '/'
    pre_tst = os.path.relpath(os.path.join(CC, 'tests'), racine).replace(os.sep, '/') + '/'
    M0 = E0.get('mentions', {}); M = {}
    for p in A:
        if p.endswith(TEXTE) and A[p][0] < 2_000_000 and not npj.search(p) or p.startswith(pre_out):
            M[p] = M0[p] if (p in M0 and p not in change) else mentions_de(os.path.join(racine, p))
    mentions = collections.Counter(n for p, L in M.items() for n in L)
    K = []                                                        # (code, gravité, message, chemin, portée)
    for p, info in A.items():                                     # contrôles de fichier : peu coûteux, à partir de l'arbre
        for k in controles_fichier(p, info, mentions, npj): K.append(k + (p, 'fichier'))
    par_h = collections.defaultdict(list)
    for p, (s, _, hh) in A.items():
        if s >= 200 and not npj.search(p): par_h[hh].append(p)
    for hh, L in par_h.items():
        if len(L) > 1: K.append(('A02', 'mineur', f'{len(L)} copies identiques : ' + ' ; '.join(L[:4]), L[0], 'fichier'))
    # outils : réexaminés seulement si leur dossier ou une suite de tests a changé
    K0 = collections.defaultdict(list)
    for k in E0.get('constats', []): K0[(k['portee'], k['cle'])].append(k)
    revus = dict(outils=0, outils_repris=0, travaux=0, travaux_repris=0)
    oc = outils_courants(); tests_changes = any(p.startswith(pre_tst + 'test_') for p in change)
    tests = couverture(oc) if (complet or not E0 or tests_changes or any(p.startswith(pre_out) for p in change)) else None
    for d, fichiers in oc.items():
        if complet or not E0 or tests_changes or any(p.startswith(pre_out + d + '/') for p in change):
            revus['outils'] += 1; K += [k + (f'{pre_out}{d}', 'outil') for k in controles_outil(d, fichiers, tests)]
        else: revus['outils_repris'] += 1; K += [(k['code'], k['gravite'], k['message'], k['chemin'], 'outil') for k in K0[('outil', f'{pre_out}{d}')]]
    # dossiers de travail (NN_*, hors 00_* et intouchables) : évalués seulement s'ils ont changé
    for t in sorted(glob.glob(os.path.join(racine, '[0-9][0-9]_*'))):
        n = os.path.basename(t)
        if not os.path.isdir(t) or os.path.realpath(t) == os.path.realpath(CC) or n.startswith('00_') or n in intou: continue
        if complet or not E0 or any(p.startswith(n + '/') for p in change):
            revus['travaux'] += 1
            r = subprocess.run([sys.executable, os.path.join(OUTILS, 'evaluer_travail.py'), t, '--sans-xsd', '--sans-manifeste'], capture_output=True, text=True)
            l = (r.stdout.strip().splitlines() or ['?'])[-1]
            if 'NON CONFORME' in l or 'CONFORME' not in l: K.append(('A13', 'majeur', f'dossier de travail non conforme : {l.strip()[:200]}', n, 'travail'))
        else: revus['travaux_repris'] += 1; K += [(k['code'], k['gravite'], k['message'], k['chemin'], 'travail') for k in K0[('travail', n)]]
    # contrôles globaux (bon marché, refaits à chaque audit)
    scripts = collections.defaultdict(set)
    for p in A:
        m = re.match(r'^([0-9][0-9]_[^/]+)/90_scripts/(.+?)_v\d+\.py$', p)
        if m and not npj.search(p): scripts[m.group(2)].add(m.group(1))
    for s, T in scripts.items():
        if len(T) > 1: K.append(('A20', 'majeur', f'script de travail « {s} » présent dans {len(T)} travaux : à promouvoir en outil', ', '.join(sorted(T)), 'global'))
    t_outils = max((os.path.getmtime(f[-1]) for f in oc.values()), default=0)
    for nom, motif in (('catalogue', os.path.join(CC, 'catalogue', 'catalogue_outils_v*.json')), ('registre', os.path.join(OUTILS, '_gestion', 'registre_outils_v*.json'))):
        f = dernier(motif)
        if not f or os.path.getmtime(f) < t_outils - 1: K.append(('A08', 'mineur', f'{nom} plus ancien que le dernier outil', None, 'global'))
    r = dernier(os.path.join(CC, 'tests', 'rapports', 'rapport_tests_*.json')); attente = E0.get('tests_a_relancer_depuis')
    t_code = max([os.path.getmtime(f[-1]) for f in oc.values()] + [os.path.getmtime(f) for f in glob.glob(os.path.join(CC, 'tests', 'test_*.py'))] or [0])
    if not r: K.append(('A16', 'majeur', 'aucun rapport de tests', None, 'global')); attente = attente or ts
    else:
        R = charger(r); rr = os.path.relpath(r, racine).replace(os.sep, '/')
        if R.get('verdict') != 'conforme': K.append(('A16', 'bloquant', f"derniers tests en échec : {R.get('unitaires', {}).get('echecs', '?')} unitaire(s), {R.get('fumee', {}).get('echecs', '?')} fumée", rr, 'global'))
        code = [p for p in change if (p.startswith(pre_out) and p.endswith(('.py', '.ps1', '.cmd'))) or (p.startswith(pre_tst + 'test_') and p.endswith('.py'))]
        if not E0:                                                # premier audit : d'après les dates des fichiers
            if os.path.getmtime(r) < t_code - 1: attente = ts
        elif code: attente = ts                                   # changement vu par cet audit : il faut un rapport postérieur
        elif attente and ts_nom(r) > attente: attente = None      # tests relancés depuis
        if attente: K.append(('A25', 'majeur', f'outils ou tests modifiés (constaté le {attente}) sans rapport de tests postérieur : tests à relancer', None, 'global'))
    if complet or not E0 or any(p.startswith(pre_out) for p in change):
        v = subprocess.run([sys.executable, os.path.join(OUTILS, 'organiser_outils.py'), 'verifier'], capture_output=True, text=True)
        if v.returncode != 0: K.append(('A17', 'majeur', 'organisation des outils non conforme : ' + (v.stdout + v.stderr).strip()[-300:], None, 'global'))
    else: K += [(k['code'], k['gravite'], k['message'], k['chemin'], 'global') for k in E0.get('constats', []) if k['code'] == 'A17']
    usage = collections.Counter(); lim = time.time() - jours * 86400
    for f in glob.glob(os.path.join(CC, 'journal', '*', '*.json')):
        m = re.match(r'^\d{8}_\d{6}_(.+?)_v\d+_', os.path.basename(f))
        if m and os.path.getmtime(f) >= lim: usage[m.group(1)] += 1
    for d in oc:
        if not usage[d] and d not in SANS_EXEC and oc[d][-1].endswith('.py'): K.append(('A07', 'info', f'outil {d} sans exécution consignée depuis {jours} j', f'{pre_out}{d}', 'global'))
    n_ess = sum(len(fs) for _, _, fs in os.walk(os.path.join(CC, 'tests', '_test_execution')))
    if n_ess > 3000: K.append(('A12', 'info', f'tests/_test_execution : {n_ess} fichiers (archiver les anciens essais ?)', None, 'global'))
    n_j = len(glob.glob(os.path.join(CC, 'journal', '*', '*.json')))
    if n_j > 20000: K.append(('A12', 'info', f'journal : {n_j} événements (compresser par mois ?)', None, 'global'))
    for f in glob.glob(os.path.join(CC, 'lecons', 'LC-*_v*.json')):
        L = charger(f)
        der = max(glob.glob(os.path.join(CC, 'lecons', L['id'] + '_v*.json')), key=num_v)
        if L.get('statut') == 'proposee' and f == der: K.append(('A10', 'info', f"leçon {L['id']} proposée, en attente d'approbation", os.path.relpath(f, racine).replace(os.sep, '/'), 'global'))
    if not glob.glob(os.path.join(CC, 'memoire', 'statut', 'v*_approbation.json')): K.append(('A11', 'majeur', "aucune version du mémoire n'est approuvée", None, 'global'))
    fl = os.path.join(racine, '00_espace_cloud_claude', 'file_lmstudio')
    for f in glob.glob(os.path.join(fl, 'entree', '*.jsonl')) + glob.glob(os.path.join(fl, 'encours', '*.jsonl')):
        if time.time() - os.path.getmtime(f) > 86400: K.append(('A18', 'majeur', 'lot LM Studio en attente depuis plus de 24 h', os.path.basename(f), 'global'))
    for t in glob.glob(os.path.join(CC, 'entrainement', 'taches', '*_v*.json')):
        tache = re.sub(r'_v\d+\.json$', '', os.path.basename(t))
        mods = glob.glob(os.path.join(CC, 'entrainement', 'modeles', tache, '*', 'modele.npz')); lots = glob.glob(os.path.join(CC, 'entrainement', 'donnees', tache, 'lot_*.jsonl'))
        if lots and (not mods or max(map(os.path.getmtime, lots)) > max(map(os.path.getmtime, mods))):
            K.append(('A22', 'info', f'classifieur « {tache} » : données plus récentes que le dernier modèle', f'entrainement/{tache}', 'global'))
    return A, D, M, K, E0, revus, attente


def ident(k): return f"{k['code']}|{k['chemin']}|{re.sub(r'[0-9]+', '#', k['message'])[:80]}"


def suivre(C, E0, ts):
    """Continuité : chaque constat garde la date de sa première apparition (« depuis ») ; nouveaux et résolus."""
    avant = {ident(k): k for k in E0.get('constats', [])}; maint = {ident(k): k for k in C}
    for i, k in maint.items(): k['depuis'] = avant[i].get('depuis', E0.get('date')) if i in avant else ts
    return [k for i, k in maint.items() if i not in avant], [k for i, k in avant.items() if i not in maint]


def ecrire(chemin, contenu):
    """Création sans écrasement ; si le nom existe déjà (deux audits dans la même seconde), suffixe _2, _3…"""
    base, ext = os.path.splitext(chemin); i = 1
    while True:
        c = chemin if i == 1 else f'{base}_{i}{ext}'
        try:
            with open(c, 'x', encoding='utf-8') as g: g.write(contenu)
            return c
        except FileExistsError: i += 1


def age_j(depuis, ts):
    try: return (datetime.datetime.strptime(ts[:15], '%Y%m%d_%H%M%S') - datetime.datetime.strptime(depuis[:15], '%Y%m%d_%H%M%S')).days
    except Exception: return 0


def rapport(ts, espace, racine, A, D, C, nouveaux, resolus, revus, duree):
    cpt = collections.Counter(k['gravite'] for k in C); idn = {id(k) for k in nouveaux}
    lien = lambda k: f" — `{k['chemin']}`" if k['chemin'] else ''
    md = [f'# Audit de l’espace « {espace} » — {ts}', '',
          f"{len(A)} fichiers ; {duree} s. Constats : " + (', '.join(f'{cpt[g]} {g}' for g in GRAV if cpt[g]) or 'aucun') + f" ; {len(nouveaux)} nouveau(x), {len(resolus)} résolu(s) depuis l’audit précédent.", '',
          '## 1. Arbre et changements depuis l’audit précédent', '']
    if D['premier']: md += ['Premier audit de cet espace : pas d’arbre précédent ; tout a été examiné.']
    else:
        md += [f"- Ajoutés : {len(D['ajoutes'])} ; supprimés : {len(D['supprimes'])} ; modifiés : {len(D['modifies'])} ; déplacés : {len(D['deplaces'])}"]
        md += [f'  - + {p}' for p in D['ajoutes'][:20]] + [f'  - − {p}' for p in D['supprimes'][:20]] + [f'  - ~ {p}' for p in D['modifies'][:20]] + [f'  - → {s} ⇒ {d}' for s, d in D['deplaces'][:20]]
        n = sum(len(D[c]) for c in ('ajoutes', 'supprimes', 'modifies', 'deplaces'))
        if n > 80: md += [f'  - … liste complète dans audit_{espace}_{ts}.json']
    md += ['', 'Répartition :', ''] + [f'- {l}' for l in resume_arbre(A)] + ['',
           f"Réexaminés : {revus['outils']} outil(s), {revus['travaux']} dossier(s) de travail ; repris sans réexamen (inchangés depuis l’audit précédent) : {revus['outils_repris']} outil(s), {revus['travaux_repris']} dossier(s).", '']
    md += ['## 2. Nouveaux constats', '']
    for g in GRAV:
        L = [k for k in nouveaux if k['gravite'] == g]
        if L: md += [f'### {g.capitalize()} ({len(L)})', ''] + [f"- **{k['code']}** {k['message']}{lien(k)}" for k in L[:150]] + ([f'- … {len(L) - 150} autres (JSON)'] if len(L) > 150 else []) + ['']
    if not nouveaux: md += ['Aucun.', '']
    md += ['## 3. Constats persistants (suivi)', '']
    P = [k for k in C if id(k) not in idn]
    graves = [k for k in P if GRAV[k['gravite']] <= 1]
    if graves: md += ['| Gravité | Code | Constat | Depuis | Jours |', '|---|---|---|---|---|'] + [f"| {k['gravite']} | {k['code']} | {k['message'][:110].replace('|', '/')}{lien(k)} | {k['depuis']} | {age_j(k['depuis'], ts)} |" for k in graves] + ['']
    legers = collections.defaultdict(list)
    for k in P:
        if GRAV[k['gravite']] > 1: legers[k['code']].append(k)
    for c, L in sorted(legers.items()):
        md += [f"- **{c}** ({L[0]['gravite']}) : {len(L)} constat(s), le plus ancien depuis {min(k['depuis'] for k in L)} ; ex. : " + ' ; '.join((k['chemin'] or k['message'][:60]) for k in L[:3])]
    if not P: md += ['Aucun.']
    md += ['']
    if resolus: md += ['## 4. Résolus depuis l’audit précédent', ''] + [f"- ~~{k['code']} {k['message'][:120]}~~{lien(k)}" for k in resolus[:60]] + ([f'- … {len(resolus) - 60} autres'] if len(resolus) > 60 else []) + ['']
    else: md += ['## 4. Résolus depuis l’audit précédent', '', 'Aucun.', '']
    nv = collections.Counter(k['code'] for k in nouveaux); tot = collections.Counter(k['code'] for k in C)
    ordre = sorted(tot, key=lambda c: (min(GRAV[k['gravite']] for k in C if k['code'] == c), -nv[c], c))
    md += ['## 5. Recommandations (une par type de constat, les plus graves d’abord)', ''] + [f"- **{c}** ({tot[c]}, dont {nv[c]} nouveau(x)) : {RECO.get(c, '—')}" for c in ordre]
    return md


def main():
    a = sys.argv[1:]; racine = os.path.abspath(opt(a, '--racine', os.path.dirname(CC))); jours = int(opt(a, '--jours', 30)); complet = '--complet' in a
    espace = re.sub(r'[^\w.-]', '_', opt(a, '--espace', os.path.basename(racine.rstrip('/\\')) or 'racine'))
    t0 = time.time(); ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S'); A, D, M, K, E0, revus, attente = auditer(racine, jours, complet, espace, ts)
    K = [(c, g, re.sub(r'\s*\n\s*', ' ; ', m), p, po) for c, g, m, p, po in K]
    C = [dict(code=c, gravite=g, message=m, chemin=p, portee=po, cle=p if po in ('outil', 'travail') else f'{c}|{p}|{m[:60]}') for c, g, m, p, po in K]
    C.sort(key=lambda k: (GRAV[k['gravite']], k['code'], k['chemin'] or '', k['message']))
    nouveaux, resolus = suivre(C, E0, ts)
    for d in ('arbres', 'etat'): os.makedirs(os.path.join(REV, d), exist_ok=True)
    fa = ecrire(os.path.join(REV, 'arbres', f'arbre_{espace}_{ts}.json'), json.dumps(A, sort_keys=True))
    E = dict(version=VERSION, date=ts, espace=espace, racine=racine, arbre=os.path.basename(fa), tests_a_relancer_depuis=attente, mentions=M, constats=C)
    ecrire(os.path.join(REV, 'etat', f'etat_audit_{espace}_{ts}.json'), json.dumps(E, ensure_ascii=False))
    cpt = collections.Counter(k['gravite'] for k in C); duree = round(time.time() - t0, 1)
    R = dict(version=VERSION, date=ts, espace=espace, racine=racine, fichiers=len(A), duree_s=duree, precedent=E0.get('date'), tests_a_relancer_depuis=attente,
             arbre=dict(premier=D['premier'], ajoutes=D['ajoutes'], supprimes=D['supprimes'], modifies=D['modifies'], deplaces=D['deplaces']),
             reexamines=revus, par_gravite=dict(cpt), nouveaux=[ident(k) for k in nouveaux], resolus=[dict(code=k['code'], chemin=k['chemin'], message=k['message']) for k in resolus], constats=C)
    fj = ecrire(os.path.join(REV, f'audit_{espace}_{ts}.json'), json.dumps(R, ensure_ascii=False, indent=1))
    md = rapport(ts, espace, racine, A, D, C, nouveaux, resolus, revus, duree)
    fm = ecrire(os.path.join(REV, f'audit_{espace}_{ts}.md'), '\n'.join(md) + '\n')
    try:
        from cc_lib_v1 import evenement; evenement('auditer_espace', VERSION, 'audit', dict(espace=espace, fichiers=len(A), par_gravite=dict(cpt), nouveaux=len(nouveaux), resolus=len(resolus), reexamines=revus))
    except Exception: pass
    print('\n'.join(md[:3])); print(f'rapport : {os.path.relpath(fm, CC)} ; données : {os.path.relpath(fj, CC)}')
    sys.exit(1 if cpt.get('bloquant') else 0)


if __name__ == '__main__':
    main()
