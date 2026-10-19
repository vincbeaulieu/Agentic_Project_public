"""
OUTIL: balayer_termes
VERSION: 2
RESUME: Balayage déterministe, par lot, de dossiers et de fichiers à la recherche des termes d'un lexique (JSON externe, jamais écrit dans le code) : catégories de termes littéraux et d'expressions régulières, avec gravité « bloquant » ou « à revoir », sans casse ni accents par défaut, mots entiers ; lit le texte des fichiers, leurs noms et le XML des fichiers zip (docx, xlsx) ; exceptions déclarées dans le lexique. Sert à vérifier qu'aucun terme confidentiel ou hors périmètre ne reste dans une édition publique.
CATALOGUE CONSULTÉ : « recherche termes lexique lot fichiers balayer confidentiel » → detecter_noms (noms de personnes par empreintes, sans catégories ni expressions régulières), anonymiser (remplace des rôles) : aucun ne balaie un lexique de termes par catégories ; outil nouveau.
USAGE: python3 outils/balayer_termes.py <lexique.json> <chemin> [<chemin> …] [--exclure <regex de chemin>]… [--json <sortie.json>] [--md <sortie.md>] [--contexte N] [--acceptes <acceptes.json>] [--strict]
ENTREES: lexique JSON {"version", "categories": [{"id", "nom", "gravite": "bloquant"|"a_revoir", "termes": [...], "regex": [...], "casse": false, "mots_entiers": true, "exceptions": [regex du contexte]}], "proximite": [{"id", "nom", "gravite", "a": [regex], "b": [regex], "fenetre": N mots}], "exceptions": [{"regex", "motif"}]} ; dossiers ou fichiers à balayer ; facultatif (v2) : constats « à revoir » relus et acceptés, JSON [{"chemin": regex du chemin, "categorie": id ou « * », "terme": terme exact (sans casse ni accents), "motif": raison}] ; un constat bloquant ne s'accepte jamais (corriger le fichier ou le lexique)
SORTIES: constats (fichier, ligne, colonne, catégorie, gravité, terme, contexte) à l'écran, en JSON et en Markdown (fichiers neufs, mode x) ; code 0 si aucun constat bloquant, 1 sinon (avec --strict : 1 dès qu'un constat n'est pas accepté), 2 si l'appel est invalide ; événement dans le journal
CATEGORIE: controle
BANC: tests/test_balayer_termes_v2.py
REMPLACE: balayer_termes_v1 (aucune trace des constats « à revoir » déjà relus : chaque passage les remontait tous, et un résultat propre ne pouvait s'obtenir qu'en ajoutant des exceptions au lexique, qui vaut pour toutes les éditions ; v2 : fichier --acceptes propre à l'édition, avec un motif par acceptation, acceptations sans objet signalées, acceptation d'un constat bloquant refusée ; --strict exige que tout constat soit corrigé ou accepté) ; v1 : -
"""
import sys, os, re, json, zipfile, unicodedata
OUTIL, VERSION = 'balayer_termes', 2
TEXTE_ZIP = re.compile(r'\.(xml|rels|txt|md|csv|json)$')
def sans_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if not unicodedata.combining(c))
def compiler(lex):
    """Rend [(categorie, gravite, motif compilé, libellé, sur_texte_normalise)] et la liste des exceptions compilées."""
    R = []
    for c in lex.get('categories', []):
        casse, entiers = bool(c.get('casse', False)), c.get('mots_entiers', True) is not False
        fl = 0 if casse else re.I
        ex = [re.compile(x, re.I) for x in c.get('exceptions', [])]          # exceptions propres à la catégorie (contexte)
        for t in c.get('termes', []):
            tt = re.escape(t if casse else sans_accents(t))
            m = rf'(?<![^\W_]){tt}(?![^\W_])' if entiers else tt   # mot entier ; « _ » sépare (identifiants de code, noms de fichiers)
            R.append((c['id'], c.get('gravite', 'bloquant'), re.compile(m, fl), t, not casse, ex))
        for x in c.get('regex', []):
            R.append((c['id'], c.get('gravite', 'bloquant'), re.compile(x, 0 if casse else re.I), x, False, ex))
    for p in lex.get('proximite', []):                                        # a et b à moins de N mots l'un de l'autre
        n = int(p.get('fenetre', 5)); A = '(?:' + '|'.join(p['a']) + ')'; B = '(?:' + '|'.join(p['b']) + ')'
        mot = r'(?:\W+\w+){0,%d}?\W+' % max(0, n - 1)
        m = re.compile(rf'(?<![^\W_]){A}(?![^\W_]){mot}{B}(?![^\W_])|(?<![^\W_]){B}(?![^\W_]){mot}{A}(?![^\W_])', re.I)
        R.append((p['id'], p.get('gravite', 'a_revoir'), m, p.get('nom', p['id']), True, [re.compile(x, re.I) for x in p.get('exceptions', [])]))
    E = [(re.compile(e['regex']), e.get('motif', '')) for e in lex.get('exceptions', [])]
    return R, E
def textes(p):
    """(étiquette, texte) pour un fichier : nom du fichier, contenu texte, ou parties texte d'une archive zip."""
    yield ('[nom]', re.sub(r'[_.-]', ' ', os.path.basename(p)))   # séparateurs du nom de fichier lus comme des espaces
    if zipfile.is_zipfile(p):
        try:
            with zipfile.ZipFile(p) as z:
                for n in z.namelist():
                    if TEXTE_ZIP.search(n):
                        yield (n, re.sub(r'<[^>]+>', ' ', z.read(n).decode('utf-8', 'replace')) if n.endswith(('.xml', '.rels')) else z.read(n).decode('utf-8', 'replace'))
        except zipfile.BadZipFile: pass
        return
    try:
        with open(p, encoding='utf-8') as f: yield ('', f.read())
    except (UnicodeDecodeError, OSError): pass
def balayer(lex, chemins, exclure=(), contexte=50):
    R, E = compiler(lex); X = [re.compile(x) for x in exclure]; C = []; n = 0
    fichiers = []
    for ch in chemins:
        if os.path.isfile(ch): fichiers.append(ch)
        else:
            for b, ds, fs in os.walk(ch):
                ds.sort()
                for f in sorted(fs): fichiers.append(os.path.join(b, f))
    for p in fichiers:
        if any(x.search(p) for x in X): continue
        n += 1
        for partie, t in textes(p):
            tn = sans_accents(t)
            debuts = [0] + [i + 1 for i, ch in enumerate(t) if ch == '\n']
            for cat, grav, m, lib, norm, ex in R:
                for mm in m.finditer(tn if norm else t):
                    a, b = mm.start(), mm.end()
                    d0 = max(0, a - contexte); ctx = t[d0:b + contexte].replace('\n', ' ')
                    # une exception ne vaut que si sa correspondance recouvre le constat (pas seulement le voisinage)
                    if any(x.start() <= a - d0 < x.end() or x.start() < b - d0 <= x.end() for e in [e for e, _ in E] + ex for x in e.finditer(ctx)): continue
                    ligne = max(i for i, d in enumerate(debuts) if d <= a) + 1 if partie != '[nom]' else 0
                    C.append(dict(fichier=p, partie=partie, ligne=ligne, colonne=a - debuts[ligne - 1] + 1 if ligne else 0, categorie=cat, gravite=grav,
                                  terme=t[a:b], motif=lib, contexte=ctx))
    C.sort(key=lambda c: (c['fichier'], c['partie'], c['ligne'], c['colonne'], c['categorie']))
    return C, n
def lire_acceptes(f):
    """Acceptations relues : liste de {chemin, categorie, terme, motif} ; motif obligatoire."""
    A = json.load(open(f, encoding='utf-8'))
    if not isinstance(A, list): raise ValueError('acceptations : liste attendue')
    for i, x in enumerate(A):
        if not isinstance(x, dict) or not all(str(x.get(k, '')).strip() for k in ('chemin', 'categorie', 'terme', 'motif')):
            raise ValueError(f'acceptation n° {i + 1} incomplète : chemin, categorie, terme et motif sont exigés')
        re.compile(x['chemin'])
    return A
def appliquer_acceptes(C, A):
    """Marque les constats acceptés ; rend (restants, acceptés, refusés, acceptations sans objet)."""
    norm = lambda t: sans_accents(t).lower()
    reste, acc, ref, servi = [], [], [], set()
    for c in C:
        k = next((i for i, x in enumerate(A) if re.search(x['chemin'], c['fichier']) and x['categorie'] in ('*', c['categorie'])
                  and norm(x['terme']) == norm(c['terme'])), None)
        if k is None: reste.append(c); continue
        servi.add(k)
        if c['gravite'] == 'bloquant': ref.append(dict(c, refus='constat bloquant : une acceptation ne vaut pas correction')); reste.append(c)
        else: acc.append(dict(c, accepte=A[k]['motif']))
    return reste, acc, ref, [x for i, x in enumerate(A) if i not in servi]
def main(a):
    if len(a) < 2: print(__doc__.split('USAGE:')[1].split('ENTREES:')[0].strip()); return 2
    def opt(k, multi=False):
        v = []
        while k in a:
            i = a.index(k)
            if i + 1 >= len(a): raise SystemExit(f'appel invalide : {k} sans valeur')
            v.append(a[i + 1]); del a[i:i + 2]
        return v if multi else (v[-1] if v else None)
    strict = '--strict' in a
    while '--strict' in a: a.remove('--strict')
    try: exclure, fj, fm, ctx, fa = opt('--exclure', True), opt('--json'), opt('--md'), int(opt('--contexte') or 50), opt('--acceptes')
    except (SystemExit, ValueError) as e: print(e); return 2
    for f in (fj, fm):
        if f and os.path.exists(f): print('existe déjà :', f); return 2
    if len(a) < 2 or not os.path.isfile(a[0]): print('appel invalide : lexique et au moins un chemin sont exigés'); return 2
    lex = json.load(open(a[0], encoding='utf-8'))
    for ch in a[1:]:
        if not os.path.exists(ch): print('appel invalide : chemin introuvable :', ch); return 2
    A = []
    if fa:
        try: A = lire_acceptes(fa)
        except (OSError, ValueError, re.error) as e: print('appel invalide :', e); return 2
    C, n = balayer(lex, a[1:], exclure, ctx)
    C, acc, ref, sans = appliquer_acceptes(C, A)
    bl = [c for c in C if c['gravite'] == 'bloquant']
    par = {}
    for c in C: par.setdefault((c['categorie'], c['gravite']), set()).add(c['terme'])
    for c in C[:200]: print(f"{c['gravite'][:8]:8s} {c['categorie']:4s} {c['fichier']}{'#' + c['partie'] if c['partie'] else ''}:{c['ligne']}:{c['colonne']} « {c['terme']} » … {c['contexte']} …")
    print(f'{n} fichier(s) balayé(s) ; {len(C)} constat(s), dont {len(bl)} bloquant(s)')
    for (cat, g), ts in sorted(par.items()): print(f'  {cat} ({g}) : {len(ts)} terme(s) distinct(s) : {", ".join(sorted(ts)[:15])}')
    if fa:
        print(f'{len(acc)} constat(s) accepté(s) (« à revoir » relus) ; {len(ref)} acceptation(s) refusée(s) (bloquant) ; {len(sans)} acceptation(s) sans objet')
        for c in ref: print(f"  refusé : {c['fichier']}:{c['ligne']} « {c['terme']} » ({c['categorie']})")
        for x in sans: print(f"  sans objet : {x['chemin']} « {x['terme']} » ({x['categorie']})")
    if fj: json.dump(dict(lexique=a[0], chemins=a[1:], fichiers=n, constats=C, acceptes=acc, refuses=ref, acceptations_sans_objet=sans, strict=strict), open(fj, 'x', encoding='utf-8'), ensure_ascii=False, indent=1)
    if fm:
        L = [f'# Balayage de termes', '', f'Lexique : `{a[0]}` ; {n} fichier(s) ; {len(C)} constat(s), dont {len(bl)} bloquant(s)' + (f' ; {len(acc)} accepté(s), {len(sans)} acceptation(s) sans objet' if fa else '') + '.', '', '| Gravité | Cat. | Fichier | Ligne | Terme | Contexte |', '|---|---|---|---|---|---|']
        L += [f"| {c['gravite']} | {c['categorie']} | {c['fichier']}{'#' + c['partie'] if c['partie'] else ''} | {c['ligne']} | {c['terme']} | {c['contexte'].replace('|', '/')} |" for c in C]
        open(fm, 'x', encoding='utf-8').write('\n'.join(L) + '\n')
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '_compat')); sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
        from cc_lib_v4 import evenement
        evenement(OUTIL, VERSION, 'balayage', dict(fichiers=n, constats=len(C), bloquants=len(bl), acceptes=len(acc), strict=strict))
    except Exception: pass
    return 1 if bl or (strict and C) else 0
if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
