"""
OUTIL: donnees_entrainement
VERSION: 1
RESUME: Répertoire d'entraînement des classifieurs (00_competences_claude/entrainement), alimenté au fil du travail : collecte d'exemples étiquetés avec leur provenance et leur qualité (or : jugement vérifié de l'utilisateur ou de Claude ; argent : modèle local + règles ; bronze : règle seule), en lots immuables (un fichier par collecte, jamais réécrit), sans doublon (empreinte de l'entrée et source) ; état par tâche ; jeu consolidé déterministe (l'or prime sur l'argent, l'argent sur le bronze ; l'utilisateur prime sur Claude).
USAGE: python3 donnees_entrainement_v1.py collecter <tache> --taches <microtaches.jsonl> --etiquettes <fichier.json> --qualite or|argent|bronze --source NOM --travail NOM [--champ-regle regle --regles R1,R2 --qualite-regle bronze]
       python3 donnees_entrainement_v1.py etat <tache>
       python3 donnees_entrainement_v1.py jeu <tache>            (affiche le résumé du jeu consolidé ; usage interne : charger_jeu)
ENTREES: entrainement/taches/<tache>_vN.json (spécification : champs d'entrée, classes, poids par qualité) ; tâches JSONL (id → entrée) ; étiquettes {id: valeur} ou {references: {id: valeur}} ou {id: {final, regle}}
SORTIES: entrainement/donnees/<tache>/lot_<AAAAMMJJ_HHMMSS>_<source>.jsonl (immuable) ; événement dans journal/
CATEGORIE: apprentissage
BANC: -
REMPLACE: -
"""
import sys, os, re, json, glob, hashlib, datetime, collections
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
from cc_lib_v1 import RACINE_CC, evenement, derniere_version
E = os.path.join(RACINE_CC, 'entrainement')
RANG_QUALITE = {'or': 3, 'argent': 2, 'bronze': 1}
def opt(a, k, d=None): return a[a.index(k) + 1] if k in a else d


def spec(tache):
    f = derniere_version(os.path.join(E, 'taches'), tache, 'json')
    if not f: raise SystemExit(f'spécification absente : entrainement/taches/{tache}_vN.json')
    return json.load(open(f, encoding='utf-8'))


def uid(tache, entree): return hashlib.sha256((tache + '|' + json.dumps(entree, ensure_ascii=False, sort_keys=True)).encode()).hexdigest()[:16]


def exemples(tache):
    for f in sorted(glob.glob(os.path.join(E, 'donnees', tache, 'lot_*.jsonl'))):
        for l in open(f, encoding='utf-8'):
            if l.strip(): yield json.loads(l)


def collecter(a):
    tache = a[0]; S = spec(tache)
    T = {x['id']: x for x in (json.loads(l) for l in open(opt(a, '--taches'), encoding='utf-8') if l.strip())}
    brut = json.load(open(opt(a, '--etiquettes'), encoding='utf-8')); brut = brut.get('references', brut)
    q, source, travail = opt(a, '--qualite'), opt(a, '--source'), opt(a, '--travail')
    regles = set((opt(a, '--regles') or '').split(',')) - {''}; q_regle = opt(a, '--qualite-regle', 'bronze')
    deja = {(x['uid'], x['source']) for x in exemples(tache)}
    now = datetime.datetime.now(datetime.timezone.utc); L = []
    for i, v in sorted(brut.items()):
        if i not in T: continue
        val = v['final'] if isinstance(v, dict) else v
        if val not in S['classes']: continue
        qq, src = q, source
        if isinstance(v, dict) and v.get('regle') in regles: qq, src = q_regle, 'regle:' + v['regle']
        entree = {c: T[i][c] for c in S['entree']}; u = uid(tache, entree)
        if (u, src) in deja: continue
        deja.add((u, src))
        L.append(dict(uid=u, tache=tache, entree=entree, etiquette=val, qualite=qq, source=src,
                      origine=dict(travail=travail, id=i), date=now.strftime('%Y-%m-%dT%H:%M:%SZ')))
    if not L: print('aucun exemple nouveau'); return
    d = os.path.join(E, 'donnees', tache); os.makedirs(d, exist_ok=True)
    f = os.path.join(d, f"lot_{now.strftime('%Y%m%d_%H%M%S')}_{re.sub(r'[^A-Za-z0-9.-]+', '-', source)}.jsonl")
    with open(f, 'x', encoding='utf-8') as g: g.write(''.join(json.dumps(x, ensure_ascii=False, sort_keys=True) + '\n' for x in L))
    c = collections.Counter((x['qualite'], x['etiquette']) for x in L)
    evenement('donnees_entrainement', 1, 'collecte', dict(tache=tache, source=source, exemples=len(L), fichier=os.path.basename(f)))
    print(f'{len(L)} exemple(s) -> {os.path.relpath(f, RACINE_CC)} ; {dict(c)}')


def charger_jeu(tache):
    """Jeu consolidé déterministe : une étiquette par entrée (meilleure qualité ; à qualité égale, l'utilisateur, puis l'accord
    du plus grand nombre de sources) ; poids = poids de la qualité (spécification) ; liste triée par uid."""
    S = spec(tache); par = collections.defaultdict(list)
    for x in exemples(tache): par[x['uid']].append(x)
    J = []
    for u in sorted(par):
        X = par[u]; top = max(RANG_QUALITE[x['qualite']] for x in X); X = [x for x in X if RANG_QUALITE[x['qualite']] == top]
        util = [x for x in X if x['source'].startswith('utilisateur')]
        if util: X = util
        votes = collections.Counter(x['etiquette'] for x in X); lab, n = sorted(votes.items(), key=lambda kv: (-kv[1], kv[0]))[0]
        q = X[0]['qualite']
        J.append(dict(uid=u, entree=X[0]['entree'], etiquette=lab, qualite=q, poids=S['poids'][q] * (1.0 if n == len(X) else 0.5),
                      sources=sorted({x['source'] for x in X}), origines=sorted({x['origine']['id'] for x in par[u]})))
    return S, J


def etat(a):
    tache = a[0]; S, J = charger_jeu(tache)
    print(f'{tache} : {len(J)} entrées distinctes ; classes {S["classes"]}')
    print('  par qualité :', dict(collections.Counter(x['qualite'] for x in J)))
    print('  par classe (or) :', dict(collections.Counter(x['etiquette'] for x in J if x['qualite'] == 'or')))
    print('  par classe (tout) :', dict(collections.Counter(x['etiquette'] for x in J)))
    print('  lots :', len(glob.glob(os.path.join(E, 'donnees', tache, 'lot_*.jsonl'))))


if __name__ == '__main__':
    {'collecter': collecter, 'etat': etat, 'jeu': etat}[sys.argv[1]](sys.argv[2:])
