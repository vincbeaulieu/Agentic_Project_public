"""
OUTIL: entrainer_classifieur
VERSION: 1
RESUME: Développement des classifieurs de mes outils : traits déterministes (n-grammes hachés, traits de paire, embeddings en cache), régression softmax ou perceptron à une couche cachée, Adam, poids par qualité d'étiquette et par classe ; points de reprise portables (npz : paramètres, moments d'Adam, pas, époque, état du générateur, empreinte des données) pour reprendre n'importe où, du CPU (numpy) au GPU (torch, si présent) ; évaluation en validation croisée sur l'or seulement, seuil de confiance pour le routage (au-dessus : décision sans LLM ; en dessous : micro-tâche déléguée) ; adoption contre la meilleure base au banc.
USAGE: python3 entrainer_classifieur_v1.py entrainer <tache> --nom NOM [--epoques 60] [--cache 0] [--lr 0.05] [--l2 1e-4] [--lot 64] [--graine 7] [--ckpt-tous 10] [--peripherique auto|cpu|cuda] [--reprendre <ckpt.npz>] [--base <predictions_base.json>]
       python3 entrainer_classifieur_v1.py predire <dossier_modele> <taches.jsonl> <sortie_dossier>
ENTREES: entrainement/taches/<tache>_vN.json ; jeu consolidé (donnees_entrainement_v1.charger_jeu) ; entrainement/traits/<modele_embeddings>/vecteurs_*.json (facultatif)
SORTIES: entrainement/modeles/<tache>/<NOM>_vN/ : ckpt_eNNNNN.npz (points de reprise, jamais réécrits), modele.npz, config.json, metriques.json ; predictions_<NOM>_vN.json ; événement dans journal/
CATEGORIE: apprentissage
BANC: validation croisée sur l'or (dans metriques.json) ; comparaison avec --base
REMPLACE: classifieur_texte_v1 (Bayes naïf, non adopté : 0,50 sur les références)
"""
import sys, os, re, json, glob, math, hashlib, unicodedata, collections, datetime
import numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
from cc_lib_v1 import RACINE_CC, evenement
from donnees_entrainement_v1 import charger_jeu, E
DIM = 1 << 14
def opt(a, k, d=None): return a[a.index(k) + 1] if k in a else d


# ---------------- traits (déterministes)
def norm(t): return ''.join(c for c in unicodedata.normalize('NFKD', (t or '').lower()) if not unicodedata.combining(c))
def h(s): return int(hashlib.md5(s.encode()).hexdigest()[:8], 16) % DIM
def mots(t): return re.findall(r'[a-z0-9]+', re.sub(r'^(demande|a|b) : ', '', norm(t)))


def ngrammes(t, pre=''):
    m = mots(t); f = {'w:' + x for x in m} | {'b:' + x + '_' + y for x, y in zip(m, m[1:])}
    s = ' ' + ' '.join(m) + ' '; f |= {'c:' + s[i:i + n] for n in (3, 4, 5) for i in range(len(s) - n + 1)}
    if (t or '').strip().endswith('?'): f.add('x:question')
    v = np.zeros(DIM, np.float32)
    for x in f: v[h(pre + x)] = 1.0
    n = np.linalg.norm(v); return v / n if n else v


def paire(a, b):                                   # traits de comparaison A (phrase) / B (extrait)
    ma, mb = mots(a), set(mots(b)); sa = set(ma)
    ca = {norm(a)[i:i + 4] for i in range(len(norm(a)) - 3)}; cb = {norm(b)[i:i + 4] for i in range(len(norm(b)) - 3)}
    nums = set(re.findall(r'\d+(?:[,.]\d+)?', a)); refs = set(re.findall(r'\[(\d+)\]', a))
    f = [len(sa & mb) / max(1, len(sa)), len(ca & cb) / max(1, len(ca)),
         float(bool(nums - set(re.findall(r'\d+(?:[,.]\d+)?', b)))), float(bool(refs - set(re.findall(r'\[(\d+)\]', b)))),
         math.log1p(len(a)) / 8, math.log1p(len(b)) / 8]
    f += [float(f[0] > s) for s in (0.3, 0.5, 0.7, 0.9)] + [float(f[1] > s) for s in (0.3, 0.5, 0.7, 0.9)]
    return np.array(f, np.float32)


def vecteurs(modele):
    V = {}
    for f in sorted(glob.glob(os.path.join(E, 'traits', modele, 'vecteurs_*.json'))): V.update(json.load(open(f, encoding='utf-8')))
    return V


def traits(S, entree, V):
    parts = []
    for t in S['traits']:
        if t == 'ngrammes': parts += [ngrammes(entree[c], c + ':') for c in S['entree']]
        elif t == 'paire': parts.append(paire(entree['a'], entree['b']))
        elif t.startswith('embeddings:'):
            cles = [hashlib.sha256(entree[c].encode()).hexdigest()[:16] for c in S['entree']]
            vs = [np.array(V[k], np.float32) if k in V else None for k in cles]
            dim = next((len(v) for v in vs if v is not None), 768)
            vs = [v / (np.linalg.norm(v) or 1) if v is not None else np.zeros(dim, np.float32) for v in vs]
            parts += vs if len(vs) == 1 else [np.array([float(vs[0] @ vs[1])], np.float32), vs[0] * vs[1], np.abs(vs[0] - vs[1])]
    return np.concatenate(parts)


# ---------------- moteurs de calcul (même calcul, même point de reprise)
class Numpy:
    nom = 'cpu-numpy'
    def t(self, x): return np.asarray(x, np.float32)
    def n(self, x): return np.asarray(x)
    relu = staticmethod(lambda x: np.maximum(x, 0)); exp = staticmethod(np.exp); sqrt = staticmethod(np.sqrt)
    def rmax(self, z): return z.max(axis=1, keepdims=True)


class Torch:
    def __init__(self, dev):
        import torch; self.T = torch; self.dev = dev; self.nom = 'torch-' + dev
        torch.use_deterministic_algorithms(True, warn_only=True)
    def t(self, x): return self.T.as_tensor(np.asarray(x, np.float32), device=self.dev)
    def n(self, x): return x.detach().cpu().numpy()
    def relu(self, x): return self.T.clamp(x, min=0)
    def exp(self, x): return self.T.exp(x)
    def sqrt(self, x): return self.T.sqrt(x)
    def rmax(self, z): return z.max(dim=1, keepdim=True).values


def moteur(choix):
    if choix in ('auto', 'cuda'):
        try:
            import torch
            if torch.cuda.is_available(): return Torch('cuda')
            if choix == 'cuda': raise SystemExit('cuda demandé mais indisponible')
        except ImportError:
            if choix == 'cuda': raise SystemExit('torch absent : cuda indisponible')
    return Numpy()


def init(d, k, cache, rng):
    if cache: return {'W1': rng.normal(0, 1 / math.sqrt(d), (d, cache)).astype(np.float32), 'b1': np.zeros(cache, np.float32),
                      'W2': rng.normal(0, 1 / math.sqrt(cache), (cache, k)).astype(np.float32), 'b2': np.zeros(k, np.float32)}
    return {'W': np.zeros((d, k), np.float32), 'b': np.zeros(k, np.float32)}


def proba(M, P, X):
    if 'W1' in P: Hh = M.relu(X @ P['W1'] + P['b1']); Z = Hh @ P['W2'] + P['b2']
    else: Hh = None; Z = X @ P['W'] + P['b']
    Z = M.exp(Z - M.rmax(Z)); return Z / Z.sum(1, keepdims=True) if isinstance(Z, np.ndarray) else Z / Z.sum(dim=1, keepdim=True), Hh


def gradients(M, P, X, Y, w, l2):
    Pr, Hh = proba(M, P, X); G = (Pr - Y) * (w / w.sum())[:, None]
    if 'W1' in P:
        g = {'W2': Hh.T @ G + l2 * P['W2'], 'b2': G.sum(0)}; dH = (G @ P['W2'].T) * (Hh > 0)
        g.update(W1=X.T @ dH + l2 * P['W1'], b1=dH.sum(0)); return g
    return {'W': X.T @ G + l2 * P['W'], 'b': G.sum(0)}


def sauver(chemin, P, Mo, Ve, pas, epoque, rng, config, empreinte, M):
    arr = {f'p:{k}': M.n(v) for k, v in P.items()} | {f'm:{k}': M.n(v) for k, v in Mo.items()} | {f'v:{k}': M.n(v) for k, v in Ve.items()}
    with open(chemin, 'xb') as f:
        np.savez(f, **arr, pas=np.array(pas), epoque=np.array(epoque), rng=np.array(json.dumps(rng.bit_generator.state)),
                 config=np.array(json.dumps(config, sort_keys=True)), empreinte=np.array(empreinte))


def charger_ckpt(chemin):
    z = np.load(chemin, allow_pickle=False)
    g = lambda p: {k[2:]: z[k] for k in z.files if k.startswith(p)}
    rng = np.random.default_rng(); rng.bit_generator.state = json.loads(str(z['rng']))
    return g('p:'), g('m:'), g('v:'), int(z['pas']), int(z['epoque']), rng, json.loads(str(z['config'])), str(z['empreinte'])


def apprendre(X, Y, w, cfg, M, dossier=None, reprise=None, empreinte=''):
    """Adam sur mini-lots ; ordre des lots tiré par le générateur numpy (identique sur tous les moteurs)."""
    if reprise:
        P, Mo, Ve, pas, ep0, rng, c0, e0 = charger_ckpt(reprise)
        if e0 != empreinte: raise SystemExit('reprise refusée : les données ont changé depuis ce point de reprise')
    else:
        rng = np.random.default_rng(cfg['graine']); P = init(X.shape[1], Y.shape[1], cfg['cache'], rng)
        Mo = {k: np.zeros_like(v) for k, v in P.items()}; Ve = {k: np.zeros_like(v) for k, v in P.items()}; pas, ep0 = 0, 0
    P, Mo, Ve = ({k: M.t(v) for k, v in D.items()} for D in (P, Mo, Ve))
    Xt, Yt, wt = M.t(X), M.t(Y), M.t(w); b1, b2, eps = 0.9, 0.999, 1e-8
    for ep in range(ep0, cfg['epoques']):
        perm = rng.permutation(len(X))
        for i in range(0, len(X), cfg['lot']):
            j = perm[i:i + cfg['lot']]; jt = j if isinstance(Xt, np.ndarray) else M.T.as_tensor(j, device=M.dev)
            g = gradients(M, P, Xt[jt], Yt[jt], wt[jt], cfg['l2']); pas += 1
            for k in P:
                Mo[k] = b1 * Mo[k] + (1 - b1) * g[k]; Ve[k] = b2 * Ve[k] + (1 - b2) * g[k] * g[k]
                P[k] = P[k] - cfg['lr'] * (Mo[k] / (1 - b1 ** pas)) / (M.sqrt(Ve[k] / (1 - b2 ** pas)) + eps)
        if dossier and ((ep + 1) % cfg['ckpt_tous'] == 0 or ep + 1 == cfg['epoques']):
            sauver(os.path.join(dossier, f'ckpt_e{ep + 1:05d}.npz'), P, Mo, Ve, pas, ep + 1, rng, cfg, empreinte, M)
    return {k: M.n(v) for k, v in P.items()}


def mesures(paires, classes):
    ok = sum(p == r for p, r in paires); f1 = []
    for c in classes:
        tp = sum(p == c and r == c for p, r in paires); fp = sum(p == c and r != c for p, r in paires); fn = sum(p != c and r == c for p, r in paires)
        if tp + fp + fn: f1.append(2 * tp / (2 * tp + fp + fn))
    return dict(n=len(paires), exactitude=round(ok / len(paires), 3) if paires else None, f1_macro=round(sum(f1) / len(f1), 3) if f1 else None)


def matrices(S, J, V):
    X = np.stack([traits(S, x['entree'], V) for x in J]); C = S['classes']
    Y = np.zeros((len(J), len(C)), np.float32); Y[np.arange(len(J)), [C.index(x['etiquette']) for x in J]] = 1
    cpt = Y.sum(0); cw = (len(J) / (len(C) * np.maximum(cpt, 1)))           # poids de classe équilibrés
    w = np.array([x['poids'] for x in J], np.float32) * cw[Y.argmax(1)]
    return X, Y, w.astype(np.float32)


def entrainer(a):
    tache, nom = a[0], opt(a, '--nom'); S, J = charger_jeu(tache)
    cfg = dict(epoques=int(opt(a, '--epoques', 60)), cache=int(opt(a, '--cache', 0)), lr=float(opt(a, '--lr', 0.05)), l2=float(opt(a, '--l2', 1e-4)),
               lot=int(opt(a, '--lot', 64)), graine=int(opt(a, '--graine', 7)), ckpt_tous=int(opt(a, '--ckpt-tous', 10)), traits=S['traits'], classes=S['classes'])
    M = moteur(opt(a, '--peripherique', 'auto')); V = {}
    for t in S['traits']:
        if t.startswith('embeddings:'): V.update(vecteurs(t.split(':', 1)[1]))
    X, Y, w = matrices(S, J, V); C = S['classes']
    empreinte = hashlib.sha256(json.dumps([[x['uid'], x['etiquette'], x['poids']] for x in J]).encode()).hexdigest()[:16]
    base = os.path.join(E, 'modeles', tache); os.makedirs(base, exist_ok=True)
    n = 1 + max([int(m.group(1)) for d in os.listdir(base) for m in [re.match(re.escape(nom) + r'_v(\d+)$', d)] if m] or [0])
    dossier = os.path.join(base, f'{nom}_v{n}'); os.makedirs(dossier)
    # validation croisée sur l'or : chaque exemple d'or est prédit par un modèle qui ne l'a pas vu
    ior = [i for i, x in enumerate(J) if x['qualite'] == 'or']; k = min(5, len(ior)); cv = []
    for f in range(k):
        test = [i for i in ior if int(J[i]['uid'], 16) % k == f]
        if not test: continue
        tr = np.array([i for i in range(len(J)) if i not in set(test)])
        P = apprendre(X[tr], Y[tr], w[tr], cfg, Numpy())
        Pr, _ = proba(Numpy(), P, X[test])
        cv += [(C[int(p.argmax())], J[i]['etiquette'], float(p.max()), J[i]['origines']) for p, i in zip(Pr, test)]
    m = mesures([(p, r) for p, r, _, _ in cv], C)
    cible = S.get('routage', {}).get('precision_cible', 0.95); seuil = 1.01
    for s in sorted({c for _, _, c, _ in cv}):
        sel = [(p, r) for p, r, c, _ in cv if c >= s]
        if sel and sum(p == r for p, r in sel) / len(sel) >= cible: seuil = s; break
    couv = round(sum(1 for _, _, c, _ in cv if c >= seuil) / len(cv), 3) if cv else 0
    comp = None
    if opt(a, '--base'):
        B = json.load(open(opt(a, '--base'), encoding='utf-8'))
        pb = [(B[o[0]], r) for _, r, _, o in cv if o and o[0] in B]
        comp = dict(base=os.path.basename(opt(a, '--base')), sur_or=mesures(pb, C), modele_sur_memes=mesures([(p, r) for p, r, _, o in cv if o and o[0] in B], C))
    # modèle final : tout le jeu, avec points de reprise
    P = apprendre(X, Y, w, cfg, M, dossier=dossier, reprise=opt(a, '--reprendre'), empreinte=empreinte)
    with open(os.path.join(dossier, 'modele.npz'), 'xb') as f: np.savez(f, **{f'p:{kk}': v for kk, v in P.items()})
    config = dict(tache=tache, nom=nom, version=n, moteur=M.nom, empreinte_donnees=empreinte, exemples=len(J),
                  par_qualite=dict(collections.Counter(x['qualite'] for x in J)), **cfg)
    met = dict(validation_croisee_or=m, seuil_routage=seuil, couverture_auto=couv, precision_cible=cible, comparaison=comp,
               erreurs_or=[f'{o[0] if o else "?"}: {p}≠{r} ({c:.2f})' for p, r, c, o in cv if p != r])
    for nomf, obj in (('config.json', config), ('metriques.json', met)):
        with open(os.path.join(dossier, nomf), 'x', encoding='utf-8') as f: json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=True)
    evenement('entrainer_classifieur', 1, 'entrainement', dict(tache=tache, modele=f'{nom}_v{n}', moteur=M.nom, exemples=len(J), cv_or=m, seuil=seuil, couverture=couv))
    print(f'{os.path.relpath(dossier, RACINE_CC)} ; {len(J)} exemples ({config["par_qualite"]}) ; moteur {M.nom}')
    print('validation croisée sur l’or :', m, '; seuil de routage', seuil, '; couverture sans LLM', couv)
    if comp: print('comparaison sur les mêmes exemples d’or :', comp)


def predire(a):
    d, ft, out = a[0], a[1], a[2]
    cfg = json.load(open(os.path.join(d, 'config.json'), encoding='utf-8')); met = json.load(open(os.path.join(d, 'metriques.json'), encoding='utf-8'))
    z = np.load(os.path.join(d, 'modele.npz')); P = {k[2:]: z[k] for k in z.files}
    from donnees_entrainement_v1 import spec
    S = spec(cfg['tache']); V = {}
    for t in S['traits']:
        if t.startswith('embeddings:'): V.update(vecteurs(t.split(':', 1)[1]))
    T = [json.loads(l) for l in open(ft, encoding='utf-8') if l.strip()]; R = {}
    for x in T:
        if not all(c in x for c in S['entree']): continue
        p, _ = proba(Numpy(), P, traits(S, {c: x[c] for c in S['entree']}, V)[None, :]); p = p[0]
        R[x['id']] = dict(etiquette=cfg['classes'][int(p.argmax())], confiance=round(float(p.max()), 4),
                          decision='auto' if p.max() >= met['seuil_routage'] else 'deleguer')
    os.makedirs(out, exist_ok=True); f = os.path.join(out, f"predictions_{cfg['nom']}_v{cfg['version']}.json")
    with open(f, 'x', encoding='utf-8') as g: json.dump(R, g, ensure_ascii=False, indent=0, sort_keys=True)
    print(f, len(R), 'prédictions ;', dict(collections.Counter(r['decision'] for r in R.values())))


if __name__ == '__main__':
    {'entrainer': entrainer, 'predire': predire}[sys.argv[1]](sys.argv[2:])
