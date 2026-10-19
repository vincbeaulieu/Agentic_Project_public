"""
OUTIL: classifieur_texte
VERSION: 1
RESUME: Classifieur de textes courts déterministe et sans LLM, entraîné sur des étiquettes produites par un modèle local (supervision faible) et contrôlé sur des références : Bayes naïf multinomial sur n-grammes de mots (1-2) et de caractères (3-5) hachés, lissage de Laplace ; modèle figé en JSON (empreinte) ; prédiction, validation croisée « un contre tous » contre les étiquettes du modèle local, exactitude contre les références.
USAGE: python3 classifieur_texte_v1.py entrainer <etiquettes.json> <taches.jsonl> <sortie_dossier> --nom NOM [--champ texte] [--exclure references.json] [--genres fil_relecteur,segment]
       python3 classifieur_texte_v1.py predire <modele.json> <taches.jsonl> <sortie_dossier> [--champ texte]
       python3 classifieur_texte_v1.py evaluer <modele.json> <taches.jsonl> <references.json> [--champ texte]
ENTREES: étiquettes {id: {final}} ou {id: valeur} ; tâches JSONL (id, champ texte, genre) ; références {references: {id: valeur}}
SORTIES: <NOM>_vN.json (modèle : classes, a priori, comptes par n-gramme haché), predictions_<NOM>_vN.json ; mesures (exactitude, F1 macro, accord en validation croisée) ; événement dans journal/
CATEGORIE: classification
BANC: -
REMPLACE: -
"""
import sys, os, re, json, math, hashlib, unicodedata, collections
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
from cc_lib_v1 import evenement, ecrire_versionne
DIM = 1 << 15
def opt(a, k, d=None): return a[a.index(k) + 1] if k in a else d
def norm(t): return ''.join(c for c in unicodedata.normalize('NFKD', (t or '').lower()) if not unicodedata.combining(c))
def h(s): return int(hashlib.md5(s.encode()).hexdigest()[:8], 16) % DIM


def traits(t):
    t = re.sub(r'^demande : ', '', norm(t)); m = re.findall(r"[a-z0-9]+", t); f = set()
    f.update('w:' + x for x in m); f.update('b:' + a + '_' + b for a, b in zip(m, m[1:]))
    s = ' ' + ' '.join(m) + ' '
    for n in (3, 4, 5): f.update('c:' + s[i:i + n] for i in range(len(s) - n + 1))
    if (t or '').strip().endswith('?'): f.add('x:finit_par_question')
    return sorted({h(x) for x in f})


def apprendre(ex):                                   # ex : [(traits, classe)]
    cl = sorted({c for _, c in ex}); cnt = {c: collections.Counter() for c in cl}; n = collections.Counter()
    for f, c in ex: n[c] += 1; cnt[c].update(f)
    tot = {c: sum(cnt[c].values()) for c in cl}
    return dict(classes=cl, n=dict(n), tot=tot, cnt={c: {str(k): v for k, v in sorted(cnt[c].items())} for c in cl}, dim=DIM)


def predire_un(M, f):
    N = sum(M['n'].values()); best = None
    for c in M['classes']:
        s = math.log(M['n'][c] / N); cc = M['cnt'][c]; den = M['tot'][c] + M['dim']
        s += sum(math.log((cc.get(str(k), 0) + 1) / den) for k in f)
        if best is None or s > best[0] + 1e-12: best = (s, c)
    return best[1]


def charger(f): return [json.loads(l) for l in open(f, encoding='utf-8') if l.strip()]
def etiq(v): return v['final'] if isinstance(v, dict) else v


def mesures(paires):
    ok = sum(1 for a, b in paires if a == b); cl = sorted({b for _, b in paires} | {a for a, _ in paires}); f1 = []
    for c in cl:
        tp = sum(1 for a, b in paires if a == c and b == c); fp = sum(1 for a, b in paires if a == c and b != c); fn = sum(1 for a, b in paires if a != c and b == c)
        if tp + fp + fn: f1.append(2 * tp / (2 * tp + fp + fn))
    return dict(n=len(paires), exactitude=round(ok / len(paires), 3) if paires else None, f1_macro=round(sum(f1) / len(f1), 3) if f1 else None)


def entrainer(a):
    E, T, out = json.load(open(a[0], encoding='utf-8')), charger(a[1]), a[2]
    nom, champ = opt(a, '--nom'), opt(a, '--champ', 'texte'); excl = set()
    if opt(a, '--exclure'): excl = set(json.load(open(opt(a, '--exclure'), encoding='utf-8')).get('references', {}))
    genres = set(opt(a, '--genres').split(',')) if opt(a, '--genres') else None
    ex = [(traits(x[champ]), etiq(E[x['id']]), x['id']) for x in T if x['id'] in E and x['id'] not in excl and (not genres or x.get('genre', 'segment') in genres)]
    cv = [(predire_un(apprendre([(f, c) for j, (f, c, _) in enumerate(ex) if j != i]), ex[i][0]), ex[i][1]) for i in range(len(ex))]
    M = apprendre([(f, c) for f, c, _ in ex]); M.update(nom=nom, champ=champ, exemples=len(ex), validation_croisee=mesures(cv))
    ch, _ = ecrire_versionne(out, nom, 'json', json.dumps(M, ensure_ascii=False, sort_keys=True))
    evenement('classifieur_texte', 1, 'entrainer', dict(nom=os.path.basename(ch), exemples=len(ex), validation_croisee=M['validation_croisee']))
    print(ch, len(ex), 'exemples ; accord en validation croisée avec les étiquettes :', M['validation_croisee'])


def predire(a):
    M, T, out = json.load(open(a[0], encoding='utf-8')), charger(a[1]), a[2]; champ = opt(a, '--champ', M.get('champ', 'texte'))
    P = {x['id']: predire_un(M, traits(x[champ])) for x in T}
    ch, _ = ecrire_versionne(out, 'predictions_' + M['nom'], 'json', json.dumps(P, ensure_ascii=False, sort_keys=True)); print(ch, len(P))


def evaluer(a):
    M, T, R = json.load(open(a[0], encoding='utf-8')), {x['id']: x for x in charger(a[1])}, json.load(open(a[2], encoding='utf-8'))['references']
    champ = opt(a, '--champ', M.get('champ', 'texte'))
    paires = [(predire_un(M, traits(T[i][champ])), r) for i, r in sorted(R.items()) if i in T]
    m = mesures(paires); evenement('classifieur_texte', 1, 'evaluer', dict(modele=M['nom'], **m))
    print(M['nom'], 'contre les références :', m, '; erreurs :', [f'{i}: {p}≠{r}' for (p, r), i in zip(paires, [i for i in sorted(R) if i in T]) if p != r])


if __name__ == '__main__':
    {'entrainer': entrainer, 'predire': predire, 'evaluer': evaluer}[sys.argv[1]](sys.argv[2:])
