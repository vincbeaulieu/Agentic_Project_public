"""
OUTIL: tester_outils
VERSION: 4
RESUME: Tests automatiques de tous les outils (bonnes pratiques) : tests de fumée de chaque version courante (compilation, import par le raccourci, en-tête complet), tests unitaires (tests/test_*.py, unittest de la bibliothèque standard), tests d'intégration en option (bancs) ; essai d'une version candidate avant son adoption (--candidat outil=N) ; rapport JSON et Markdown par outil, événement au journal ; code de sortie non nul au moindre échec.
USAGE: python3 outils/tester_outils.py [--complet] [--outil NOM] [--candidat NOM=N[,NOM2=M]] [--test <module>[.<Classe>[.<méthode>]]]
ENTREES: outils/<outil>/<outil>_vN.py (versions courantes) ; tests/test_*.py ; raccourcis (outils/_raccourci_vN.py)
SORTIES: tests/rapports/rapport_tests_<ts>.json et .md ; événement dans journal/ ; code 0 si tout passe
CATEGORIE: qualite
BANC: tests/test_*.py (il se teste en lançant toute la suite)
REMPLACE: tester_outils_v3 (trois défauts qui poussaient à contourner l'outil, 16 oct. 2026 : avec --candidat, la fumée échouait toujours pour une version nouvelle — « introuvable », car l'import passait par le registre des versions adoptées — fausse alarme qui habitue à ignorer un échec ; chaque échec était réduit à sa dernière ligne — « ?   ^ » pour une différence de chaînes — ce qui obligeait à relancer les tests à la main ; les tests ignorés (skipTest, skipUnless) n'étaient pas comptés, si bien qu'un test de données réelles ignoré en silence passait pour réussi ; + --test pour une seule suite, classe ou méthode, sans contourner l'outil ; chaque test repart de l'environnement initial : un test qui modifiait PYTHONPATH faisait échouer les sous-processus des tests suivants) ; v3 : tester_outils_v2 (deux rapports dans la même seconde ne plantent plus ; dossier des tests désigné par le registre central des chemins, outils/_gestion/chemins_vN.json ; candidate trouvée aussi dans outils/<outil>/candidat/ ; événements par cc_lib_v4) ; v2 : tester_outils_v1 (compilation par compile() en mémoire : py_compile vers /dev/null échouait partout)
"""
import sys, os, re, json, glob, time, datetime, traceback, unittest, importlib, py_compile, io, contextlib, collections
H = os.path.dirname(os.path.abspath(__file__)); O = H
while os.path.basename(O) != 'outils' and os.path.dirname(O) != O: O = os.path.dirname(O)
OUTILS = O; RACINE_CC = os.path.dirname(O)


def dossier(cle):
    """Dossier de l'espace désigné par sa clé logique (dernière version de outils/_gestion/chemins_vN.json, sinon la clé)."""
    V = sorted(glob.glob(os.path.join(OUTILS, '_gestion', 'chemins_v*.json')), key=lambda f: int(re.search(r'_v(\d+)\.json$', f).group(1)))
    C = {}
    if V:
        with open(V[-1], encoding='utf-8') as g: C = json.load(g).get('chemins', {})
    return os.path.join(RACINE_CC, C.get(cle, cle))


TESTS = dossier('tests')
for p in (TESTS, os.path.join(OUTILS, '_compat'), OUTILS):
    if p not in sys.path: sys.path.insert(0, p)
os.environ.setdefault('CC_BANC', 'tests')
CHAMPS = ('OUTIL', 'VERSION', 'RESUME', 'USAGE', 'ENTREES', 'SORTIES', 'CATEGORIE', 'BANC', 'REMPLACE')
def opt(a, k, d=None): return a[a.index(k) + 1] if k in a else d


def moteur():
    c = sorted((int(m.group(1)), f) for f in os.listdir(OUTILS) for m in [re.match(r'^_raccourci_v(\d+)\.py$', f)] if m)
    return importlib.import_module(f'_raccourci_v{c[-1][0]}')


def candidats(R, cand):
    """Remplace, le temps des tests, la version courante de certains outils par une version candidate. v4 : l'import de la fumée
    charge aussi la candidate (en v3, R.importer passait par les seules versions adoptées : « introuvable » pour toute version nouvelle)."""
    if not cand: return
    C = dict(x.split('=') for x in cand.split(',')); orig = R.courante; orig_imp = R.importer
    def chemin_candidat(outil, v):
        V = R.versions(outil)
        return V[v][0] if v in V else os.path.join(OUTILS, outil, 'candidat', f'{outil}_v{v}.py')
    def courante(outil, ext='py'):
        if outil in C and ext == 'py':
            v = int(C[outil]); return v, chemin_candidat(outil, v)
        return orig(outil, ext)
    def importer(nom, version=None):
        if nom in C and int(version or C[nom]) == int(C[nom]):
            v = int(C[nom]); return R._charger_module(f'{nom}_v{v}', chemin_candidat(nom, v))
        return orig_imp(nom, version)
    R.courante = courante; R.importer = importer


def fumee(R, seul=None):
    res = {}
    for d in sorted(os.listdir(OUTILS)):
        p = os.path.join(OUTILS, d)
        if not os.path.isdir(p) or d.startswith('_') or d == '__pycache__' or (seul and d != seul): continue
        try: v, f = R.courante(d)
        except ImportError: continue
        r = dict(version=v, fichier=os.path.relpath(f, RACINE_CC), erreurs=[])
        try: compile(open(f, encoding='utf-8').read(), f, 'exec')
        except Exception as e: r['erreurs'].append('compilation : ' + str(e)[:300])
        txt = open(f, encoding='utf-8').read(8000); manq = [c for c in CHAMPS if not re.search(r'(?m)^\s*#?\s*' + c + r':', txt)]
        if manq: r['erreurs'].append('en-tête incomplet : ' + ', '.join(manq))
        try:
            with contextlib.redirect_stdout(io.StringIO()): R.importer(d, v)
        except BaseException as e: r['erreurs'].append('import : ' + repr(e)[:300])
        res[d] = r
    return res


ENV_INITIAL = {k: os.environ.get(k) for k in ('PYTHONPATH',)}


class Resultat(unittest.TextTestResult):
    """v4 : chaque test part de l'environnement initial. Un test qui importe le moteur des raccourcis d'un espace d'essai modifie
    PYTHONPATH (le moteur le règle pour ses sous-processus) ; en v3, les tests suivants lançaient leurs sous-processus avec les outils de
    cet espace d'essai (ImportError « cc_lib_v2.py introuvable », trouvé le 16 oct. 2026)."""
    def startTest(self, test):
        for k, v in ENV_INITIAL.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v
        super().startTest(test)


def message_echec(trace, limite=1200):
    """v4 : message lisible d'un échec — la ligne de l'exception (AssertionError…) et les lignes qui la suivent (différence de
    chaînes ou de listes), bornées ; en v3, la seule dernière ligne (« ?   ^ ») ne disait rien."""
    L = (trace or '').strip().splitlines()
    i = next((k for k in range(len(L) - 1, -1, -1) if re.match(r'^[A-Za-z_][\w.]*(Error|Exception|Exit|Interrupt)\b', L[k])), None)
    if i is None: return '\n'.join(L[-8:])[:limite]
    return '\n'.join(L[i:i + 12])[:limite]


def ignores_lisibles(skipped):
    """v4 : [(test, raison)] des tests ignorés, pour qu'aucun ne passe pour réussi."""
    return [dict(test=str(t), raison=str(r)[:200]) for t, r in skipped]


def unitaires(complet, seul, cible=None):
    L = unittest.TestLoader(); suite = unittest.TestSuite(); ignores = []
    if cible:                                                    # v4 : --test <module>[.<Classe>[.<méthode>]]
        try: suite.addTests(L.loadTestsFromName(cible))
        except BaseException as e: suite.addTest(unittest.FunctionTestCase(lambda e=e: (_ for _ in ()).throw(e), description=f'chargement {cible}'))
        flux = io.StringIO(); t0 = time.time()
        with contextlib.redirect_stdout(io.StringIO()):
            r = unittest.TextTestRunner(stream=flux, verbosity=2, resultclass=Resultat).run(suite)
        return r, time.time() - t0, ignores, flux.getvalue()
    for f in sorted(glob.glob(os.path.join(TESTS, 'test_*.py'))):
        nom = os.path.basename(f)[:-3]
        if seul and seul not in nom: continue
        try: m = importlib.import_module(nom)
        except BaseException as e:
            suite.addTest(unittest.FunctionTestCase(lambda e=e: (_ for _ in ()).throw(e), description=f'import {nom}')); continue
        if getattr(m, 'INTEGRATION', False) and not complet: ignores.append(nom); continue
        suite.addTests(L.loadTestsFromModule(m))
    flux = io.StringIO(); t0 = time.time()
    with contextlib.redirect_stdout(io.StringIO()):
        r = unittest.TextTestRunner(stream=flux, verbosity=2, resultclass=Resultat).run(suite)
    return r, time.time() - t0, ignores, flux.getvalue()


def outil_du_test(tid):
    m = re.search(r'test_([a-z_]+?)_v\d+', tid); return m.group(1) if m else 'divers'


def main():
    a = sys.argv[1:]; complet = '--complet' in a; seul = opt(a, '--outil'); cible = opt(a, '--test')
    R = moteur(); candidats(R, opt(a, '--candidat'))
    F = fumee(R, seul) if (seul or not cible) else {}; r, duree, ignores, detail = unitaires(complet, seul, cible)
    sautes = ignores_lisibles(r.skipped)
    echecs = [(str(t), e) for t, e in r.failures + r.errors]
    par = collections.defaultdict(lambda: dict(tests=0, echecs=0))
    for t, _ in echecs: par[outil_du_test(t)]['echecs'] += 1
    for nom, v in F.items(): par[nom].update(fumee='ok' if not v['erreurs'] else 'échec', version=v['version'])
    n_f = sum(1 for v in F.values() if v['erreurs'])
    rap = dict(date=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), complet=complet, candidat=opt(a, '--candidat'),
               fumee=dict(outils=len(F), echecs=n_f, details={k: v for k, v in F.items() if v['erreurs']}),
               unitaires=dict(lances=r.testsRun, echecs=len(echecs), ignores_integration=ignores, ignores=len(sautes), ignores_details=sautes, duree_s=round(duree, 2),
                              details=[dict(test=t, message=message_echec(e), trace=e.strip()[-4000:]) for t, e in echecs]),
               test=cible,
               par_outil=dict(par), verdict='conforme' if not echecs and not n_f else 'échec')
    d = os.path.join(TESTS, 'rapports'); os.makedirs(d, exist_ok=True); ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    k = 1
    while os.path.exists(os.path.join(d, f'rapport_tests_{ts}.json')): k += 1; ts = ts.split('_s')[0] + f'_s{k}'   # deux rapports dans la même seconde
    with open(os.path.join(d, f'rapport_tests_{ts}.json'), 'x', encoding='utf-8') as g: json.dump(rap, g, ensure_ascii=False, indent=1)
    md = [f"# Tests des outils — {rap['date']}", '', f"Verdict : **{rap['verdict']}**", '',
          f"- Fumée : {len(F)} outils, {n_f} échec(s)" + (' (non lancée : --test seul)' if cible and not seul else ''),
          f"- Unitaires : {r.testsRun} tests, {len(echecs)} échec(s), {len(sautes)} ignoré(s), {round(duree, 1)} s"
          + (f" ; intégration ignorée : {', '.join(ignores)} (--complet pour l'inclure)" if ignores else ''), '']
    md += [f"- **{k}** : {'; '.join(v['erreurs'])}" for k, v in F.items() if v['erreurs']]
    md += [f"- `{x['test']}` :\n  ```\n  " + x['message'].replace('\n', '\n  ') + "\n  ```" for x in rap['unitaires']['details']]
    md += [f"- ignoré : `{x['test']}` ({x['raison']})" for x in sautes]
    with open(os.path.join(d, f'rapport_tests_{ts}.md'), 'x', encoding='utf-8') as g: g.write('\n'.join(md) + '\n')
    try:
        from cc_lib_v5 import evenement
        evenement('tester_outils', 4, 'tests', dict(verdict=rap['verdict'], fumee_echecs=n_f, unitaires=r.testsRun, unitaires_echecs=len(echecs), ignores=len(sautes), complet=complet, candidat=rap['candidat'], test=cible))
    except Exception: pass
    print('\n'.join(md[2:6])); [print(x) for x in md[6:]]
    print(f'rapport : tests/rapports/rapport_tests_{ts}.json')
    sys.exit(0 if rap['verdict'] == 'conforme' else 1)


if __name__ == '__main__':
    main()
