"""
OUTIL: tester_outils
VERSION: 2
RESUME: Tests automatiques de tous les outils (bonnes pratiques) : tests de fumée de chaque version courante (compilation, import par le raccourci, en-tête complet), tests unitaires (tests/test_*.py, unittest de la bibliothèque standard), tests d'intégration en option (bancs) ; essai d'une version candidate avant son adoption (--candidat outil=N) ; rapport JSON et Markdown par outil, événement au journal ; code de sortie non nul au moindre échec.
USAGE: python3 outils/tester_outils.py [--complet] [--outil NOM] [--candidat NOM=N[,NOM2=M]]
ENTREES: outils/<outil>/<outil>_vN.py (versions courantes) ; tests/test_*.py ; raccourcis (outils/_raccourci_vN.py)
SORTIES: tests/rapports/rapport_tests_<ts>.json et .md ; événement dans journal/ ; code 0 si tout passe
CATEGORIE: qualite
BANC: tests/test_*.py (il se teste en lançant toute la suite)
REMPLACE: tester_outils_v1 (compilation par compile() en mémoire : py_compile vers /dev/null échouait partout)
"""
import sys, os, re, json, glob, time, datetime, traceback, unittest, importlib, py_compile, io, contextlib, collections
H = os.path.dirname(os.path.abspath(__file__)); O = H
while os.path.basename(O) != 'outils' and os.path.dirname(O) != O: O = os.path.dirname(O)
OUTILS = O; RACINE_CC = os.path.dirname(O); TESTS = os.path.join(RACINE_CC, 'tests')
for p in (TESTS, os.path.join(OUTILS, '_compat'), OUTILS):
    if p not in sys.path: sys.path.insert(0, p)
os.environ.setdefault('CC_BANC', 'tests')
CHAMPS = ('OUTIL', 'VERSION', 'RESUME', 'USAGE', 'ENTREES', 'SORTIES', 'CATEGORIE', 'BANC', 'REMPLACE')
def opt(a, k, d=None): return a[a.index(k) + 1] if k in a else d


def moteur():
    c = sorted((int(m.group(1)), f) for f in os.listdir(OUTILS) for m in [re.match(r'^_raccourci_v(\d+)\.py$', f)] if m)
    return importlib.import_module(f'_raccourci_v{c[-1][0]}')


def candidats(R, cand):
    """Remplace, le temps des tests, la version courante de certains outils par une version candidate."""
    if not cand: return
    C = dict(x.split('=') for x in cand.split(',')); orig = R.courante
    def courante(outil, ext='py'):
        if outil in C and ext == 'py': v = int(C[outil]); return v, R.versions(outil)[v][0]
        return orig(outil, ext)
    R.courante = courante


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


class Resultat(unittest.TextTestResult):
    pass


def unitaires(complet, seul):
    L = unittest.TestLoader(); suite = unittest.TestSuite(); ignores = []
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
        r = unittest.TextTestRunner(stream=flux, verbosity=2).run(suite)
    return r, time.time() - t0, ignores, flux.getvalue()


def outil_du_test(tid):
    m = re.search(r'test_([a-z_]+?)_v\d+', tid); return m.group(1) if m else 'divers'


def main():
    a = sys.argv[1:]; complet = '--complet' in a; seul = opt(a, '--outil')
    R = moteur(); candidats(R, opt(a, '--candidat'))
    F = fumee(R, seul); r, duree, ignores, detail = unitaires(complet, seul)
    echecs = [(str(t), e) for t, e in r.failures + r.errors]
    par = collections.defaultdict(lambda: dict(tests=0, echecs=0))
    for t, _ in echecs: par[outil_du_test(t)]['echecs'] += 1
    for nom, v in F.items(): par[nom].update(fumee='ok' if not v['erreurs'] else 'échec', version=v['version'])
    n_f = sum(1 for v in F.values() if v['erreurs'])
    rap = dict(date=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), complet=complet, candidat=opt(a, '--candidat'),
               fumee=dict(outils=len(F), echecs=n_f, details={k: v for k, v in F.items() if v['erreurs']}),
               unitaires=dict(lances=r.testsRun, echecs=len(echecs), ignores_integration=ignores, duree_s=round(duree, 2),
                              details=[dict(test=t, message=e.strip().splitlines()[-1][:300]) for t, e in echecs]),
               par_outil=dict(par), verdict='conforme' if not echecs and not n_f else 'échec')
    d = os.path.join(TESTS, 'rapports'); os.makedirs(d, exist_ok=True); ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    with open(os.path.join(d, f'rapport_tests_{ts}.json'), 'x', encoding='utf-8') as g: json.dump(rap, g, ensure_ascii=False, indent=1)
    md = [f"# Tests des outils — {rap['date']}", '', f"Verdict : **{rap['verdict']}**", '',
          f"- Fumée : {len(F)} outils, {n_f} échec(s)", f"- Unitaires : {r.testsRun} tests, {len(echecs)} échec(s), {round(duree, 1)} s"
          + (f" ; intégration ignorée : {', '.join(ignores)} (--complet pour l'inclure)" if ignores else ''), '']
    md += [f"- **{k}** : {'; '.join(v['erreurs'])}" for k, v in F.items() if v['erreurs']] + [f"- `{x['test']}` : {x['message']}" for x in rap['unitaires']['details']]
    with open(os.path.join(d, f'rapport_tests_{ts}.md'), 'x', encoding='utf-8') as g: g.write('\n'.join(md) + '\n')
    try:
        from cc_lib_v1 import evenement
        evenement('tester_outils', 2, 'tests', dict(verdict=rap['verdict'], fumee_echecs=n_f, unitaires=r.testsRun, unitaires_echecs=len(echecs), complet=complet, candidat=rap['candidat']))
    except Exception: pass
    print('\n'.join(md[2:6])); [print(x) for x in md[6:]]
    print(f'rapport : tests/rapports/rapport_tests_{ts}.json')
    sys.exit(0 if rap['verdict'] == 'conforme' else 1)


if __name__ == '__main__':
    main()
