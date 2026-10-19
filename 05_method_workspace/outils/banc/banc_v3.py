"""
OUTIL: banc
VERSION: 3
RESUME: Banc d'essai déterministe des outils : exécute une ou plusieurs versions d'un outil sur les cas fixes de bancs/<outil>/cas_vN.py et mesure la performance au sens large (qualité, alignement, rapidité, ressources utilisées et consultées, compacité, déterminisme, absence de LLM) ; compare deux versions et dit si la nouvelle peut être adoptée.
USAGE: python3 banc_v3.py <outil> <version>[,<version2>…]   |   python3 banc_v1.py <outil> --comparer <ancienne> <nouvelle>
ENTREES: outils/<outil>_v<N>.py ; bancs/<outil>/cas_v<N>.py (dernière version : CAS = [dict(nom, construire(base)->dossier, commande(outil, dossier, json)->argv, attendu=[(regle, chemin)])])
SORTIES: bancs/<outil>/resultats/resultat_<outil>_v<N>_<ts>.json ; tableau comparatif ; événement dans journal/
CATEGORIE: evaluation
BANC: tests/test_banc_v3.py
REMPLACE: banc_v2 (noms de dossiers de l'espace écrits en dur, remplacés par le registre central cc_lib_v4.chemin) ; v2 : banc_v1 (versions cherchées aussi dans outils/archive/<outil>/ : comparaison possible avec une version archivée)
"""
import sys, os, re, json, time, shutil, subprocess, importlib.util, datetime, hashlib, statistics
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
from cc_lib_v2 import chemin_outil
from cc_lib_v1 import RACINE_CC, derniere_version
from cc_lib_v4 import chemin, evenement     # dossiers de l'espace et journal désignés par le registre central
CC = RACINE_CC                              # racine de l'espace, comme avant

MESURE = r'''
import sys, runpy, resource, json, os
out = sys.argv[1]; sys.argv = sys.argv[2:]
code = 0
try:
    runpy.run_path(sys.argv[0], run_name="__main__")
except SystemExit as e:
    code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
io = {}
try:
    for l in open("/proc/self/io"):
        k, v = l.split(":"); io[k.strip()] = int(v)
except Exception: pass
ru = resource.getrusage(resource.RUSAGE_SELF)
json.dump(dict(code=code, rchar=io.get("rchar"), read_bytes=io.get("read_bytes"), maxrss_ko=ru.ru_maxrss, cpu_s=ru.ru_utime + ru.ru_stime), open(out, "w"))
'''
LLM = re.compile(r'\b(import anthropic|from anthropic|openai|claude\s+-p|api\.anthropic\.com)\b')


def charger_cas(outil):
    d = chemin('bancs', outil, racine=CC)
    f = derniere_version(d, 'cas', 'py')
    if not f: raise SystemExit(f'aucun fichier de cas : {d}/cas_vN.py')
    spec = importlib.util.spec_from_file_location('cas', f); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return f, m.CAS


def executer(outil, version, cas, rep, essai):
    tool = chemin_outil(outil, int(version))
    if not os.path.exists(tool): raise SystemExit('outil absent : ' + tool)
    dossier = os.path.join(rep, f'{cas["nom"]}_v{version}_{essai}'); os.makedirs(dossier)
    wd = cas['construire'](dossier) or dossier
    jout = os.path.join(rep, f'{cas["nom"]}_v{version}_{essai}_sortie.json')
    mfile = os.path.join(rep, f'{cas["nom"]}_v{version}_{essai}_mesure.json')
    runner = os.path.join(rep, '_mesure.py')
    if not os.path.exists(runner): open(runner, 'w').write(MESURE)
    argv = cas['commande'](tool, wd, jout)
    t0 = time.time()
    r = subprocess.run([sys.executable, runner, mfile] + argv, capture_output=True, text=True, env=dict(os.environ, CC_BANC='1'))
    duree = time.time() - t0
    m = json.load(open(mfile)) if os.path.exists(mfile) else {}
    sortie = json.load(open(jout)) if os.path.exists(jout) else {'constats': []}
    obtenu = {(c['regle'], c.get('chemin') or c.get('paraId') or 'global') for c in sortie.get('constats', [])}
    brut = json.dumps(sortie, sort_keys=True, ensure_ascii=False)
    return dict(obtenu=obtenu, duree_s=duree, mesure=m, hash=hashlib.sha256(brut.encode()).hexdigest()[:16], taille_sortie=len(brut),
                stderr=r.stderr[-500:])


def evaluer_version(outil, version):
    fcas, CAS = charger_cas(outil)
    ts = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M%S')
    rep = chemin('bancs', outil, '_execution', f'{ts}_v{version}', racine=CC); os.makedirs(rep)
    tool = chemin_outil(outil, int(version))
    src = open(tool, encoding='utf-8').read()
    lignes = [l for l in src.splitlines() if l.strip() and not l.strip().startswith('#')]
    par_cas = []; tp = fp = fn = 0; exacts = 0; durees = []; cpu = []; rss = []; lus = []; det = True
    for cas in CAS:
        a = executer(outil, version, cas, rep, 1); b = executer(outil, version, cas, rep, 2)
        att = {tuple(x) for x in cas['attendu']}
        o = a['obtenu']
        tp_, fp_, fn_ = len(o & att), len(o - att), len(att - o)
        tp += tp_; fp += fp_; fn += fn_; exacts += (fp_ == 0 and fn_ == 0)
        det = det and a['hash'] == b['hash']
        durees += [a['duree_s'], b['duree_s']]; cpu.append(a['mesure'].get('cpu_s') or 0); rss.append(a['mesure'].get('maxrss_ko') or 0); lus.append(a['mesure'].get('rchar') or 0)
        par_cas.append(dict(cas=cas['nom'], vrais_positifs=tp_, faux_positifs=sorted(o - att), faux_negatifs=sorted(att - o),
                            deterministe=a['hash'] == b['hash'], duree_s=round(a['duree_s'], 3), stderr=a['stderr'] if fp_ or fn_ else ''))
    prec = tp / (tp + fp) if tp + fp else 1.0; rapp = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * prec * rapp / (prec + rapp) if prec + rapp else 0.0
    res = dict(outil=outil, version=version, fichier_cas=os.path.basename(fcas), date=ts,
               qualite=dict(precision=round(prec, 4), rappel=round(rapp, 4), f1=round(f1, 4)),
               alignement=dict(cas_exacts=exacts, cas_total=len(CAS), taux=round(exacts / len(CAS), 4)),
               rapidite=dict(duree_mediane_s=round(statistics.median(durees), 3)),
               ressources=dict(cpu_median_s=round(statistics.median(cpu), 3), rss_max_ko=max(rss)),
               consultees=dict(octets_lus_median=int(statistics.median(lus))),
               compacite=dict(lignes_code=len(lignes), octets_code=len(src.encode())),
               automatisation=dict(deterministe=det, sans_llm=not LLM.search(src)),
               cas=par_cas)
    rdir = chemin('bancs', outil, 'resultats', racine=CC); os.makedirs(rdir, exist_ok=True)
    with open(os.path.join(rdir, f'resultat_{outil}_v{version}_{ts}.json'), 'x', encoding='utf-8') as f: json.dump(res, f, ensure_ascii=False, indent=1)
    evenement('banc', 3, 'banc', dict(outil=outil, version=version, f1=res['qualite']['f1'], alignement=res['alignement']['taux'],
                                      deterministe=det, duree=res['rapidite']['duree_mediane_s']))
    shutil.rmtree(rep, ignore_errors=True) if f1 == 1.0 and det else None
    return res


def dernier_resultat(outil, version):
    rdir = chemin('bancs', outil, 'resultats', racine=CC)
    c = sorted(f for f in os.listdir(rdir) if f.startswith(f'resultat_{outil}_v{version}_')) if os.path.isdir(rdir) else []
    return json.load(open(os.path.join(rdir, c[-1]), encoding='utf-8')) if c else None


def resume(r):
    return (f"v{r['version']} : F1 {r['qualite']['f1']:.3f} (P {r['qualite']['precision']:.3f}, R {r['qualite']['rappel']:.3f}) · "
            f"cas exacts {r['alignement']['cas_exacts']}/{r['alignement']['cas_total']} · {r['rapidite']['duree_mediane_s']} s · "
            f"CPU {r['ressources']['cpu_median_s']} s · RSS {r['ressources']['rss_max_ko']} Ko · lus {r['consultees']['octets_lus_median']} o · "
            f"{r['compacite']['lignes_code']} lignes · déterministe {r['automatisation']['deterministe']} · sans LLM {r['automatisation']['sans_llm']}")


def comparer(outil, va, vb):
    A = evaluer_version(outil, va)   # mêmes cas (dernier cas_vN.py) pour les deux versions
    B = evaluer_version(outil, vb)
    print('ancienne', resume(A)); print('nouvelle', resume(B))
    ok = (B['qualite']['f1'] >= A['qualite']['f1'] and B['alignement']['taux'] >= A['alignement']['taux']
          and B['automatisation']['deterministe'] and B['automatisation']['sans_llm'])
    print('ADOPTER v%s' % vb if ok else 'NE PAS ADOPTER v%s (qualité, alignement ou déterminisme en baisse)' % vb)
    evenement('banc', 3, 'comparaison', dict(outil=outil, ancienne=va, nouvelle=vb, adopter=ok))
    return 0 if ok else 1


if __name__ == '__main__':
    outil = sys.argv[1]
    if '--comparer' in sys.argv:
        i = sys.argv.index('--comparer'); sys.exit(comparer(outil, sys.argv[i + 1], sys.argv[i + 2]))
    for v in sys.argv[2].split(','):
        r = evaluer_version(outil, v); print(resume(r))
        for c in r['cas']:
            if c['faux_positifs'] or c['faux_negatifs']: print('   ', c['cas'], 'FP', c['faux_positifs'], 'FN', c['faux_negatifs'], c['stderr'][:200])
