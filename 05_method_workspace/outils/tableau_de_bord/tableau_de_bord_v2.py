"""
OUTIL: tableau_de_bord
VERSION: 2
RESUME: Tableau de bord visuel du flux de travail, pour que l'utilisateur suive la progression et repère les goulots d'étranglement, en français ou en anglais (bouton FR / EN), en instantané (artifact) ou en direct sur le PC (serveur_tableau_de_bord). (1) Journal des étapes : début, fin, point d'étape, attente (raison : pc, utilisateur, agents, lmstudio), en événements immuables du journal ; importation d'étapes reconstituées, sans doublon. (2) Agrégation déterministe : journal des outils (exécutions réelles et essais de banc, par heure et par outil, durées mesurées, résultats des tests), étapes appariées, agents (durée, charge de contexte maximale, tokens, appels d'outils, vagues et traînards) lus dans leurs transcriptions avec un cache incrémental (un fichier inchangé n'est pas relu), planificateur (tâches planifiées, tâche cron de session, ouvrier LM Studio, rappels ; expressions cron vérifiées), ce qui attend (décisions de l'utilisateur, sauvegardes non confirmées, PC injoignable). (3) Règles de goulots G-… avec preuve et piste. (4) Page HTML autonome (deux thèmes, largeur téléphone, données intégrées, prochaines exécutions calculées à l'ouverture, heures locales du lecteur) à publier en artifact ; la même page, servie par serveur_tableau_de_bord sur le PC, passe en direct : elle relit les fichiers bruts toutes les 5 s et refait l'agrégation dans le navigateur (agrégateur JavaScript équivalent à collecter, vérifié par les tests). (5) Ouvrier LM Studio : état de la file (etat.json, lots en entrée) et goulots G-LM. Nouvelle version d'un fichier seulement si son contenu change.
USAGE: python3 outils/tableau_de_bord.py etape debut|fin|point|attente <id> [--titre "…"] [--categorie rapport|outils|revue|sync|agents|attente|autre] [--raison pc|utilisateur|agents|lmstudio|autre] [--note "…"] [--tokens N] [--resultat ok|partiel|echec] [--quand AAAA-MM-JJTHH:MM:SSZ] [--source direct|reconstitue]  |  importer_etapes <etapes.json>  |  agents [--source <dossier subagents>]…  |  cron "<expression>" [--n 5]  |  generer [--sans-agents] [--avec-essais] [--etat-sync <etat.json>]  |  brut [--sortie <fichier>] (fichiers bruts au format du serveur local, pour les tests)  |  etat
ENTREES: journal/AAAA-MM-JJ/*.json ; taches/planificateur_vN.json ; propositions/registre_propositions_vN.json ; revues/tableau_de_bord/agents_vN.json (cache) ; transcriptions des agents (/root/.claude/projects/*/*/subagents/agent-*.jsonl et .meta.json, dans le cloud seulement) ; état de la sauvegarde cloud → PC (/home/claude/.sync_cloud_pc/etat.json, facultatif) ; ouvrier LM Studio (Revision/00_espace_cloud_claude/file_lmstudio/journal/etat.json et entree/*.jsonl, facultatif)
SORTIES: événements « etape » et « generation » dans journal/ ; revues/tableau_de_bord/agents_vN.json, donnees_tableau_vN.json, tableau_de_bord_vN.html (nouvelle version seulement si le contenu change)
CATEGORIE: gouvernance
BANC: tests/test_tableau_de_bord_v2.py
REMPLACE: tableau_de_bord_v1 (bouton FR / EN ; mode direct par le serveur local du PC, avec agrégateur JavaScript équivalent ; goulots avec paramètres, rendus dans les deux langues ; arrondis déterministes identiques en Python et en JavaScript ; ouvrier LM Studio et goulots G-LM1, G-LM2) ; v1 : -
"""
import sys, os, re, json, glob, datetime, collections, statistics, math
H = os.path.dirname(os.path.abspath(__file__)); O = H
while os.path.basename(O) != 'outils' and os.path.dirname(O) != O: O = os.path.dirname(O)
for p in (os.path.join(O, '_compat'), O):
    if p not in sys.path: sys.path.insert(0, p)
import cc_lib_v4 as L                                   # noqa: E402
from cc_lib_v4 import chemin, ecrire_versionne         # noqa: E402
try:
    from zoneinfo import ZoneInfo
except ImportError:                                     # pragma: no cover
    ZoneInfo = None

CC = os.path.dirname(O); VERSION = 2; OUTIL = 'tableau_de_bord'
CATEGORIES = ('rapport', 'outils', 'revue', 'sync', 'agents', 'attente', 'autre')
PHASES = ('debut', 'fin', 'point', 'attente')
RAISONS = ('pc', 'utilisateur', 'agents', 'lmstudio', 'autre')
RESULTATS = ('ok', 'partiel', 'echec')
SEUILS = dict(contexte_agent=300000, trainard=1.5, ecart_vague_s=180, part_attente=0.25, part_attente_majeure=0.5,
              etape_ouverte_h=2.0, proposition_jours=3.0, part_essais=0.7)
SOURCES_AGENTS = '/root/.claude/projects/*/*/subagents'
ETAT_SYNC = '/home/claude/.sync_cloud_pc/etat.json'
CLES_TEXTE = ('verdict', 'statut', 'mode', 'commande', 'phase', 'outil', 'cible')


def opt(a, k, d=None): return a[a.index(k) + 1] if k in a and a.index(k) + 1 < len(a) else d


def opts(a, k): return [a[i + 1] for i, x in enumerate(a) if x == k and i + 1 < len(a)]


def sortie(*p): return chemin('revues', 'tableau_de_bord', *p, racine=CC)


# ---------- temps
def utc(t): return t.astimezone(datetime.timezone.utc)


def lire_t(s):
    """« 2026-10-15T20:16:33Z », « …33.916Z », « 2026-10-15 18:05 » (UTC) ou avec décalage → datetime UTC."""
    s = s.strip().replace(' ', 'T', 1).replace('Z', '+00:00')
    t = datetime.datetime.fromisoformat(s)
    return utc(t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc))


def iso(t): return utc(t).strftime('%Y-%m-%dT%H:%M:%SZ')


def maintenant(): return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


MOIS = ('janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.')


def arr(x, d=0):
    """Arrondi déterministe au plus proche, moitié vers le haut : même résultat en Python et dans l'agrégateur JavaScript
    (Math.floor(x * 10^d + 0.5) / 10^d), à la différence de round(), qui arrondit au pair."""
    k = 10 ** d
    return math.floor(x * k + 0.5) / k if d else int(math.floor(x + 0.5))


def fr(x, d=1):
    """Nombre à la française : virgule décimale, sans zéro inutile (79,8 ; 3)."""
    t = f'{arr(x, d):.{d}f}'.rstrip('0').rstrip('.') if d else str(arr(x))
    return t.replace('.', ',')


def jour_fr(j): a, m, d = j[:10].split('-'); return f'{int(d)} {MOIS[int(m) - 1]} {a}'


# ---------- cron (5 champs, préfixe CRON_TZ= facultatif ; même logique que la page)
def champ(s, lo, hi):
    vals = set()
    for part in s.split(','):
        m = re.fullmatch(r'(\*|\d+(?:-\d+)?)(?:/(\d+))?', part)
        if not m: raise ValueError(f'champ cron invalide : {part!r}')
        r, pas = m.group(1), int(m.group(2) or 1)
        if r == '*': a, b = lo, hi
        elif '-' in r: a, b = map(int, r.split('-'))
        else: a = b = int(r); b = hi if m.group(2) else b
        if a < lo or b > hi or a > b or pas < 1: raise ValueError(f'champ cron hors bornes : {part!r}')
        vals.update(range(a, b + 1, pas))
    return vals


def analyser_cron(expr):
    e = expr.strip(); tz = 'UTC'
    m = re.match(r'CRON_TZ=(\S+)\s+(.*)$', e)
    if m: tz, e = m.group(1), m.group(2)
    p = e.split()
    if len(p) != 5: raise ValueError(f'expression cron à 5 champs attendue : {expr!r}')
    if tz != 'UTC' and ZoneInfo is None: raise ValueError('fuseau non pris en charge ici')
    if tz != 'UTC': ZoneInfo(tz)
    return dict(tz=tz, mi=champ(p[0], 0, 59), h=champ(p[1], 0, 23), dom=champ(p[2], 1, 31), mo=champ(p[3], 1, 12),
                dow={0 if d == 7 else d for d in champ(p[4], 0, 7)}, dom_etoile=p[2] == '*', dow_etoile=p[4] == '*')


def correspond(C, t):
    """t : datetime dans le fuseau de l'expression. Jour : ET si l'un des deux champs vaut *, OU sinon (cron standard)."""
    if t.minute not in C['mi'] or t.hour not in C['h'] or t.month not in C['mo']: return False
    jd, js = t.day in C['dom'], (t.weekday() + 1) % 7 in C['dow']
    if C['dom_etoile'] or C['dow_etoile']: return jd and js
    return jd or js


def prochaines(expr, depuis=None, n=5, horizon_j=8):
    """n prochaines exécutions strictement après « depuis » (UTC, à la minute), dans un horizon de horizon_j jours."""
    C = analyser_cron(expr); zone = datetime.timezone.utc if C['tz'] == 'UTC' else ZoneInfo(C['tz'])
    u = utc(depuis or maintenant()).replace(second=0, microsecond=0); R = []
    for _ in range(horizon_j * 1440):
        u += datetime.timedelta(minutes=1)
        if correspond(C, u.astimezone(zone)):
            R.append(u)
            if len(R) >= n: break
    return R


# ---------- journal
def evenements():
    J = chemin('journal', racine=CC); E = []
    for d in sorted(glob.glob(os.path.join(J, '????-??-??'))):
        for f in sorted(glob.glob(os.path.join(d, '*.json'))):
            try:
                with open(f, encoding='utf-8') as g: e = json.load(g)
            except (OSError, ValueError): continue
            if isinstance(e, dict) and e.get('date') and e.get('outil'): e.setdefault('donnees', {}); E.append(e)
    return E


def est_essai(e): return bool((e.get('donnees') or {}).get('banc'))


def resume(e):
    """Résumé court et sûr d'un événement : nombres, booléens et quelques clés de texte connues (jamais de texte libre)."""
    R = {}
    for k, v in sorted((e.get('donnees') or {}).items()):
        if k in ('banc', 'mesures'): continue
        if isinstance(v, bool) or isinstance(v, (int, float)): R[k] = v
        elif isinstance(v, str) and k in CLES_TEXTE and len(v) <= 40: R[k] = v
        elif isinstance(v, (list, dict)): R[k] = f'{len(v)} él.'
        if len(R) >= 4: break
    return R


# ---------- étapes
def etapes_de(E, avec_essais=False):
    S = {}
    def cle(e): return (e['donnees'].get('quand') or e['date'], e['date'])
    for e in sorted((e for e in E if e.get('outil') == OUTIL and e.get('type') == 'etape' and (avec_essais or not est_essai(e))), key=cle):
        d = e['donnees']; q = iso(lire_t(d.get('quand') or e['date'])); ph = d.get('phase')
        s = S.setdefault(d.get('id'), dict(id=d.get('id'), titre=None, categorie='autre', raison=None, debut=None, fin=None,
                                           points=[], notes=[], tokens=0, resultat=None, source=d.get('source', 'direct')))
        if ph in ('debut', 'attente'):
            s['debut'] = min(s['debut'], q) if s['debut'] else q
            s['titre'] = d.get('titre') or s['titre']
            s['categorie'] = 'attente' if ph == 'attente' else (d.get('categorie') or s['categorie'])
            s['raison'] = d.get('raison') or s['raison']
        elif ph == 'fin': s['fin'] = q; s['resultat'] = d.get('resultat') or 'ok'
        elif ph == 'point': s['points'].append(dict(quand=q, note=d.get('note', '')))
        if d.get('note') and ph != 'point': s['notes'].append(d['note'])
        if d.get('tokens'): s['tokens'] += int(d['tokens'])
    for s in S.values():
        s['titre'] = s['titre'] or s['id']
        if not s['debut']: s['debut'] = min([p['quand'] for p in s['points']] + ([s['fin']] if s['fin'] else []))
        s['duree_s'] = int((lire_t(s['fin']) - lire_t(s['debut'])).total_seconds()) if s['fin'] else None
    return sorted(S.values(), key=lambda s: s['debut'])


def deja_ecrites(E):
    return {(e['donnees'].get('id'), e['donnees'].get('phase'), e['donnees'].get('quand')) for e in E if e.get('outil') == OUTIL and e.get('type') == 'etape'}


def ecrire_etape(phase, id_, titre=None, categorie=None, raison=None, note=None, tokens=None, resultat=None, quand=None, source='direct'):
    if phase not in PHASES: raise SystemExit(f'phase inconnue : {phase} (attendu : {", ".join(PHASES)})')
    if categorie and categorie not in CATEGORIES: raise SystemExit(f'catégorie inconnue : {categorie} (attendu : {", ".join(CATEGORIES)})')
    if raison and raison not in RAISONS: raise SystemExit(f'raison inconnue : {raison} (attendu : {", ".join(RAISONS)})')
    if resultat and resultat not in RESULTATS: raise SystemExit(f'résultat inconnu : {resultat}')
    if phase in ('debut', 'attente') and not titre: raise SystemExit('--titre est requis pour débuter une étape')
    if not re.fullmatch(r'[\w.:-]{1,80}', id_ or ''): raise SystemExit(f'identifiant d’étape invalide : {id_!r}')
    d = dict(id=id_, phase=phase, titre=titre, categorie='attente' if phase == 'attente' else categorie, raison=raison, note=note,
             tokens=int(tokens) if tokens not in (None, '') else None, resultat=resultat, quand=iso(lire_t(quand) if quand else maintenant()), source=source)
    return L.evenement(OUTIL, VERSION, 'etape', {k: v for k, v in d.items() if v is not None})


def importer_etapes(f):
    with open(f, encoding='utf-8') as g: Lst = json.load(g)
    if isinstance(Lst, dict): Lst = Lst.get('etapes', [])
    vu = deja_ecrites(evenements()); n = 0
    for x in Lst:
        src = x.get('source', 'reconstitue'); ph0 = 'attente' if x.get('categorie') == 'attente' else 'debut'
        lots = [(ph0, x['debut'], dict(titre=x.get('titre'), categorie=x.get('categorie'), raison=x.get('raison'), note=x.get('note'), tokens=x.get('tokens')))]
        if x.get('fin'): lots.append(('fin', x['fin'], dict(resultat=x.get('resultat'), note=x.get('note_fin'))))
        for ph, q, k in lots:
            if (x['id'], ph, iso(lire_t(q))) in vu: continue
            ecrire_etape(ph, x['id'], quand=q, source=src, **k); n += 1
    return n


# ---------- agents (transcriptions des sous-agents)
def lire_agent(f):
    msgs, ts, outils_n, modeles = {}, [], 0, collections.Counter()
    with open(f, encoding='utf-8', errors='replace') as g:
        for l in g:
            try: d = json.loads(l)
            except ValueError: continue
            if not isinstance(d, dict): continue
            if d.get('timestamp'): ts.append(d['timestamp'])
            m = d.get('message')
            if d.get('type') == 'assistant' and isinstance(m, dict):
                if m.get('usage'): msgs[m.get('id') or d.get('uuid') or len(msgs)] = m['usage']
                if m.get('model') and not str(m['model']).startswith('<'): modeles[m['model']] += 1
                for c in m.get('content') or []:
                    if isinstance(c, dict) and c.get('type') == 'tool_use': outils_n += 1
    if not ts: return None
    ctx = [int(u.get('input_tokens', 0) or 0) + int(u.get('cache_read_input_tokens', 0) or 0) + int(u.get('cache_creation_input_tokens', 0) or 0) for u in msgs.values()]
    out = [int(u.get('output_tokens', 0) or 0) for u in msgs.values()]
    meta = {}; fm = f[:-len('.jsonl')] + '.meta.json'
    if os.path.exists(fm):
        try:
            with open(fm, encoding='utf-8') as g: meta = json.load(g)
        except ValueError: meta = {}
    T = sorted(lire_t(t) for t in ts); st = os.stat(f)
    return dict(id=os.path.basename(f)[:-len('.jsonl')], session=os.path.basename(os.path.dirname(os.path.dirname(f)))[:8],
                description=str(meta.get('description') or '')[:80], type=meta.get('agentType'), modele=modeles.most_common(1)[0][0] if modeles else None,
                debut=iso(T[0]), fin=iso(T[-1]), duree_s=int((T[-1] - T[0]).total_seconds()), contexte_max=max(ctx) if ctx else 0,
                contexte_final=(ctx[-1] + out[-1]) if ctx else 0, sortie=sum(out), traites=sum(ctx) + sum(out), appels=len(msgs),
                appels_outils=outils_n, taille=st.st_size, mtime=int(st.st_mtime))


def cache_agents():
    f = L.derniere_version(sortie(), 'agents', 'json')
    if not f: return {}
    with open(f, encoding='utf-8') as g: return json.load(g).get('agents', {})


def maj_agents(sources=None):
    """Lit les transcriptions nouvelles ou modifiées ; reprend les autres du cache, y compris celles d'une session disparue."""
    S = sources if sources else glob.glob(SOURCES_AGENTS); A = cache_agents(); lus = repris = 0
    for d in S:
        for f in sorted(glob.glob(os.path.join(d, 'agent-*.jsonl'))):
            st = os.stat(f); k = os.path.basename(os.path.dirname(os.path.dirname(f)))[:8] + '/' + os.path.basename(f)[:-len('.jsonl')]
            if k in A and A[k].get('taille') == st.st_size and A[k].get('mtime') == int(st.st_mtime): repris += 1; continue
            a = lire_agent(f)
            if a: A[k] = a; lus += 1
    fo, cree = ecrire_versionne(sortie(), 'agents', 'json', json.dumps(dict(agents=A), ensure_ascii=False, indent=1, sort_keys=True))
    return fo, cree, lus, repris, A


def libelle(D):
    if len(D) == 1: return D[0] or 'agent'
    p = os.path.commonprefix(D)
    if not all(d.startswith(p + ' ') or d == p for d in D) and ' ' in p: p = p[:p.rfind(' ')]
    p = p.strip(' -–:·(')
    return p if len(p) >= 4 else f"{D[0] or 'agent'} (+{len(D) - 1})"


def vagues(A):
    A = sorted(A, key=lambda a: a['debut']); V = []
    for a in A:
        if V and (lire_t(a['debut']) - lire_t(V[-1][-1]['debut'])).total_seconds() <= SEUILS['ecart_vague_s']: V[-1].append(a)
        else: V.append([a])
    R = []
    for i, v in enumerate(V, 1):
        D = [x['duree_s'] for x in v]; med = statistics.median(D); lent = max(v, key=lambda x: x['duree_s'])
        deb, fin = min(x['debut'] for x in v), max(x['fin'] for x in v)
        R.append(dict(id=f'V{i:03d}', libelle=libelle([x['description'] for x in v]), debut=deb, fin=fin, n=len(v),
                      mur_s=int((lire_t(fin) - lire_t(deb)).total_seconds()), somme_s=sum(D), mediane_s=int(med), max_s=max(D),
                      ratio=arr(max(D) / med, 2) if med else None, trainard=lent['description'], contexte_moyen=int(statistics.mean(x['contexte_max'] for x in v)),
                      contexte_max=max(x['contexte_max'] for x in v), sortie=sum(x['sortie'] for x in v), traites=sum(x['traites'] for x in v),
                      lourds=sum(1 for x in v if x['contexte_max'] > SEUILS['contexte_agent']),
                      modeles=dict(collections.Counter(x['modele'] or '?' for x in v)), agents=[x['id'] for x in v]))
        for x in v: x['vague'] = R[-1]['id']
    return R


# ---------- planificateur et attentes
def planificateur():
    f = L.derniere_version(chemin('taches', racine=CC), 'planificateur', 'json')
    if not f: return dict(source=None, taches=[], erreurs=[])
    with open(f, encoding='utf-8') as g: P = json.load(g)
    T, Er = [], []
    for t in P.get('taches', []):
        t = dict(t)
        if t.get('cron'):
            try: analyser_cron(t['cron'])
            except ValueError as e: Er.append(f"{t.get('id')} : {e}"); t['cron_invalide'] = True
        T.append(t)
    return dict(source=os.path.relpath(f, CC).replace(os.sep, '/'), note=P.get('note'), taches=T, erreurs=Er)


def statut_proposition(P):
    """Même règle que suivre_propositions.statut : dernier événement qui clôt ou qui suspend, sinon « proposée »."""
    E = [e.get('evenement') for e in P.get('evenements', [])]
    for ev in reversed(E):
        if ev in ('acceptee', 'refusee', 'remplacee', 'retiree', 'modification_demandee', 'a_confirmer'): return ev
    return 'proposee' if E else '?'


def attentes(Et, etat_sync):
    R = dict(propositions=[], sauvegardes=dict(non_confirmees=[], derniere_complete=None, source=None), pc=dict(injoignable=False, depuis=None, etape=None), etapes=[])
    f = L.derniere_version(chemin('propositions', racine=CC), 'registre_propositions', 'json')
    if f:
        with open(f, encoding='utf-8') as g: Reg = json.load(g).get('propositions', {})
        for pid, P in sorted(Reg.items()):
            st = statut_proposition(P)
            if st in ('proposee', 'modification_demandee', 'a_confirmer'):
                dates = [e.get('date') for e in P.get('evenements', []) if e.get('date')]
                R['propositions'].append(dict(id=pid, type=P.get('type'), objet=str(P.get('objet') or pid)[:110], statut=st,
                                              depuis=iso(lire_t(min(dates))) if dates else None))
    if etat_sync and os.path.exists(etat_sync):
        try:
            with open(etat_sync, encoding='utf-8') as g: S = json.load(g)
            R['sauvegardes']['source'] = 'etat de sync_cloud_pc'
            for ts, v in sorted((S.get('attente') or {}).items()):
                m = re.fullmatch(r'(\d{8})_(\d{6})', ts)
                if m: R['sauvegardes']['non_confirmees'].append(dict(ts=ts, quand=iso(datetime.datetime.strptime(ts, '%Y%m%d_%H%M%S').replace(tzinfo=datetime.timezone.utc)),
                                                                     fichiers=len((v or {}).get('copies', [])) if isinstance(v, dict) else None))
            m = re.search(r'(\d{8}_\d{6})', str(S.get('base') or ''))
            if m: R['sauvegardes']['derniere_complete'] = iso(datetime.datetime.strptime(m.group(1), '%Y%m%d_%H%M%S').replace(tzinfo=datetime.timezone.utc))
        except (OSError, ValueError): pass
    for s in Et:
        if s['categorie'] == 'attente' and not s['fin']:
            R['etapes'].append(dict(id=s['id'], titre=s['titre'], raison=s['raison'], depuis=s['debut']))
            if s['raison'] == 'pc': R['pc'] = dict(injoignable=True, depuis=s['debut'], etape=s['id'])
    return R


# ---------- goulots
def nombre(v): return isinstance(v, (int, float)) and not isinstance(v, bool)


def goulots(Et, A, V, E, att, tests, ref, lm=None):
    """Règles G-… : chaque constat porte ses paramètres (« params »), dont la page tire le texte dans la langue choisie ;
    titre, preuve et piste restent écrits en français pour la ligne de commande. Même logique dans l'agrégateur JavaScript."""
    G = []
    def g(code, niveau, titre, preuve, piste, /, **p): G.append(dict(code=code, niveau=niveau, titre=titre, preuve=preuve, piste=piste, params=p))
    for v in V[-6:]:
        if v['n'] >= 3 and v['ratio'] and v['ratio'] >= SEUILS['trainard']:
            g('G-AG1', 'attention', f"Vague « {v['libelle']} » : un agent traînard",
              f"{v['n']} agents ; le plus lent ({v['trainard']}) a duré {v['max_s'] // 60} min, la médiane {v['mediane_s'] // 60} min (×{fr(v['ratio'], 2)}).",
              "Équilibrer les lots : donner moins de travail à l'agent le plus lent, ou couper son lot en deux.",
              libelle=v['libelle'], n=v['n'], trainard=v['trainard'], max_min=v['max_s'] // 60, med_min=v['mediane_s'] // 60, ratio=v['ratio'])
    rec = [a for a in A if (ref - lire_t(a['debut'])).total_seconds() <= 7 * 86400]
    lourds = [a for a in rec if a['contexte_max'] > SEUILS['contexte_agent']]
    if lourds:
        top = max(lourds, key=lambda a: a['contexte_max'])
        g('G-AG2', 'attention', 'Charge de contexte élevée chez des agents',
          f"{len(lourds)} agent(s) sur {len(rec)} en 7 jours au-dessus de {SEUILS['contexte_agent'] // 1000} k tokens ; maximum {top['contexte_max'] // 1000} k ({top['description']}).",
          "Briefs plus courts et lots plus petits : les agents puisent dans le même réservoir de tokens.",
          n=len(lourds), total=len(rec), seuil_k=SEUILS['contexte_agent'] // 1000, max_k=top['contexte_max'] // 1000, description=top['description'])
    jour = iso(ref)[:10]; Ej = [s for s in Et if s['debut'][:10] == jour]
    def duree(s): return ((lire_t(s['fin']) if s['fin'] else ref) - lire_t(s['debut'])).total_seconds()
    tot = sum(duree(s) for s in Ej if s['categorie'] != 'attente'); att_s = sum(duree(s) for s in Ej if s['categorie'] == 'attente')
    if tot + att_s > 0 and att_s / (tot + att_s) >= SEUILS['part_attente']:
        part = att_s / (tot + att_s)
        g('G-AT1', 'majeur' if part >= SEUILS['part_attente_majeure'] else 'attention', "Temps d'attente important aujourd'hui",
          f"{arr(100 * part)} % du temps des étapes du {jour_fr(jour)} est en attente ({int(att_s // 60)} min).",
          "Préparer en amont ce qui attend (lots, décisions groupées) et poursuivre une autre tâche pendant l'attente.",
          part_pct=arr(100 * part), jour=jour, attente_min=int(att_s // 60))
    for s in Et:
        if not s['fin'] and s['categorie'] != 'attente' and duree(s) / 3600 >= SEUILS['etape_ouverte_h'] and not s['points']:
            g('G-ET1', 'info', f"Étape ouverte depuis longtemps : {s['titre']}", f"Ouverte depuis {fr(duree(s) / 3600)} h sans point d'étape.",
              "Noter un point d'étape (« etape point ») ou la clore.", titre=s['titre'], heures=arr(duree(s) / 3600, 1))
    if att['sauvegardes']['non_confirmees']:
        nc = att['sauvegardes']['non_confirmees']; age = (ref - lire_t(nc[0]['quand'])).total_seconds() / 3600
        g('G-SY1', 'majeur' if age >= 12 else 'attention', 'Sauvegardes vers le PC non confirmées',
          f"{len(nc)} envoi(s) non confirmé(s), le plus ancien il y a {fr(age)} h" + (" ; PC injoignable." if att['pc']['injoignable'] else '.'),
          "Au retour du PC : sauvegarde complète (manifeste d'abord), puis « N / N conformes ».",
          n=len(nc), age_h=arr(age, 1), pc_injoignable=bool(att['pc']['injoignable']))
    P = att['propositions']
    if P:
        ages = [(ref - lire_t(p['depuis'])).total_seconds() / 86400 for p in P if p['depuis']]; vieux = max(ages) if ages else 0
        g('G-PR1', 'attention' if vieux >= SEUILS['proposition_jours'] else 'info', "Décisions de l'utilisateur en attente",
          f"{len(P)} proposition(s) ouvertes ; la plus ancienne depuis {fr(vieux)} j.",
          "Les regrouper dans une seule revue (index de skills_propositions_a_reviser).", n=len(P), jours=arr(vieux, 1))
    Ed = [e for e in E if e['date'][:10] == jour]
    if Ed:
        pe = sum(1 for e in Ed if est_essai(e)) / len(Ed)
        if pe >= SEUILS['part_essais']:
            g('G-JO1', 'info', 'Le journal est dominé par les essais', f"{arr(100 * pe)} % des {len(Ed)} événements du {jour_fr(jour)} viennent des tests et des bancs.",
              "Les tests complets tournent souvent : les réserver aux adoptions et à la fin d'étape ; lancer une suite seule sinon.",
              part_pct=arr(100 * pe), n=len(Ed), jour=jour)
    du = collections.Counter()
    for e in E:
        m = (e.get('donnees') or {}).get('mesures') or {}
        if nombre(m.get('duree_s')) and not est_essai(e): du[e['outil']] += m['duree_s']
    if du:
        o, s = du.most_common(1)[0]
        g('G-OU1', 'info', 'Outil le plus long (durées mesurées)', f"{o} : {fr(s)} s cumulées ; {len(du)} outil(s) seulement mesurent leur durée.",
          "Mesurer la durée dans les autres outils (mesures.duree_s) pour comparer.", outil=o, secondes=arr(s, 1), n_outils=len(du))
    if tests and tests[-1].get('verdict') not in (None, 'conforme'):
        g('G-TE1', 'majeur', 'Derniers tests non conformes', f"{tests[-1].get('unitaires_echecs')} échec(s) sur {tests[-1].get('unitaires')}.", "Corriger avant toute adoption.",
          echecs=tests[-1].get('unitaires_echecs'), total=tests[-1].get('unitaires'))
    if lm:
        et = lm.get('etat') or {}; st = et.get('statut'); n_ent = lm.get('lots_entree') or 0
        if n_ent and (not et or str(st or '').startswith('arr')):        # « arrêté » (ou ses accents mal lus par PowerShell 5.1)
            g('G-LM1', 'attention', 'Lots LM Studio en attente : ouvrier arrêté',
              f"{n_ent} lot(s) dans la file d'entrée ; ouvrier {'jamais lancé' if not et else 'arrêté' + (' (' + str(et.get('raison_arret')) + ')' if et.get('raison_arret') else '')}.",
              "Lancer l'ouvrier (lancer_worker_lmstudio, double-clic) : les lots partent seuls, regroupés par modèle.",
              lots=n_ent, jamais=not et, raison=et.get('raison_arret'))
        if st == 'attente de LM Studio':
            g('G-LM2', 'attention', 'LM Studio injoignable pour l\'ouvrier', f"Ouvrier en attente de LM Studio ; {et.get('en_attente') or 0} tâche(s) en file.",
              "Démarrer le serveur de LM Studio (onglet Developer, Start Server) ; l'ouvrier reprend seul.", en_attente=et.get('en_attente') or 0)
    ordre = dict(majeur=0, attention=1, info=2)
    return sorted(G, key=lambda x: (ordre[x['niveau']], x['code']))


# ---------- ouvrier LM Studio (facultatif : PC)
def lire_lmstudio(racine_file=None):
    """État de l'ouvrier LM Studio (journal/etat.json) et nombre de lots dans entree/ ; None si la file est absente (cloud)."""
    F = racine_file or os.path.join(os.path.dirname(CC), '00_espace_cloud_claude', 'file_lmstudio')
    if not os.path.isdir(F): return None
    et = None; fe = os.path.join(F, 'journal', 'etat.json')
    if os.path.exists(fe):
        try:
            with open(fe, encoding='utf-8-sig') as g: et = json.load(g)
        except (OSError, ValueError): et = None
    E = os.path.join(F, 'entree'); n = len([f for f in os.listdir(E) if f.endswith('.jsonl')]) if os.path.isdir(E) else 0
    return dict(etat=et, lots_entree=n)


# ---------- collecte
def collecter(avec_essais=False, etat_sync=ETAT_SYNC, agents=None, lmstudio=None):
    """lmstudio : None = lire la file du PC si elle existe ; False = ignorer ; dict = état fourni (tests)."""
    Tout = evenements(); Et = etapes_de(Tout, avec_essais)
    lm = lire_lmstudio() if lmstudio is None else (lmstudio or None)
    E = [e for e in Tout if e['outil'] != OUTIL]           # événements des outils, sans ceux du tableau (étapes à part ; génération et cache exclus)
    A = sorted((agents if agents is not None else cache_agents()).values(), key=lambda a: a['debut'])
    A = [dict(a) for a in A]; V = vagues(A)
    for a in A: a.pop('taille', None); a.pop('mtime', None)
    act = collections.Counter(); ess = collections.Counter(); heures = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0, 0.0]))
    tests = []
    for e in E:
        t = e['date']; b = t[:15] + '0:00Z'; x = heures[t[:13]][e['outil']]
        if est_essai(e): ess[b] += 1; x[1] += 1
        else: act[b] += 1; x[0] += 1
        m = (e['donnees'].get('mesures') or {})
        if nombre(m.get('duree_s')): x[2] = arr(x[2] + m['duree_s'], 2)
        if e['outil'] == 'tester_outils' and e.get('type') == 'tests':
            d = e['donnees']; tests.append(dict(quand=t, unitaires=d.get('unitaires'), unitaires_echecs=d.get('unitaires_echecs'),
                                                fumee_echecs=d.get('fumee_echecs'), verdict=d.get('verdict'), complet=d.get('complet'), candidat=d.get('candidat')))
    hors = sorted(E, key=lambda e: e['date'])
    choisis = [e for e in hors if not est_essai(e)][-150:] + [e for e in hors if est_essai(e)][-80:]
    recents = [dict(quand=e['date'], outil=e['outil'], version=e.get('version'), type=e.get('type'), essai=est_essai(e), resume=resume(e)) for e in choisis]
    for s in Et:
        recents.append(dict(quand=s['debut'], etape=s['id'], phase='attente' if s['categorie'] == 'attente' else 'debut', titre=s['titre'], categorie=s['categorie'], source=s['source']))
        recents += [dict(quand=p['quand'], etape=s['id'], phase='point', titre=s['titre'], note=p['note'], categorie=s['categorie'], source=s['source']) for p in s['points']]
        if s['fin']: recents.append(dict(quand=s['fin'], etape=s['id'], phase='fin', titre=s['titre'], resultat=s['resultat'], categorie=s['categorie'], source=s['source']))
    recents.sort(key=lambda r: r['quand'])
    dates = [e['date'] for e in E] + [s['fin'] or s['debut'] for s in Et] + [p['quand'] for s in Et for p in s['points']] + [a['fin'] for a in A]
    ref = lire_t(max(dates)) if dates else maintenant()
    att = attentes(Et, etat_sync); P = planificateur()
    return dict(outil=f'{OUTIL}_v{VERSION}', etat_au=iso(ref), seuils=SEUILS, categories=list(CATEGORIES), etapes=Et, agents=A, vagues=V,
                activite=sorted([b, act[b], ess[b]] for b in set(act) | set(ess)),
                outils_heure={h: {o: v for o, v in sorted(d.items())} for h, d in sorted(heures.items())},
                journal_recent=recents, tests=tests[-30:], planificateur=P, attentes=att,
                goulots=goulots(Et, A, V, E, att, tests, ref, lm), lmstudio=lm,
                totaux=dict(evenements=len(E), essais=sum(1 for e in E if est_essai(e)), etapes=len(Et), agents=len(A), vagues=len(V)))


def page(D):
    brut = json.dumps(D, ensure_ascii=False, sort_keys=True).replace('</', '<\\/')
    return GABARIT.replace('/*__DONNEES__*/null', brut)


def generer(a):
    sans_agents = '--sans-agents' in a; A = None
    if not sans_agents: _, _, lus, repris, A = maj_agents(opts(a, '--source') or None)
    D = collecter('--avec-essais' in a, opt(a, '--etat-sync', ETAT_SYNC), A)
    fd, c1 = ecrire_versionne(sortie(), 'donnees_tableau', 'json', json.dumps(D, ensure_ascii=False, indent=1, sort_keys=True))
    fh, c2 = ecrire_versionne(sortie(), 'tableau_de_bord', 'html', page(D))
    L.evenement(OUTIL, VERSION, 'generation', dict(nouvelle_page=c2, etapes=len(D['etapes']), agents=len(D['agents']), goulots=len(D['goulots']),
                                                  evenements=D['totaux']['evenements']))
    return fd, c1, fh, c2, D


def brut(a):
    """Fichiers bruts au format du serveur local (serveur_tableau_de_bord) : une ligne par enregistrement, champs séparés par des
    tabulations. « M » méta ; « E clé json » un événement du journal (clé AAAA-MM-JJ/nom, ordre binaire) ; « F nom source json » :
    planificateur, registre, agents, lmstudio. Sert aux tests d'équivalence entre l'agrégateur JavaScript et collecter."""
    J = chemin('journal', racine=CC); lignes = []
    for d in sorted(glob.glob(os.path.join(J, '????-??-??'))):
        for f in sorted(glob.glob(os.path.join(d, '*.json'))):
            with open(f, encoding='utf-8') as g: txt = g.read().strip()
            lignes.append('E\t' + os.path.basename(d) + '/' + os.path.basename(f) + '\t' + txt)
    def fich(nom, f):
        if f:
            with open(f, encoding='utf-8') as g: lignes.append('F\t' + nom + '\t' + os.path.relpath(f, CC).replace(os.sep, '/') + '\t' + json.dumps(json.load(g), ensure_ascii=False))
    fich('planificateur', L.derniere_version(chemin('taches', racine=CC), 'planificateur', 'json'))
    fich('registre', L.derniere_version(chemin('propositions', racine=CC), 'registre_propositions', 'json'))
    fich('agents', L.derniere_version(sortie(), 'agents', 'json'))
    lm = lire_lmstudio()
    if lm is not None: lignes.append('F\tlmstudio\t-\t' + json.dumps(lm, ensure_ascii=False))
    ev = [l for l in lignes if l.startswith('E\t')]
    meta = dict(curseur=ev[-1].split('\t')[1] if ev else '', fin=True, n=len(ev), serveur='tableau_de_bord brut')
    txt = 'M\t' + json.dumps(meta, ensure_ascii=False) + '\n' + ''.join(l + '\n' for l in lignes)
    s = opt(a, '--sortie')
    if s:
        with open(s, 'w', encoding='utf-8') as g: g.write(txt)
    else: sys.stdout.write(txt)
    return 0


def etat(a):
    D = collecter('--avec-essais' in a, opt(a, '--etat-sync', ETAT_SYNC))
    ouv = [s for s in D['etapes'] if not s['fin']]
    print(f"données au {D['etat_au']} ; {D['totaux']['evenements']} événements ({D['totaux']['essais']} essais), {len(D['etapes'])} étapes, {len(D['agents'])} agents en {len(D['vagues'])} vagues")
    for s in ouv: print(f"  en cours : {s['id']} — {s['titre']} ({s['categorie']}, depuis {s['debut']})")
    for t in D['planificateur']['taches']:
        if t.get('cron') and not t.get('cron_invalide') and t.get('actif', True):
            p = prochaines(t['cron'], n=1); print(f"  planifié : {t.get('nom')} — prochaine {iso(p[0]) if p else '?'}")
    print(f"  en attente : {len(D['attentes']['propositions'])} décision(s), {len(D['attentes']['sauvegardes']['non_confirmees'])} sauvegarde(s) non confirmée(s), PC {'injoignable' if D['attentes']['pc']['injoignable'] else 'non signalé injoignable'}")
    for g in D['goulots']: print(f"  {g['code']} [{g['niveau']}] {g['titre']}")
    return 0


USAGE = __doc__.split('USAGE:')[1].split('ENTREES:')[0].strip()


def main(a=None):
    a = sys.argv[1:] if a is None else a
    if not a: print(USAGE); return 2
    c = a[0]
    if c == 'etape':
        if len(a) < 3: raise SystemExit('etape debut|fin|point|attente <id> …')
        f = ecrire_etape(a[1], a[2], titre=opt(a, '--titre'), categorie=opt(a, '--categorie'), raison=opt(a, '--raison'), note=opt(a, '--note'),
                         tokens=opt(a, '--tokens'), resultat=opt(a, '--resultat'), quand=opt(a, '--quand'), source=opt(a, '--source', 'direct'))
        print('étape notée :', os.path.relpath(f, CC)); return 0
    if c == 'importer_etapes':
        n = importer_etapes(a[1]); print(f'{n} événement(s) d’étape importé(s)'); L.evenement(OUTIL, VERSION, 'importer', dict(evenements=n)); return 0
    if c == 'agents':
        f, cree, lus, repris, A = maj_agents(opts(a, '--source') or None)
        print(f"{len(A)} agents ({lus} lus, {repris} repris du cache) → {os.path.relpath(f, CC)}{'' if cree else ' (inchangé)'}")
        L.evenement(OUTIL, VERSION, 'agents', dict(agents=len(A), lus=lus, repris=repris)); return 0
    if c == 'cron':
        for t in prochaines(a[1], n=int(opt(a, '--n', 5))): print(iso(t))
        return 0
    if c == 'generer':
        fd, c1, fh, c2, D = generer(a)
        print(f"données : {os.path.relpath(fd, CC)}{'' if c1 else ' (inchangées)'}")
        print(f"page : {os.path.relpath(fh, CC)}{'' if c2 else ' (inchangée)'}")
        print(f"{len(D['etapes'])} étapes, {len(D['agents'])} agents, {len(D['goulots'])} goulot(s) ; à publier en artifact (même URL que la version précédente)")
        return 0
    if c == 'etat': return etat(a)
    if c == 'brut': return brut(a)
    print(USAGE); return 2


GABARIT = r'''<title>Tableau de bord du flux</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+Condensed:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
:root{
  --bg:#f3f6f6;--surface:#ffffff;--surface-2:#e9efef;--fg:#122120;--muted:#566a68;--faint:#8a9b99;--line:#d3dedd;--line-2:#e4ebea;
  --accent:#0d7a72;--accent-soft:#d3ece9;--essai:#bccac8;--reel:#34504d;
  --c-rapport:#2c66ad;--c-outils:#0d7a72;--c-revue:#4c7a33;--c-sync:#a8700f;--c-agents:#6f52bd;--c-attente:#b8443f;--c-autre:#6d7d7b;
  --m-opus:#6f52bd;--m-sonnet:#2c66ad;--m-haiku:#a8700f;--m-autre:#6d7d7b;
  --majeur:#b8443f;--attention:#a8700f;--info:#566a68;
  --f-titre:"IBM Plex Sans Condensed","Arial Narrow","Roboto Condensed",system-ui,sans-serif;
  --f-texte:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  --f-mono:"IBM Plex Mono",ui-monospace,"SFMono-Regular",Consolas,monospace;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0e1514;--surface:#141d1c;--surface-2:#1b2625;--fg:#e2ebe9;--muted:#97aaa7;--faint:#6c7e7c;--line:#2a3a38;--line-2:#21302e;
  --accent:#3cbfb2;--accent-soft:#173d39;--essai:#3a4b49;--reel:#a9c4c0;
  --c-rapport:#6fa3e6;--c-outils:#3cbfb2;--c-revue:#8cc46a;--c-sync:#e0a94a;--c-agents:#a68ef0;--c-attente:#ec7f78;--c-autre:#9aaaa8;
  --m-opus:#a68ef0;--m-sonnet:#6fa3e6;--m-haiku:#e0a94a;--m-autre:#9aaaa8;
  --majeur:#ec7f78;--attention:#e0a94a;--info:#97aaa7;color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#0e1514;--surface:#141d1c;--surface-2:#1b2625;--fg:#e2ebe9;--muted:#97aaa7;--faint:#6c7e7c;--line:#2a3a38;--line-2:#21302e;
  --accent:#3cbfb2;--accent-soft:#173d39;--essai:#3a4b49;--reel:#a9c4c0;
  --c-rapport:#6fa3e6;--c-outils:#3cbfb2;--c-revue:#8cc46a;--c-sync:#e0a94a;--c-agents:#a68ef0;--c-attente:#ec7f78;--c-autre:#9aaaa8;
  --m-opus:#a68ef0;--m-sonnet:#6fa3e6;--m-haiku:#e0a94a;--m-autre:#9aaaa8;
  --majeur:#ec7f78;--attention:#e0a94a;--info:#97aaa7;color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);font:15px/1.5 var(--f-texte);
  padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:20px 48px}
.page{max-width:1180px;margin:0 auto;display:flex;flex-direction:column;gap:22px}
h1,h2,h3{font-family:var(--f-titre);text-wrap:balance;margin:0;line-height:1.15}
h1{font-size:clamp(28px,4.4vw,40px);font-weight:700;letter-spacing:-.01em}
h2{font-size:21px;font-weight:600;display:flex;gap:10px;align-items:baseline}
h2 .no{font-family:var(--f-mono);font-size:12px;color:var(--faint);font-weight:400}
h3{font-size:15px;font-weight:600}
.sur,.etiq{font-family:var(--f-titre);text-transform:uppercase;letter-spacing:.08em;font-size:12px;color:var(--muted);font-weight:600}
.mono,code,.num{font-family:var(--f-mono);font-variant-numeric:tabular-nums}
code{font-size:12.5px;background:var(--surface-2);padding:1px 5px;border-radius:4px;overflow-wrap:anywhere}
.aide{color:var(--muted);margin:0;max-width:72ch;font-size:14px}
.tete{display:flex;flex-direction:column;gap:14px;padding-bottom:6px;border-bottom:1px solid var(--line)}
.tete .etat{margin:0;color:var(--muted);font-size:14px}
.puces{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.puce{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:10px 12px;display:flex;flex-direction:column;gap:2px;min-width:0}
.puce .val{font-family:var(--f-mono);font-size:21px;font-weight:500;line-height:1.2;overflow-wrap:anywhere}
.puce .sous{font-size:12.5px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.puce.alerte{border-color:var(--majeur)}.puce.alerte .val{color:var(--majeur)}
.puce.ok .val{color:var(--accent)}
nav.sommaire{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:13.5px}
nav.sommaire a{color:var(--muted);text-decoration:none;border-bottom:1px dotted var(--line)}
nav.sommaire a:hover{color:var(--accent)}
section{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:18px;display:flex;flex-direction:column;gap:14px;min-width:0;scroll-margin-top:12px}
.defile{overflow-x:auto;min-width:0;-webkit-overflow-scrolling:touch}
.defile svg{display:block}
.onglets{display:flex;flex-wrap:wrap;gap:6px}
.onglets button{font:500 13px var(--f-texte);color:var(--fg);background:var(--surface-2);border:1px solid var(--line);border-radius:999px;padding:4px 11px;cursor:pointer}
.onglets button[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:var(--surface)}
.onglets button .n{font-family:var(--f-mono);font-size:11.5px;opacity:.75;margin-left:5px}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th{font-family:var(--f-titre);text-transform:uppercase;letter-spacing:.06em;font-size:11.5px;color:var(--muted);font-weight:600;text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);white-space:nowrap;background:var(--surface);position:sticky;top:0}
td{padding:7px 8px;border-bottom:1px solid var(--line-2);vertical-align:top}
td.num,th.num{text-align:right;white-space:nowrap}
.tab-haute{max-height:430px;overflow:auto}
.legende{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:13px;color:var(--muted);margin:0}
.legende span{display:inline-flex;align-items:center;gap:6px}
.pastille{width:10px;height:10px;border-radius:3px;display:inline-block;flex:none}
.grille-2{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.4fr);gap:18px}
.grille-3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}
@media (max-width:860px){.grille-2,.grille-3{grid-template-columns:minmax(0,1fr)}}
.cartes{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:10px}
.carte{border:1px solid var(--line);border-left:4px solid var(--info);border-radius:8px;padding:10px 12px;display:flex;flex-direction:column;gap:5px;background:var(--bg);min-width:0}
.carte.majeur{border-left-color:var(--majeur)}.carte.attention{border-left-color:var(--attention)}
.carte .haut{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}
.carte .code{font-family:var(--f-mono);font-size:12px;color:var(--muted)}
.niv{font-family:var(--f-titre);text-transform:uppercase;letter-spacing:.06em;font-size:11px;font-weight:700}
.niv.majeur{color:var(--majeur)}.niv.attention{color:var(--attention)}.niv.info{color:var(--info)}
.carte p{margin:0;font-size:13.5px}.carte .piste{color:var(--muted)}
.barres{display:flex;flex-direction:column;gap:7px}
.barre{display:grid;grid-template-columns:minmax(90px,170px) minmax(0,1fr) auto;gap:10px;align-items:center;font-size:13px}
.barre .nom{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.barre .piste{height:12px;background:var(--surface-2);border-radius:3px;display:flex;overflow:hidden}
.barre .piste i{display:block;height:100%}
.barre .chiffre{font-family:var(--f-mono);font-size:12.5px;color:var(--muted);white-space:nowrap;text-align:right}
ol.journal{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;max-height:520px;overflow:auto;border-top:1px solid var(--line-2)}
ol.journal li{display:grid;grid-template-columns:110px minmax(0,190px) minmax(0,1fr);gap:10px;padding:6px 4px;border-bottom:1px solid var(--line-2);font-size:13px;align-items:baseline}
ol.journal li.essai{color:var(--muted)}
ol.journal .q{font-family:var(--f-mono);font-size:12px;color:var(--muted);white-space:nowrap}
ol.journal .o{font-family:var(--f-mono);font-size:12.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.kv{display:inline-block;font-family:var(--f-mono);font-size:11.5px;background:var(--surface-2);border-radius:4px;padding:0 5px;margin:1px 4px 1px 0;color:var(--muted)}
@media (max-width:560px){ol.journal li{grid-template-columns:88px minmax(0,1fr)}ol.journal li .r{grid-column:1/-1}
  table.cartes-etroites thead{display:none}
  table.cartes-etroites tr{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:4px 12px;padding:10px 0;border-bottom:1px solid var(--line-2)}
  table.cartes-etroites td{border:0;padding:0;text-align:left!important;white-space:normal!important}
  table.cartes-etroites td.large{grid-column:1/-1}
  table.cartes-etroites td[data-l]::before{content:attr(data-l);display:block;font:600 10.5px var(--f-titre);letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}}
ol.journal li.etape .o{font-family:var(--f-titre);font-weight:600}
ol.journal .ph{font-family:var(--f-titre);text-transform:uppercase;letter-spacing:.05em;font-size:11px;font-weight:700;margin-right:6px}
.bascule{display:inline-flex;gap:8px;align-items:center;font-size:13.5px;color:var(--muted);cursor:pointer}
.case{border:1px solid var(--line);border-radius:10px;padding:12px 14px;display:flex;flex-direction:column;gap:8px;min-width:0;background:var(--bg)}
.case .grand{font-family:var(--f-mono);font-size:26px;line-height:1}
.case ul{margin:0;padding-left:18px;display:flex;flex-direction:column;gap:5px;font-size:13.5px}
.case li small{color:var(--muted)}
.vide{color:var(--faint);font-style:italic;font-size:13.5px;margin:0}
footer{color:var(--muted);font-size:13px;display:flex;flex-direction:column;gap:6px}
footer pre{margin:0;background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:10px 12px;overflow-x:auto;font:12.5px/1.6 var(--f-mono);color:var(--fg)}
/* SVG */
svg text{font-family:var(--f-texte);fill:var(--fg)}
svg .ax{font:11px var(--f-mono);fill:var(--muted)}
svg .lane{font:600 11.5px var(--f-titre);letter-spacing:.05em;text-transform:uppercase;fill:var(--muted)}
svg .grille{stroke:var(--line-2);stroke-width:1}
svg .cadre{stroke:var(--line);fill:none}
svg .maint{stroke:var(--accent);stroke-width:1.5;stroke-dasharray:4 3}
svg .maint-t{font:600 10.5px var(--f-mono);fill:var(--accent)}
svg .lbl{font:500 11px var(--f-texte);fill:#fff;pointer-events:none}
.cat-rapport{fill:var(--c-rapport)}.cat-outils{fill:var(--c-outils)}.cat-revue{fill:var(--c-revue)}.cat-sync{fill:var(--c-sync)}
.cat-agents{fill:var(--c-agents)}.cat-attente{fill:var(--c-attente)}.cat-autre{fill:var(--c-autre)}
.bg-rapport{background:var(--c-rapport)}.bg-outils{background:var(--c-outils)}.bg-revue{background:var(--c-revue)}.bg-sync{background:var(--c-sync)}
.bg-agents{background:var(--c-agents)}.bg-attente{background:var(--c-attente)}.bg-autre{background:var(--c-autre)}
.bg-reel{background:var(--reel)}.bg-essai{background:var(--essai)}
svg .ouverte{fill-opacity:.55;stroke-dasharray:3 2;stroke-width:1.2}
svg .ouverte.cat-rapport{stroke:var(--c-rapport)}svg .ouverte.cat-outils{stroke:var(--c-outils)}svg .ouverte.cat-revue{stroke:var(--c-revue)}
svg .ouverte.cat-sync{stroke:var(--c-sync)}svg .ouverte.cat-agents{stroke:var(--c-agents)}svg .ouverte.cat-attente{stroke:var(--c-attente)}svg .ouverte.cat-autre{stroke:var(--c-autre)}
svg .reel{fill:var(--reel)}svg .essai{fill:var(--essai)}
svg .tick{fill:var(--accent)}svg .tick.bloque{fill:var(--bg);stroke:var(--c-attente);stroke-width:1.4}
svg .continu{fill:var(--accent-soft);stroke:var(--accent)}svg .continu.inactif{fill:none;stroke:var(--faint);stroke-dasharray:5 4}
svg .seuil{stroke:var(--majeur);stroke-dasharray:6 4;stroke-width:1.2}
svg .seuil-t{font:500 11px var(--f-mono);fill:var(--majeur)}
svg .pt{stroke:var(--surface);stroke-width:1}
.m-opus{fill:var(--m-opus)}.m-sonnet{fill:var(--m-sonnet)}.m-haiku{fill:var(--m-haiku)}.m-autre{fill:var(--m-autre)}
.bg-m-opus{background:var(--m-opus)}.bg-m-sonnet{background:var(--m-sonnet)}.bg-m-haiku{background:var(--m-haiku)}.bg-m-autre{background:var(--m-autre)}
svg .point-etape{fill:var(--surface);stroke:var(--fg);stroke-width:1.2}
.tete .ligne{display:flex;flex-wrap:wrap;gap:10px 16px;align-items:flex-start;justify-content:space-between}
.reglages{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.langue{display:inline-flex;border:1px solid var(--line);border-radius:999px;overflow:hidden;background:var(--surface)}
.langue button{font:600 12.5px var(--f-titre);letter-spacing:.06em;color:var(--muted);background:transparent;border:0;padding:5px 12px;cursor:pointer}
.langue button[aria-pressed="true"]{background:var(--accent);color:var(--surface)}
.langue button:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
.mode{display:inline-flex;align-items:center;gap:7px;font:500 12.5px var(--f-mono);color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:4px 11px;background:var(--surface)}
.mode::before{content:"";width:8px;height:8px;border-radius:50%;background:var(--faint);flex:none}
.mode.direct{color:var(--accent);border-color:var(--accent)}
.mode.direct::before{background:var(--accent);animation:pouls 2s ease-in-out infinite}
.mode.perdu{color:var(--majeur);border-color:var(--majeur)}.mode.perdu::before{background:var(--majeur);animation:none}
@keyframes pouls{0%,100%{opacity:1}50%{opacity:.25}}
@media (prefers-reduced-motion:reduce){.mode.direct::before{animation:none}}
.grille-4{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}
</style>

<div class="page">
  <header class="tete">
    <div class="ligne">
      <div>
        <p class="sur" data-t="sur">Espace de compétences · flux de travail de Claude</p>
        <h1 data-t="h1">Tableau de bord du flux</h1>
      </div>
      <div class="reglages">
        <span class="mode instantane" id="mode" role="status">Instantané</span>
        <div class="langue" id="langue" role="group" aria-label="Langue"><button type="button" data-lang="fr" aria-pressed="true">FR</button><button type="button" data-lang="en" aria-pressed="false">EN</button></div>
      </div>
    </div>
    <p class="etat" id="etat-au"></p>
    <div class="puces" id="puces"></div>
  </header>
  <nav class="sommaire" aria-label="Sections">
    <a href="#planificateur" data-t="nav_plan">Planificateur</a><a href="#chronologie" data-t="nav_chrono">Chronologie</a><a href="#goulots" data-t="nav_goulots">Goulots</a>
    <a href="#agents" data-t="nav_agents">Agents</a><a href="#outils" data-t="nav_outils">Outils</a><a href="#journal" data-t="nav_journal">Journal</a><a href="#attente" data-t="nav_attente">En attente</a>
  </nav>

  <section id="planificateur">
    <h2><span class="no">01</span><span data-t="plan_t">Planificateur</span></h2>
    <p class="aide" data-t="plan_aide">Les prochaines 24 heures, calculées à l'ouverture de la page dans votre fuseau. Un repère creux signale une exécution qui a besoin du PC alors qu'il est injoignable.</p>
    <div class="defile" id="plan-svg"></div>
    <div class="defile"><table id="tab-plan" class="cartes-etroites"></table></div>
  </section>

  <section id="chronologie">
    <h2><span class="no">02</span><span data-t="chrono_t">Chronologie</span></h2>
    <p class="aide" data-t="chrono_aide">Étapes notées par catégorie, agents en parallèle et activité du journal des outils, par tranche de 10 minutes. Une barre pâle en pointillé est une étape encore ouverte.</p>
    <div class="onglets" id="jours" role="group" aria-label="Jour"></div>
    <div class="defile" id="gantt"></div>
    <p class="legende" id="legende-cat"></p>
  </section>

  <section id="goulots">
    <h2><span class="no">03</span><span data-t="goulots_t">Goulots d'étranglement</span></h2>
    <p class="aide" id="goulots-aide"></p>
    <div class="cartes" id="cartes-goulots"></div>
    <div class="grille-2">
      <div style="display:flex;flex-direction:column;gap:10px;min-width:0"><h3 id="titre-cat">Temps par catégorie</h3><div class="barres" id="barres-cat"></div><p class="aide" id="note-cat"></p></div>
      <div style="display:flex;flex-direction:column;gap:10px;min-width:0"><h3 data-t="vagues_t">Vagues d'agents</h3><div class="tab-haute defile"><table id="tab-vagues" class="cartes-etroites"></table></div></div>
    </div>
  </section>

  <section id="agents">
    <h2><span class="no">04</span><span data-t="agents_t">Agents</span></h2>
    <p class="aide" data-t="agents_aide">Chaque point est un agent : durée et charge de contexte maximale. Au-dessus de la ligne, la charge est à surveiller, car les agents puisent dans le même réservoir de tokens.</p>
    <div class="onglets" id="filtre-agents" role="group" aria-label="Période"></div>
    <div class="defile" id="nuage"></div>
    <p class="legende" id="legende-agents"></p>
  </section>

  <section id="outils">
    <h2><span class="no">05</span><span data-t="outils_t">Activité des outils</span></h2>
    <p class="aide" id="outils-aide"></p>
    <div class="barres" id="barres-outils"></div>
  </section>

  <section id="journal">
    <h2><span class="no">06</span><span data-t="journal_t">Journal</span></h2>
    <label class="bascule"><input type="checkbox" id="avec-essais"> <span data-t="avec_essais">Inclure les essais (bancs et tests)</span></label>
    <ol class="journal" id="liste-journal"></ol>
  </section>

  <section id="attente">
    <h2><span class="no">07</span><span data-t="attente_t">En attente</span></h2>
    <div class="grille-4" id="attentes"></div>
  </section>

  <footer>
    <span class="etiq" data-t="maj">Mettre à jour</span>
    <pre>python3 outils/tableau_de_bord.py etape debut &lt;id&gt; --titre "…" --categorie outils
python3 outils/tableau_de_bord.py etape attente &lt;id&gt; --titre "…" --raison pc
python3 outils/tableau_de_bord.py etape fin &lt;id&gt; [--resultat ok]
python3 outils/tableau_de_bord.py generer</pre>
    <span id="pied"></span>
  </footer>
</div>

<script type="application/json" id="donnees">/*__DONNEES__*/null</script>
<script>
(function(){
"use strict";
const D0 = JSON.parse(document.getElementById('donnees').textContent || 'null');
if (!D0) { document.querySelector('.page').insertAdjacentHTML('beforeend','<p class="vide">Aucune donnée intégrée / no embedded data.</p>'); return; }
let D = D0;
const NS = 'http://www.w3.org/2000/svg';
let MAINT = new Date();

/* ----- langue (FR / EN) */
const TXT = {
fr: {
  sur: 'Espace de compétences · flux de travail de Claude', h1: 'Tableau de bord du flux',
  nav_plan: 'Planificateur', nav_chrono: 'Chronologie', nav_goulots: 'Goulots', nav_agents: 'Agents', nav_outils: 'Outils', nav_journal: 'Journal', nav_attente: 'En attente',
  plan_t: 'Planificateur', plan_aide: "Les prochaines 24 heures, calculées à l'ouverture de la page dans votre fuseau. Un repère creux signale une exécution qui a besoin du PC alors qu'il est injoignable.",
  chrono_t: 'Chronologie', chrono_aide: "Étapes notées par catégorie, agents en parallèle et activité du journal des outils, par tranche de 10 minutes. Une barre pâle en pointillé est une étape encore ouverte.",
  goulots_t: "Goulots d'étranglement", vagues_t: "Vagues d'agents",
  agents_t: 'Agents', agents_aide: "Chaque point est un agent : durée et charge de contexte maximale. Au-dessus de la ligne, la charge est à surveiller, car les agents puisent dans le même réservoir de tokens.",
  outils_t: 'Activité des outils', journal_t: 'Journal', avec_essais: 'Inclure les essais (bancs et tests)', attente_t: 'En attente', maj: 'Mettre à jour',
  langue: 'Langue', direct: 'En direct', direct_maj: 'En direct · relu {h}', direct_perdu: 'Serveur local injoignable · nouvel essai…', instantane: 'Instantané',
  instantane_aide: 'Instantané publié : lancez lancer_tableau_de_bord sur le PC pour le suivi en temps réel.',
  cat: {rapport: 'Rapport', outils: 'Outils', revue: 'Revue', sync: 'Sauvegarde', agents: 'Agents', attente: 'Attente', autre: 'Autre'},
  raison: {pc: 'PC injoignable', utilisateur: "décision de l'utilisateur", agents: 'agents', lmstudio: 'LM Studio', autre: 'autre'},
  statut: {proposee: 'en attente', modification_demandee: 'modification demandée', a_confirmer: 'à confirmer'},
  type: {decision: 'décision', lecon: 'leçon', memoire: 'mémoire', procedure: 'procédure', guide: 'guide', skill: 'skill', organigramme: 'organigramme', methode: 'méthode'},
  phase: {debut: 'début', fin: 'fin', point: 'point', attente: 'attente'}, niveau: {majeur: 'majeur', attention: 'attention', info: 'info'},
  maintenant: 'maintenant', instant: "à l'instant", il_y_a: 'il y a {t}', dans: 'dans {t}', jour_abr: 'j',
  en_cours: 'En cours', aucune_ouverte: 'aucune étape ouverte', decisions: 'Décisions en attente', decisions_s: "propositions à réviser par l'utilisateur",
  prochaine: 'Prochaine tâche', bloquee_p: ' (bloquée)', rien_planifie: 'rien de planifié', tests: 'Tests', aucun_resultat: 'aucun résultat',
  pc: 'PC', injoignable: 'injoignable', depuis: 'depuis {q}', non_signale: 'non signalé', aucune_attente_pc: 'aucune attente « pc » ouverte',
  sauvegardes: 'Sauvegardes', non_confirmes: 'envoi(s) non confirmé(s)', tout_confirme: 'tout est confirmé',
  etat_au: 'Données au {q} ({r}) · heures dans votre fuseau · {e} événements, {s} étapes, {a} agents',
  pied: 'Généré par {o} · planificateur : {p}', absent: 'absent',
  aucun_planif: 'Aucun planificateur (taches/planificateur_vN.json).', plan_aria: 'Prochaines 24 heures du planificateur',
  bloquee: 'bloquée', pc_ko_court: ' (PC injoignable)',
  th_tache: 'Tâche', th_ou: 'Où', th_rythme: 'Rythme', th_prochaine: 'Prochaine', th_etat: 'État',
  en_continu: 'en continu', une_fois: 'une fois', chaque_jour: 'chaque jour à {h} {tz}', chaque_heure: 'chaque heure, aux minutes {m}', toutes: 'toutes les {n} min',
  expr_invalide: 'expression invalide', inactive: 'inactive', bloquee_pc: 'bloquée : PC injoignable', active: 'active',
  aucune_donnee: 'Aucune donnée.', rien_jour: 'Rien ce jour-là.', chrono_aria: 'Chronologie du jour', en_cours_m: 'en cours', reconstitue: 'reconstitué',
  contexte_max: 'contexte max', vague: 'vague', journal_lane: 'Journal', max_10: 'max {n} / 10 min', reels_essais: '{r} réel(s), {e} essai(s)',
  leg_reel: 'journal : réel', leg_essai: 'journal : essais',
  temps_cat: 'Temps par catégorie · {j}', aucune_etape_jour: 'Aucune étape notée ce jour-là.', cumul: 'cumul',
  note_cat_att: 'Attente : {p} % du temps des étapes. ', note_cat: 'Agents : durée murale (temps où au moins un agent travaille) et cumul de tous les agents.',
  goulots_aide: "Règles déterministes appliquées aux données du {j} : {n} constat(s). Seuils : contexte d'agent {c}, traînard ×{t}, attente {a} %.",
  piste: 'Piste : {p}', aucun_goulot: 'Aucun goulot détecté.',
  th_debut: 'Début', th_lot: 'Lot', th_agents: 'Agents', th_duree: 'Durée', th_trainard: 'Traînard', th_contexte: 'Contexte moy. / max', th_sortie: 'Sortie',
  au_dessus: 'agents au-dessus du seuil', tous: 'Tous', aucun_agent: 'Aucun agent.', nuage_aria: "Durée et charge de contexte des agents",
  duree_agent: "durée de l'agent →", charge: 'charge à surveiller · {c}', sortie: 'sortie', appels: "{n} appels d'outils",
  leg_agents: '{n} au-dessus du seuil · durée médiane {d}',
  outils_aide: '{j} : {o} outils, {r} exécutions réelles parmi les 15 plus actifs, {e} essais (bancs et tests marqués CC_BANC).',
  aucune_exec: 'Aucune exécution ce jour-là.', reel: 'réel', essai: 'essai', leg_reels: 'exécutions réelles', leg_essais: 'essais',
  aucun_evt: 'Aucun événement.',
  c_decisions: "Décisions de l'utilisateur", rien_reviser: 'Rien à réviser.', c_sauvegarde: 'Sauvegarde vers le PC',
  pc_inj: 'PC : <strong style="color:var(--majeur)">injoignable</strong> depuis {q}', pc_ok: 'PC : aucune attente « pc » ouverte',
  derniere: 'Dernière sauvegarde complète : {q}', inconnue: 'inconnue', envoi_nc: 'Envoi non confirmé du {q}', copies: '{n} copie(s) à vérifier',
  instantane_sv: 'état relevé dans le cloud ({q})',
  c_attend: 'Ce qui attend', rien: 'Rien.', a_besoin_pc: 'a besoin du PC', utilise_pc: 'utilise le PC', prochaine_q: 'prochaine {q}',
  c_lm: 'Ouvrier LM Studio', lm_absent: 'File absente ici (cloud) : visible sur le PC.', lm_jamais: "Ouvrier jamais lancé.",
  lm_statut: 'Statut : {s}', lm_file: '{a} tâche(s) en file · {l} lot(s) en entrée', lm_traites: '{t} traitée(s) · {e} erreur(s)', lm_modele: 'Modèle : {m}',
  lm_maj: 'État écrit le {q} (heure du PC)',
},
en: {
  sur: "Skills workspace · Claude's workflow", h1: 'Workflow dashboard',
  nav_plan: 'Scheduler', nav_chrono: 'Timeline', nav_goulots: 'Bottlenecks', nav_agents: 'Agents', nav_outils: 'Tools', nav_journal: 'Log', nav_attente: 'Waiting',
  plan_t: 'Scheduler', plan_aide: 'The next 24 hours, computed when the page opens, in your time zone. A hollow tick marks a run that needs the PC while it is unreachable.',
  chrono_t: 'Timeline', chrono_aide: 'Logged steps by category, parallel agents and tool-log activity, in 10-minute slots. A pale dashed bar is a step that is still open.',
  goulots_t: 'Bottlenecks', vagues_t: 'Agent waves',
  agents_t: 'Agents', agents_aide: 'Each dot is an agent: duration and peak context load. Above the line, the load needs watching, because agents draw on the same token pool.',
  outils_t: 'Tool activity', journal_t: 'Log', avec_essais: 'Include trial runs (benches and tests)', attente_t: 'Waiting', maj: 'Update',
  langue: 'Language', direct: 'Live', direct_maj: 'Live · read {h}', direct_perdu: 'Local server unreachable · retrying…', instantane: 'Snapshot',
  instantane_aide: 'Published snapshot: run lancer_tableau_de_bord on the PC for real-time monitoring.',
  cat: {rapport: 'Report', outils: 'Tools', revue: 'Review', sync: 'Backup', agents: 'Agents', attente: 'Waiting', autre: 'Other'},
  raison: {pc: 'PC unreachable', utilisateur: "user's decision", agents: 'agents', lmstudio: 'LM Studio', autre: 'other'},
  statut: {proposee: 'pending', modification_demandee: 'changes requested', a_confirmer: 'to confirm'},
  type: {decision: 'decision', lecon: 'lesson', memoire: 'memory', procedure: 'procedure', guide: 'guide', skill: 'skill', organigramme: 'org chart', methode: 'method'},
  phase: {debut: 'start', fin: 'end', point: 'checkpoint', attente: 'waiting'}, niveau: {majeur: 'major', attention: 'warning', info: 'info'},
  maintenant: 'now', instant: 'just now', il_y_a: '{t} ago', dans: 'in {t}', jour_abr: 'd',
  en_cours: 'In progress', aucune_ouverte: 'no open step', decisions: 'Pending decisions', decisions_s: 'proposals for the user to review',
  prochaine: 'Next task', bloquee_p: ' (blocked)', rien_planifie: 'nothing scheduled', tests: 'Tests', aucun_resultat: 'no result',
  pc: 'PC', injoignable: 'unreachable', depuis: 'since {q}', non_signale: 'not reported', aucune_attente_pc: 'no open “pc” wait',
  sauvegardes: 'Backups', non_confirmes: 'unconfirmed send(s)', tout_confirme: 'all confirmed',
  etat_au: 'Data as of {q} ({r}) · times in your time zone · {e} events, {s} steps, {a} agents',
  pied: 'Generated by {o} · scheduler: {p}', absent: 'missing',
  aucun_planif: 'No scheduler (taches/planificateur_vN.json).', plan_aria: 'Next 24 hours of the scheduler',
  bloquee: 'blocked', pc_ko_court: ' (PC unreachable)',
  th_tache: 'Task', th_ou: 'Where', th_rythme: 'Rhythm', th_prochaine: 'Next', th_etat: 'State',
  en_continu: 'continuous', une_fois: 'once', chaque_jour: 'daily at {h} {tz}', chaque_heure: 'hourly, at minutes {m}', toutes: 'every {n} min',
  expr_invalide: 'invalid expression', inactive: 'inactive', bloquee_pc: 'blocked: PC unreachable', active: 'active',
  aucune_donnee: 'No data.', rien_jour: 'Nothing that day.', chrono_aria: "Day's timeline", en_cours_m: 'ongoing', reconstitue: 'reconstructed',
  contexte_max: 'peak context', vague: 'wave', journal_lane: 'Log', max_10: 'max {n} / 10 min', reels_essais: '{r} real, {e} trial',
  leg_reel: 'log: real', leg_essai: 'log: trials',
  temps_cat: 'Time by category · {j}', aucune_etape_jour: 'No step logged that day.', cumul: 'total',
  note_cat_att: 'Waiting: {p} % of step time. ', note_cat: 'Agents: wall-clock time (at least one agent working) and the total across all agents.',
  goulots_aide: 'Deterministic rules applied to the data of {j}: {n} finding(s). Thresholds: agent context {c}, straggler ×{t}, waiting {a} %.',
  piste: 'Lead: {p}', aucun_goulot: 'No bottleneck detected.',
  th_debut: 'Start', th_lot: 'Batch', th_agents: 'Agents', th_duree: 'Duration', th_trainard: 'Straggler', th_contexte: 'Context avg / max', th_sortie: 'Output',
  au_dessus: 'agents above the threshold', tous: 'All', aucun_agent: 'No agent.', nuage_aria: 'Agent duration and context load',
  duree_agent: 'agent duration →', charge: 'load to watch · {c}', sortie: 'output', appels: '{n} tool calls',
  leg_agents: '{n} above the threshold · median duration {d}',
  outils_aide: '{j}: {o} tools, {r} real runs among the 15 most active, {e} trial runs (benches and tests flagged CC_BANC).',
  aucune_exec: 'No run that day.', reel: 'real', essai: 'trial', leg_reels: 'real runs', leg_essais: 'trial runs',
  aucun_evt: 'No event.',
  c_decisions: "User's decisions", rien_reviser: 'Nothing to review.', c_sauvegarde: 'Backup to the PC',
  pc_inj: 'PC: <strong style="color:var(--majeur)">unreachable</strong> since {q}', pc_ok: 'PC: no open “pc” wait',
  derniere: 'Last full backup: {q}', inconnue: 'unknown', envoi_nc: 'Unconfirmed send of {q}', copies: '{n} copy(ies) to check',
  instantane_sv: 'state read in the cloud ({q})',
  c_attend: 'What is waiting', rien: 'Nothing.', a_besoin_pc: 'needs the PC', utilise_pc: 'uses the PC', prochaine_q: 'next {q}',
  c_lm: 'LM Studio worker', lm_absent: 'No queue here (cloud): visible on the PC.', lm_jamais: 'Worker never started.',
  lm_statut: 'Status: {s}', lm_file: '{a} task(s) queued · {l} batch(es) in the inbox', lm_traites: '{t} done · {e} error(s)', lm_modele: 'Model: {m}',
  lm_maj: 'State written on {q} (PC time)',
}};
/* Textes des goulots, tirés des paramètres calculés (mêmes règles en Python et en JavaScript). */
const GT = {
fr: {
  'G-AG1': p => [`Vague « ${p.libelle} » : un agent traînard`, `${p.n} agents ; le plus lent (${p.trainard}) a duré ${p.max_min} min, la médiane ${p.med_min} min (×${nb(p.ratio, 2)}).`, "Équilibrer les lots : donner moins de travail à l'agent le plus lent, ou couper son lot en deux."],
  'G-AG2': p => ['Charge de contexte élevée chez des agents', `${p.n} agent(s) sur ${p.total} en 7 jours au-dessus de ${p.seuil_k} k tokens ; maximum ${p.max_k} k (${p.description}).`, 'Briefs plus courts et lots plus petits : les agents puisent dans le même réservoir de tokens.'],
  'G-AT1': p => ["Temps d'attente important aujourd'hui", `${p.part_pct} % du temps des étapes du ${jourTexte(p.jour)} est en attente (${p.attente_min} min).`, "Préparer en amont ce qui attend (lots, décisions groupées) et poursuivre une autre tâche pendant l'attente."],
  'G-ET1': p => [`Étape ouverte depuis longtemps : ${p.titre}`, `Ouverte depuis ${nb(p.heures, 1)} h sans point d'étape.`, "Noter un point d'étape (« etape point ») ou la clore."],
  'G-SY1': p => ['Sauvegardes vers le PC non confirmées', `${p.n} envoi(s) non confirmé(s), le plus ancien il y a ${nb(p.age_h, 1)} h${p.pc_injoignable ? ' ; PC injoignable.' : '.'}`, "Au retour du PC : sauvegarde complète (manifeste d'abord), puis « N / N conformes »."],
  'G-PR1': p => ["Décisions de l'utilisateur en attente", `${p.n} proposition(s) ouvertes ; la plus ancienne depuis ${nb(p.jours, 1)} j.`, 'Les regrouper dans une seule revue (index de skills_propositions_a_reviser).'],
  'G-JO1': p => ['Le journal est dominé par les essais', `${p.part_pct} % des ${p.n} événements du ${jourTexte(p.jour)} viennent des tests et des bancs.`, "Les tests complets tournent souvent : les réserver aux adoptions et à la fin d'étape ; lancer une suite seule sinon."],
  'G-OU1': p => ['Outil le plus long (durées mesurées)', `${p.outil} : ${nb(p.secondes, 1)} s cumulées ; ${p.n_outils} outil(s) seulement mesurent leur durée.`, 'Mesurer la durée dans les autres outils (mesures.duree_s) pour comparer.'],
  'G-TE1': p => ['Derniers tests non conformes', `${p.echecs} échec(s) sur ${p.total}.`, 'Corriger avant toute adoption.'],
  'G-LM1': p => ['Lots LM Studio en attente : ouvrier arrêté', `${p.lots} lot(s) dans la file d'entrée ; ouvrier ${p.jamais ? 'jamais lancé' : 'arrêté' + (p.raison ? ' (' + p.raison + ')' : '')}.`, "Lancer l'ouvrier (lancer_worker_lmstudio, double-clic) : les lots partent seuls, regroupés par modèle."],
  'G-LM2': p => ["LM Studio injoignable pour l'ouvrier", `Ouvrier en attente de LM Studio ; ${p.en_attente} tâche(s) en file.`, "Démarrer le serveur de LM Studio (onglet Developer, Start Server) ; l'ouvrier reprend seul."],
},
en: {
  'G-AG1': p => [`Wave “${p.libelle}”: one straggling agent`, `${p.n} agents; the slowest (${p.trainard}) took ${p.max_min} min, the median ${p.med_min} min (×${nb(p.ratio, 2)}).`, 'Balance the batches: give the slowest agent less work, or split its batch in two.'],
  'G-AG2': p => ['High context load in agents', `${p.n} agent(s) out of ${p.total} in 7 days above ${p.seuil_k} k tokens; peak ${p.max_k} k (${p.description}).`, 'Shorter briefs and smaller batches: agents draw on the same token pool.'],
  'G-AT1': p => ['Significant waiting time today', `${p.part_pct} % of step time on ${jourTexte(p.jour)} is spent waiting (${p.attente_min} min).`, 'Prepare what is waited on in advance (batches, grouped decisions) and work on another task meanwhile.'],
  'G-ET1': p => [`Step open for a long time: ${p.titre}`, `Open for ${nb(p.heures, 1)} h with no checkpoint.`, 'Log a checkpoint (“etape point”) or close it.'],
  'G-SY1': p => ['Unconfirmed backups to the PC', `${p.n} unconfirmed send(s), the oldest ${nb(p.age_h, 1)} h ago${p.pc_injoignable ? '; PC unreachable.' : '.'}`, 'When the PC is back: full backup (manifest first), then “N / N conformes”.'],
  'G-PR1': p => ["User's decisions pending", `${p.n} open proposal(s); the oldest for ${nb(p.jours, 1)} d.`, 'Group them in a single review (index of skills_propositions_a_reviser).'],
  'G-JO1': p => ['The log is dominated by trial runs', `${p.part_pct} % of the ${p.n} events on ${jourTexte(p.jour)} come from tests and benches.`, 'Full test runs are frequent: keep them for adoptions and end of step; run a single suite otherwise.'],
  'G-OU1': p => ['Longest tool (measured durations)', `${p.outil}: ${nb(p.secondes, 1)} s in total; only ${p.n_outils} tool(s) measure their duration.`, 'Measure duration in the other tools (mesures.duree_s) to compare.'],
  'G-TE1': p => ['Latest tests not compliant', `${p.echecs} failure(s) out of ${p.total}.`, 'Fix before any adoption.'],
  'G-LM1': p => ['LM Studio batches waiting: worker stopped', `${p.lots} batch(es) in the inbox; worker ${p.jamais ? 'never started' : 'stopped' + (p.raison ? ' (' + p.raison + ')' : '')}.`, 'Start the worker (lancer_worker_lmstudio, double-click): batches run by themselves, grouped by model.'],
  'G-LM2': p => ['LM Studio unreachable for the worker', `Worker waiting for LM Studio; ${p.en_attente} task(s) queued.`, 'Start the LM Studio server (Developer tab, Start Server); the worker resumes by itself.'],
}};
function lireLangue() { try { const v = localStorage.getItem('tdb-langue'); if (v === 'fr' || v === 'en') return v; } catch (e) {} return 'fr'; }
let LANG = lireLangue();
function t(k, p) { const v = (TXT[LANG] && TXT[LANG][k] !== undefined) ? TXT[LANG][k] : TXT.fr[k]; if (typeof v !== 'string') return v;
  return p ? v.replace(/\{(\w+)\}/g, (m, x) => (p[x] === undefined ? m : p[x])) : v; }
const LOC = () => (LANG === 'en' ? 'en' : 'fr');
let fH, fJ, fJL;
function formats() { fH = new Intl.DateTimeFormat(LOC(), {hour: '2-digit', minute: '2-digit'}); fJ = new Intl.DateTimeFormat(LOC(), {weekday: 'short', day: 'numeric', month: 'short'});
  fJL = new Intl.DateTimeFormat(LOC(), {day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC'}); }
formats();
function nb(x, d) { if (x == null) return '–'; const s = String(AG.arr(x, d || 0)); return LANG === 'fr' ? s.replace('.', ',') : s; }
const jourTexte = j => fJL.format(new Date(j + 'T12:00:00Z'));
const champ = (o, k) => (LANG === 'en' && o[k + '_en'] != null ? o[k + '_en'] : o[k]);
function textesGoulot(g) { const f = (GT[LANG] || GT.fr)[g.code]; if (f && g.params) { try { return f(g.params); } catch (e) {} } return [g.titre || g.code, g.preuve || '', g.piste || '']; }

const $ = s => document.querySelector(s);
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pad = n => String(n).padStart(2, '0');
const T = s => new Date(s);
const jourLocal = d => { const x = new Date(d); return x.getFullYear() + '-' + pad(x.getMonth() + 1) + '-' + pad(x.getDate()); };
const debutJour = k => { const [a, m, j] = k.split('-').map(Number); return new Date(a, m - 1, j); };
const heure = d => fH.format(new Date(d));
const quand = d => (jourLocal(d) === jourLocal(MAINT) ? '' : fJ.format(new Date(d)) + ' · ') + heure(d);
function duree(s) { s = Math.max(0, Math.round(s)); if (s < 60) return s + ' s'; if (s < 3600) return Math.round(s / 60) + ' min';
  const h = Math.floor(s / 3600), m = Math.round((s % 3600) / 60); return h + ' h ' + pad(m); }
function tok(n) { if (n == null) return '–'; if (n >= 1e6) return nb(n / 1e6, 1) + ' M'; if (n >= 1000) return Math.round(n / 1000) + ' k'; return String(n); }
function rel(d) { const m = Math.round((MAINT - new Date(d)) / 60000), f = m < 0, a = Math.abs(m);
  const x = a < 1 ? null : a < 60 ? a + ' min' : a < 1440 ? Math.round(a / 60) + ' h' : Math.round(a / 1440) + ' ' + t('jour_abr');
  return x == null ? t('instant') : t(f ? 'dans' : 'il_y_a', {t: x}); }
function S(tag, at, parent) { const e = document.createElementNS(NS, tag); for (const k in (at || {})) e.setAttribute(k, at[k]); if (parent) parent.appendChild(e); return e; }
function titre(e, x) { S('title', {}, e).textContent = x; return e; }
function largeur(sel, min) { const c = $(sel); return Math.max(min, Math.floor((c.clientWidth || c.parentElement.clientWidth || 900))); }
const famille = m => !m ? 'autre' : /opus/.test(m) ? 'opus' : /sonnet/.test(m) ? 'sonnet' : /haiku/.test(m) ? 'haiku' : 'autre';

/*CRON-DEBUT*/
function champCron(s, lo, hi) { const v = new Set();
  for (const part of s.split(',')) { const m = part.match(/^(\*|\d+(?:-\d+)?)(?:\/(\d+))?$/); if (!m) throw new Error('champ ' + part);
    const pas = +(m[2] || 1); let a, b;
    if (m[1] === '*') { a = lo; b = hi; } else if (m[1].indexOf('-') >= 0) { [a, b] = m[1].split('-').map(Number); } else { a = b = +m[1]; if (m[2]) b = hi; }
    if (a < lo || b > hi || a > b || pas < 1) throw new Error('bornes ' + part);
    for (let i = a; i <= b; i += pas) v.add(i); }
  return v; }
function analyserCron(expr) { let e = expr.trim(), tz = 'UTC'; const m = e.match(/^CRON_TZ=(\S+)\s+(.*)$/); if (m) { tz = m[1]; e = m[2]; }
  const p = e.split(/\s+/); if (p.length !== 5) throw new Error('cron ' + expr);
  return {tz, mi: champCron(p[0], 0, 59), h: champCron(p[1], 0, 23), dom: champCron(p[2], 1, 31), mo: champCron(p[3], 1, 12),
    dow: new Set([...champCron(p[4], 0, 7)].map(d => d === 7 ? 0 : d)), domE: p[2] === '*', dowE: p[4] === '*'}; }
const FMT_TZ = {};
function partiesCron(d, tz) { if (tz === 'UTC') return {mi: d.getUTCMinutes(), h: d.getUTCHours(), j: d.getUTCDate(), mo: d.getUTCMonth() + 1, js: d.getUTCDay()};
  const f = FMT_TZ[tz] || (FMT_TZ[tz] = new Intl.DateTimeFormat('en-US', {timeZone: tz, hourCycle: 'h23', minute: 'numeric', hour: 'numeric', day: 'numeric', month: 'numeric', weekday: 'short'}));
  const o = {}; for (const x of f.formatToParts(d)) o[x.type] = x.value;
  return {mi: +o.minute, h: (+o.hour) % 24, j: +o.day, mo: +o.month, js: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].indexOf(o.weekday)}; }
function correspondCron(C, P) { if (!C.mi.has(P.mi) || !C.h.has(P.h) || !C.mo.has(P.mo)) return false;
  const jd = C.dom.has(P.j), js = C.dow.has(P.js); return (C.domE || C.dowE) ? (jd && js) : (jd || js); }
function prochainesCron(expr, depuis, n, horizonMin) { const C = analyserCron(expr); let t = Math.floor(depuis.getTime() / 60000) * 60000; const R = [];
  for (let i = 0; i < (horizonMin || 8 * 1440); i++) { t += 60000; const d = new Date(t); if (correspondCron(C, partiesCron(d, C.tz))) { R.push(d); if (R.length >= (n || 5)) break; } }
  return R; }
/*CRON-FIN*/

/*AGREGER-DEBUT*/
/* Agrégateur du mode direct : même logique que collecter() de tableau_de_bord (Python), appliquée dans le navigateur aux fichiers
   bruts servis par serveur_tableau_de_bord. Les tests comparent sa sortie à celle de collecter() sur les mêmes fichiers. */
const AG = (function () {
  const OUTIL = 'tableau_de_bord';
  const CLES_TEXTE = ['verdict', 'statut', 'mode', 'commande', 'phase', 'outil', 'cible'];
  const cmp = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
  const minA = L => L.reduce((m, x) => (m === undefined || x < m ? x : m), undefined);
  const maxA = L => L.reduce((m, x) => (m === undefined || x > m ? x : m), undefined);
  const somme = L => L.reduce((m, x) => m + x, 0);
  function arr(x, d) { if (!d) return Math.floor(x + 0.5); const k = Math.pow(10, d); return Math.floor(x * k + 0.5) / k; }
  const nombre = v => typeof v === 'number' && isFinite(v);
  function vrai(v) { if (v == null || v === false || v === 0 || v === '') return false; if (Array.isArray(v)) return v.length > 0;
    if (typeof v === 'object') return Object.keys(v).length > 0; return true; }
  function isoN(s) { let x = String(s).trim().replace(' ', 'T'); if (!/(Z|[+-]\d\d:?\d\d)$/.test(x)) x += 'Z';
    const d = new Date(x); if (isNaN(d.getTime())) throw new Error('date invalide : ' + s); return isoMs(d.getTime()); }
  function isoMs(t) { return new Date(Math.floor(t / 1000) * 1000).toISOString().replace(/\.\d{3}Z$/, 'Z'); }
  const ms = s => Date.parse(isoN(s));
  const estEssai = e => vrai((e.donnees || {}).banc);
  const longueur = s => [...s].length;

  function resume(e) { const R = {}, d = e.donnees || {};
    for (const k of Object.keys(d).sort(cmp)) { if (k === 'banc' || k === 'mesures') continue; const v = d[k];
      if (typeof v === 'boolean' || typeof v === 'number') R[k] = v;
      else if (typeof v === 'string' && CLES_TEXTE.indexOf(k) >= 0 && longueur(v) <= 40) R[k] = v;
      else if (Array.isArray(v)) R[k] = v.length + ' él.';
      else if (v && typeof v === 'object') R[k] = Object.keys(v).length + ' él.';
      if (Object.keys(R).length >= 4) break; }
    return R; }

  function etapesDe(E, avec) {
    const S = new Map();
    const L = E.filter(e => e.outil === OUTIL && e.type === 'etape' && (avec || !estEssai(e)))
      .map((e, i) => ({e, k1: e.donnees.quand || e.date, k2: e.date, i})).sort((a, b) => cmp(a.k1, b.k1) || cmp(a.k2, b.k2) || a.i - b.i);
    for (const {e} of L) {
      const d = e.donnees, q = isoN(d.quand || e.date), ph = d.phase, id = d.id === undefined ? null : d.id;
      if (!S.has(id)) S.set(id, {id, titre: null, categorie: 'autre', raison: null, debut: null, fin: null, points: [], notes: [], tokens: 0,
        resultat: null, source: 'source' in d ? d.source : 'direct'});
      const s = S.get(id);
      if (ph === 'debut' || ph === 'attente') { s.debut = s.debut ? minA([s.debut, q]) : q; s.titre = d.titre || s.titre;
        s.categorie = ph === 'attente' ? 'attente' : (d.categorie || s.categorie); s.raison = d.raison || s.raison; }
      else if (ph === 'fin') { s.fin = q; s.resultat = d.resultat || 'ok'; }
      else if (ph === 'point') s.points.push({quand: q, note: 'note' in d ? d.note : ''});
      if (vrai(d.note) && ph !== 'point') s.notes.push(d.note);
      if (vrai(d.tokens)) s.tokens += Math.trunc(Number(d.tokens));
    }
    const R = [...S.values()];
    for (const s of R) { s.titre = s.titre || s.id;
      if (!s.debut) s.debut = minA(s.points.map(p => p.quand).concat(s.fin ? [s.fin] : []));
      s.duree_s = s.fin ? Math.trunc((ms(s.fin) - ms(s.debut)) / 1000) : null; }
    return R.sort((a, b) => cmp(a.debut, b.debut)); }

  function prefixe(D) { if (!D.length) return ''; let p = minA(D); const q = maxA(D); let i = 0;
    while (i < p.length && i < q.length && p[i] === q[i]) i++; return p.slice(0, i); }
  function libelle(D) { if (D.length === 1) return D[0] || 'agent';
    let p = prefixe(D);
    if (!D.every(d => d.startsWith(p + ' ') || d === p) && p.indexOf(' ') >= 0) p = p.slice(0, p.lastIndexOf(' '));
    p = p.replace(/^[ \-–:·(]+|[ \-–:·(]+$/g, '');
    return longueur(p) >= 4 ? p : `${D[0] || 'agent'} (+${D.length - 1})`; }
  function mediane(L) { const s = L.slice().sort((a, b) => a - b), n = s.length; return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2; }
  function vagues(A0, S) {
    const A = A0.slice().sort((a, b) => cmp(a.debut, b.debut)), V = [];
    for (const a of A) { const w = V[V.length - 1];
      if (w && (ms(a.debut) - ms(w[w.length - 1].debut)) / 1000 <= S.ecart_vague_s) w.push(a); else V.push([a]); }
    const R = [];
    V.forEach((v, i) => {
      const D = v.map(x => x.duree_s), med = mediane(D); let lent = v[0]; for (const x of v) if (x.duree_s > lent.duree_s) lent = x;
      const deb = minA(v.map(x => x.debut)), fin = maxA(v.map(x => x.fin)), mx = Math.max(...D), modeles = {};
      for (const x of v) { const m = x.modele || '?'; modeles[m] = (modeles[m] || 0) + 1; }
      R.push({id: 'V' + String(i + 1).padStart(3, '0'), libelle: libelle(v.map(x => x.description)), debut: deb, fin, n: v.length,
        mur_s: Math.trunc((ms(fin) - ms(deb)) / 1000), somme_s: somme(D), mediane_s: Math.trunc(med), max_s: mx,
        ratio: med ? arr(mx / med, 2) : null, trainard: lent.description, contexte_moyen: Math.trunc(somme(v.map(x => x.contexte_max)) / v.length),
        contexte_max: Math.max(...v.map(x => x.contexte_max)), sortie: somme(v.map(x => x.sortie)), traites: somme(v.map(x => x.traites)),
        lourds: v.filter(x => x.contexte_max > S.contexte_agent).length, modeles, agents: v.map(x => x.id)});
      for (const x of v) x.vague = R[R.length - 1].id; });
    return R; }

  function planificateur(F, analyser) {
    if (!F || !F.contenu) return {source: null, taches: [], erreurs: []};
    const P = F.contenu, T = [], Er = [];
    for (const t0 of (P.taches || [])) { const t = Object.assign({}, t0);
      if (t.cron) { try { analyser(t.cron); } catch (e) { Er.push(`${t.id} : ${e.message}`); t.cron_invalide = true; } }
      T.push(t); }
    return {source: F.source, note: P.note === undefined ? null : P.note, taches: T, erreurs: Er}; }

  const CLOS = ['acceptee', 'refusee', 'remplacee', 'retiree', 'modification_demandee', 'a_confirmer'];
  function statutProposition(P) { const E = (P.evenements || []).map(e => e.evenement);
    for (let i = E.length - 1; i >= 0; i--) if (CLOS.indexOf(E[i]) >= 0) return E[i];
    return E.length ? 'proposee' : '?'; }
  function attentes(Et, F, sauvegardes) {
    const R = {propositions: [], sauvegardes: sauvegardes || {non_confirmees: [], derniere_complete: null, source: null},
      pc: {injoignable: false, depuis: null, etape: null}, etapes: []};
    const Reg = (F && F.contenu && F.contenu.propositions) || {};
    for (const pid of Object.keys(Reg).sort(cmp)) { const P = Reg[pid], st = statutProposition(P);
      if (['proposee', 'modification_demandee', 'a_confirmer'].indexOf(st) >= 0) {
        const dates = (P.evenements || []).map(e => e.date).filter(vrai);
        R.propositions.push({id: pid, type: P.type === undefined ? null : P.type, objet: [...String(P.objet || pid)].slice(0, 110).join(''), statut: st,
          depuis: dates.length ? isoN(minA(dates)) : null}); } }
    for (const s of Et) if (s.categorie === 'attente' && !s.fin) {
      R.etapes.push({id: s.id, titre: s.titre, raison: s.raison, depuis: s.debut});
      if (s.raison === 'pc') R.pc = {injoignable: true, depuis: s.debut, etape: s.id}; }
    return R; }

  function goulots(Et, A, V, E, att, tests, ref, lm, S) {
    const G = [], g = (code, niveau, params) => G.push({code, niveau, params});
    for (const v of V.slice(-6)) if (v.n >= 3 && v.ratio && v.ratio >= S.trainard)
      g('G-AG1', 'attention', {libelle: v.libelle, n: v.n, trainard: v.trainard, max_min: Math.floor(v.max_s / 60), med_min: Math.floor(v.mediane_s / 60), ratio: v.ratio});
    const rec = A.filter(a => (ref - ms(a.debut)) / 1000 <= 7 * 86400), lourds = rec.filter(a => a.contexte_max > S.contexte_agent);
    if (lourds.length) { let top = lourds[0]; for (const a of lourds) if (a.contexte_max > top.contexte_max) top = a;
      g('G-AG2', 'attention', {n: lourds.length, total: rec.length, seuil_k: Math.floor(S.contexte_agent / 1000), max_k: Math.floor(top.contexte_max / 1000), description: top.description}); }
    const jour = isoMs(ref).slice(0, 10), Ej = Et.filter(s => s.debut.slice(0, 10) === jour);
    const duree = s => ((s.fin ? ms(s.fin) : ref) - ms(s.debut)) / 1000;
    let tot = 0, att_s = 0;
    for (const s of Ej) if (s.categorie !== 'attente') tot += duree(s);
    for (const s of Ej) if (s.categorie === 'attente') att_s += duree(s);
    if (tot + att_s > 0 && att_s / (tot + att_s) >= S.part_attente) { const part = att_s / (tot + att_s);
      g('G-AT1', part >= S.part_attente_majeure ? 'majeur' : 'attention', {part_pct: arr(100 * part), jour, attente_min: Math.floor(att_s / 60)}); }
    for (const s of Et) if (!s.fin && s.categorie !== 'attente' && duree(s) / 3600 >= S.etape_ouverte_h && !s.points.length)
      g('G-ET1', 'info', {titre: s.titre, heures: arr(duree(s) / 3600, 1)});
    const nc = att.sauvegardes.non_confirmees || [];
    if (nc.length) { const age = (ref - ms(nc[0].quand)) / 1000 / 3600;
      g('G-SY1', age >= 12 ? 'majeur' : 'attention', {n: nc.length, age_h: arr(age, 1), pc_injoignable: !!att.pc.injoignable}); }
    const P = att.propositions;
    if (P.length) { const ages = P.filter(p => p.depuis).map(p => (ref - ms(p.depuis)) / 1000 / 86400), vieux = ages.length ? Math.max(...ages) : 0;
      g('G-PR1', vieux >= S.proposition_jours ? 'attention' : 'info', {n: P.length, jours: arr(vieux, 1)}); }
    const Ed = E.filter(e => e.date.slice(0, 10) === jour);
    if (Ed.length) { const pe = Ed.filter(estEssai).length / Ed.length;
      if (pe >= S.part_essais) g('G-JO1', 'info', {part_pct: arr(100 * pe), n: Ed.length, jour}); }
    const du = new Map();
    for (const e of E) { const m = (e.donnees || {}).mesures || {}; if (nombre(m.duree_s) && !estEssai(e)) du.set(e.outil, (du.get(e.outil) || 0) + m.duree_s); }
    if (du.size) { let o = null, s = -Infinity; for (const [k, v] of du) if (v > s) { o = k; s = v; } g('G-OU1', 'info', {outil: o, secondes: arr(s, 1), n_outils: du.size}); }
    const te = tests[tests.length - 1];
    if (te && te.verdict != null && te.verdict !== 'conforme') g('G-TE1', 'majeur', {echecs: te.unitaires_echecs, total: te.unitaires});
    if (lm) { const et = lm.etat || null, st = et ? et.statut : undefined, n = lm.lots_entree || 0;
      if (n && (!vrai(et) || String(st || '').slice(0, 3) === 'arr')) g('G-LM1', 'attention', {lots: n, jamais: !vrai(et), raison: et && et.raison_arret !== undefined ? et.raison_arret : null});
      if (st === 'attente de LM Studio') g('G-LM2', 'attention', {en_attente: (et && et.en_attente) || 0}); }
    const ordre = {majeur: 0, attention: 1, info: 2};
    return G.sort((a, b) => ordre[a.niveau] - ordre[b.niveau] || cmp(a.code, b.code)); }

  function agreger(B, conf) {
    const S = conf.seuils, analyser = conf.analyserCron;
    const Tout = (B.evenements || []).filter(e => e && typeof e === 'object' && !Array.isArray(e) && vrai(e.date) && vrai(e.outil));
    for (const e of Tout) if (!('donnees' in e)) e.donnees = {};
    const Et = etapesDe(Tout, !!conf.avec_essais), E = Tout.filter(e => e.outil !== OUTIL);
    const cache = (B.agents && B.agents.contenu && B.agents.contenu.agents) || {};
    const A = Object.values(cache).slice().sort((a, b) => cmp(a.debut, b.debut)).map(a => Object.assign({}, a));
    const V = vagues(A, S);
    for (const a of A) { delete a.taille; delete a.mtime; }
    const act = new Map(), ess = new Map(), H = new Map(), tests = [];
    for (const e of E) {
      const t = e.date, b = t.slice(0, 15) + '0:00Z', hh = t.slice(0, 13);
      if (!H.has(hh)) H.set(hh, new Map()); const Ho = H.get(hh); if (!Ho.has(e.outil)) Ho.set(e.outil, [0, 0, 0.0]); const x = Ho.get(e.outil);
      if (estEssai(e)) { ess.set(b, (ess.get(b) || 0) + 1); x[1] += 1; } else { act.set(b, (act.get(b) || 0) + 1); x[0] += 1; }
      const m = e.donnees.mesures || {};
      if (nombre(m.duree_s)) x[2] = arr(x[2] + m.duree_s, 2);
      if (e.outil === 'tester_outils' && e.type === 'tests') { const d = e.donnees, v = k => (d[k] === undefined ? null : d[k]);
        tests.push({quand: t, unitaires: v('unitaires'), unitaires_echecs: v('unitaires_echecs'), fumee_echecs: v('fumee_echecs'), verdict: v('verdict'), complet: v('complet'), candidat: v('candidat')}); }
    }
    const hors = E.slice().sort((a, b) => cmp(a.date, b.date));
    const choisis = hors.filter(e => !estEssai(e)).slice(-150).concat(hors.filter(estEssai).slice(-80));
    const rec = choisis.map(e => ({quand: e.date, outil: e.outil, version: e.version === undefined ? null : e.version, type: e.type === undefined ? null : e.type,
      essai: estEssai(e), resume: resume(e)}));
    for (const s of Et) {
      rec.push({quand: s.debut, etape: s.id, phase: s.categorie === 'attente' ? 'attente' : 'debut', titre: s.titre, categorie: s.categorie, source: s.source});
      for (const p of s.points) rec.push({quand: p.quand, etape: s.id, phase: 'point', titre: s.titre, note: p.note, categorie: s.categorie, source: s.source});
      if (s.fin) rec.push({quand: s.fin, etape: s.id, phase: 'fin', titre: s.titre, resultat: s.resultat, categorie: s.categorie, source: s.source}); }
    rec.sort((a, b) => cmp(a.quand, b.quand));
    const dates = E.map(e => e.date).concat(Et.map(s => s.fin || s.debut), [].concat(...Et.map(s => s.points.map(p => p.quand))), A.map(a => a.fin));
    const ref = dates.length ? ms(maxA(dates)) : Math.floor(Date.now() / 1000) * 1000;
    const att = attentes(Et, B.registre, conf.sauvegardes), P = planificateur(B.planificateur, analyser);
    const lm = B.lmstudio ? B.lmstudio.contenu : null;
    const cles = [...new Set([...act.keys(), ...ess.keys()])].sort(cmp);
    const OH = {}; for (const hh of [...H.keys()].sort(cmp)) { const o = {}; for (const k of [...H.get(hh).keys()].sort(cmp)) o[k] = H.get(hh).get(k); OH[hh] = o; }
    return {outil: conf.outil, etat_au: isoMs(ref), seuils: S, categories: conf.categories, etapes: Et, agents: A, vagues: V,
      activite: cles.map(b => [b, act.get(b) || 0, ess.get(b) || 0]), outils_heure: OH, journal_recent: rec, tests: tests.slice(-30),
      planificateur: P, attentes: att, goulots: goulots(Et, A, V, E, att, tests, ref, lm, S), lmstudio: lm,
      totaux: {evenements: E.length, essais: E.filter(estEssai).length, etapes: Et.length, agents: A.length, vagues: V.length}}; }

  /* Lecture de la réponse du serveur : une ligne par enregistrement, champs séparés par des tabulations. */
  function lireBrut(texte, B) {
    let meta = null, nouveaux = 0, changes = 0;
    for (const ligne of texte.split('\n')) { if (!ligne) continue;
      const i = ligne.indexOf('\t'), type = ligne.slice(0, i);
      if (type === 'M') { try { meta = JSON.parse(ligne.slice(i + 1)); } catch (e) { meta = null; } }
      else if (type === 'E') { const j = ligne.indexOf('\t', i + 1), cle = ligne.slice(i + 1, j);
        if (B.cles.has(cle)) continue;
        try { B.evenements.push(JSON.parse(ligne.slice(j + 1))); B.cles.add(cle); nouveaux++; } catch (e) { B.illisibles = (B.illisibles || 0) + 1; B.cles.add(cle); } }
      else if (type === 'F') { const j = ligne.indexOf('\t', i + 1), k = ligne.indexOf('\t', j + 1), nom = ligne.slice(i + 1, j), source = ligne.slice(j + 1, k);
        try { B[nom] = {source, contenu: JSON.parse(ligne.slice(k + 1))}; changes++; } catch (e) { B.illisibles = (B.illisibles || 0) + 1; } } }
    return {meta, nouveaux, changes}; }
  function nouveauBrut() { return {evenements: [], cles: new Set(), planificateur: null, registre: null, agents: null, lmstudio: null, illisibles: 0}; }

  return {agreger, lireBrut, nouveauBrut, arr, isoN};
})();
/*AGREGER-FIN*/

let PC_KO = false, TACHES = [];
function prealable() { PC_KO = !!(D.attentes && D.attentes.pc && D.attentes.pc.injoignable); TACHES = (D.planificateur && D.planificateur.taches) || []; }
function occurrences(x, depuis, fin) {
  if (x.cron && !x.cron_invalide) { try { return prochainesCron(x.cron, depuis, 400, Math.ceil((fin - depuis) / 60000)); } catch (e) { return []; } }
  if (x.quand) { const q = T(x.quand); return q > depuis && q <= fin ? [q] : []; }
  return []; }
function rythme(x) {
  if (x.continu) return t('en_continu');
  if (x.quand && !x.cron) return t('une_fois');
  const e = (x.cron || '').replace(/^CRON_TZ=\S+\s+/, ''), mt = (x.cron || '').match(/^CRON_TZ=(\S+)/), tz = mt ? mt[1] : 'UTC';
  let m;
  if ((m = e.match(/^(\d+) (\d+) \* \* \*$/))) return t('chaque_jour', {h: pad(m[2]) + ':' + pad(m[1]), tz});
  if ((m = e.match(/^([\d,]+) \* \* \* \*$/))) return t('chaque_heure', {m: m[1].split(',').join(', ')});
  if ((m = e.match(/^\*\/(\d+) \* \* \* \*$/))) return t('toutes', {n: m[1]});
  return e || '–'; }
function etatTache(x) {
  if (x.cron_invalide) return t('expr_invalide');
  if (x.actif === false) return champ(x, 'etat') || t('inactive');
  if (x.besoin_pc && PC_KO) return t('bloquee_pc');
  return champ(x, 'etat') || t('active'); }

function chips() {
  const P = [], ouv = D.etapes.filter(s => !s.fin && s.categorie !== 'attente');
  P.push({e: t('en_cours'), v: String(ouv.length), s: ouv.length ? ouv[ouv.length - 1].titre : t('aucune_ouverte')});
  const att = D.attentes || {}, np = (att.propositions || []).length;
  P.push({e: t('decisions'), v: String(np), s: t('decisions_s'), c: np ? '' : 'ok'});
  let best = null;
  for (const x of TACHES) { if (x.actif === false) continue; const o = occurrences(x, MAINT, new Date(MAINT.getTime() + 8 * 864e5)); if (o.length && (!best || o[0] < best.d)) best = {x, d: o[0]}; }
  P.push(best ? {e: t('prochaine'), v: heure(best.d), s: champ(best.x, 'nom') + (best.x.besoin_pc && PC_KO ? t('bloquee_p') : ''), c: best.x.besoin_pc && PC_KO ? 'alerte' : ''} : {e: t('prochaine'), v: '–', s: t('rien_planifie')});
  const te = (D.tests || [])[D.tests.length - 1];
  P.push(te ? {e: t('tests'), v: String(te.unitaires == null ? '?' : te.unitaires), s: (te.verdict || '?') + ' · ' + quand(te.quand), c: te.verdict === 'conforme' ? 'ok' : 'alerte'} : {e: t('tests'), v: '–', s: t('aucun_resultat')});
  P.push(PC_KO ? {e: t('pc'), v: t('injoignable'), s: t('depuis', {q: quand(att.pc.depuis)}), c: 'alerte'} : {e: t('pc'), v: t('non_signale'), s: t('aucune_attente_pc')});
  const nc = ((att.sauvegardes || {}).non_confirmees || []).length;
  P.push({e: t('sauvegardes'), v: String(nc), s: nc ? t('non_confirmes') : t('tout_confirme'), c: nc ? 'alerte' : 'ok'});
  $('#puces').innerHTML = P.map(p => `<div class="puce ${p.c || ''}"><span class="etiq">${esc(p.e)}</span><span class="val">${esc(p.v)}</span><span class="sous" title="${esc(p.s)}">${esc(p.s)}</span></div>`).join('');
  $('#etat-au').innerHTML = esc(t('etat_au', {q: '\u0001', r: rel(D.etat_au), e: D.totaux.evenements, s: D.totaux.etapes, a: D.totaux.agents}))
    .replace('\u0001', `<span class="mono">${esc(fJ.format(T(D.etat_au)))} · ${esc(heure(D.etat_au))}</span>`);
  $('#pied').textContent = t('pied', {o: D.outil, p: (D.planificateur && D.planificateur.source) || t('absent')});
}

function planificateur() {
  const box = $('#plan-svg'); box.innerHTML = '';
  if (!TACHES.length) { box.innerHTML = `<p class="vide">${esc(t('aucun_planif'))}</p>`; $('#tab-plan').innerHTML = ''; return; }
  const W = largeur('#plan-svg', 320), G = W < 560 ? 126 : 210, Dr = 14, rh = 30, top = 26, h = top + TACHES.length * rh + 8, nmax = W < 560 ? 17 : 30;
  const t0 = MAINT, t1 = new Date(MAINT.getTime() + 864e5), x = d => G + (W - G - Dr) * (d - t0) / (t1 - t0);
  const s = S('svg', {width: W, height: h, viewBox: `0 0 ${W} ${h}`, role: 'img', 'aria-label': t('plan_aria')}, box);
  const g0 = new Date(t0); g0.setMinutes(0, 0, 0);
  for (let d = new Date(g0.getTime() + 3600e3); d < t1; d = new Date(d.getTime() + 3600e3)) {
    const xx = x(d); if (d.getHours() % (W < 560 ? 6 : 3)) continue;
    S('line', {x1: xx, x2: xx, y1: top - 6, y2: h - 6, class: 'grille'}, s);
    if (xx - G > 78 && W - Dr - xx > 18) S('text', {x: xx, y: 14, 'text-anchor': 'middle', class: 'ax'}, s).textContent = d.getHours() === 0 ? fJ.format(d).replace(/^\S+\s/, '') : pad(d.getHours()) + ' h';
  }
  S('line', {x1: G, x2: G, y1: top - 8, y2: h - 6, class: 'maint'}, s);
  S('text', {x: G + 4, y: 14, class: 'maint-t'}, s).textContent = t('maintenant');
  TACHES.forEach((x0, i) => {
    const y = top + i * rh + rh / 2, bloque = x0.besoin_pc && PC_KO, nom = champ(x0, 'nom') || x0.id, ou = champ(x0, 'ou') || '';
    S('line', {x1: G, x2: W - Dr, y1: y, y2: y, class: 'grille'}, s);
    const lb = S('text', {x: 0, y: y - 2, 'font-size': W < 560 ? 12 : 13, 'font-weight': 500}, s); lb.textContent = nom.length > nmax ? nom.slice(0, nmax - 1) + '…' : nom;
    titre(lb, nom);
    const sous = W < 560 ? (bloque ? t('bloquee') : ou.slice(0, 16)) : ou + (bloque ? ' · ' + t('bloquee') : '');
    S('text', {x: 0, y: y + 12, class: 'ax'}, s).textContent = sous;
    if (x0.continu) { const r = S('rect', {x: G, y: y - 6, width: W - Dr - G, height: 12, rx: 6, class: 'continu' + (x0.actif === false ? ' inactif' : '')}, s); titre(r, `${nom} — ${etatTache(x0)}`); return; }
    for (const d of occurrences(x0, t0, t1)) { const c = S('rect', {x: x(d) - 3, y: y - 7, width: 6, height: 14, rx: 2, class: 'tick' + (bloque ? ' bloque' : '')}, s); titre(c, `${nom} — ${quand(d)}${bloque ? t('pc_ko_court') : ''}`); }
  });
  const lignes = TACHES.map(x0 => { const o = x0.actif === false ? [] : occurrences(x0, MAINT, new Date(MAINT.getTime() + 8 * 864e5)), desc = champ(x0, 'description');
    return `<tr><td class="large"><strong>${esc(champ(x0, 'nom'))}</strong>${desc ? `<br><small class="aide">${esc(desc)}</small>` : ''}</td><td data-l="${esc(t('th_ou'))}">${esc(champ(x0, 'ou') || '')}</td>
      <td data-l="${esc(t('th_rythme'))}">${esc(rythme(x0))}${x0.cron ? `<br><code>${esc(x0.cron)}</code>` : ''}</td><td class="num" data-l="${esc(t('th_prochaine'))}">${o.length ? esc(quand(o[0])) + '<br><small class="aide">' + esc(rel(o[0])) + '</small>' : '–'}</td><td data-l="${esc(t('th_etat'))}">${esc(etatTache(x0))}</td></tr>`; }).join('');
  $('#tab-plan').innerHTML = `<thead><tr><th>${esc(t('th_tache'))}</th><th>${esc(t('th_ou'))}</th><th>${esc(t('th_rythme'))}</th><th class="num">${esc(t('th_prochaine'))}</th><th>${esc(t('th_etat'))}</th></tr></thead><tbody>${lignes}</tbody>`;
}

/* ----- jours et chronologie */
const finEt = s => s.fin ? T(s.fin) : MAINT;
function jours() {
  const J = new Map(), plus = (d, k) => { const j = jourLocal(d); J.set(j, (J.get(j) || 0) + (k == null ? 1 : k)); };
  D.etapes.forEach(s => plus(s.debut)); D.agents.forEach(a => plus(a.debut)); D.activite.forEach(b => plus(b[0], 0));
  return [...J.entries()].sort((a, b) => a[0] < b[0] ? -1 : 1); }
let JOURS = [], JOUR = null, JOUR_CHOISI = false;
function chevauche(a, b, j0, j1) { return a < j1 && b > j0; }
function paquets(I) { const fins = []; return I.map(it => { let r = fins.findIndex(f => f <= it.a); if (r < 0) { r = fins.length; fins.push(0); } fins[r] = it.b; return Object.assign(it, {r}); }); }
function union(I) { const L = I.slice().sort((p, q) => p[0] - q[0]); let tot = 0, c = null; for (const [a, b] of L) { if (!c || a > c[1]) { if (c) tot += c[1] - c[0]; c = [a, b]; } else c[1] = Math.max(c[1], b); } if (c) tot += c[1] - c[0]; return tot / 1000; }
function donneesJour(k) {
  const j0 = debutJour(k), j1 = new Date(j0.getTime() + 864e5);
  const E = D.etapes.filter(s => chevauche(T(s.debut), finEt(s), j0, j1)).map(s => ({s, a: Math.max(T(s.debut), j0), b: Math.min(finEt(s), j1)}));
  const A = D.agents.filter(a => chevauche(T(a.debut), T(a.fin), j0, j1)).map(a => ({ag: a, a: Math.max(T(a.debut), j0), b: Math.min(T(a.fin), j1)}));
  const B = D.activite.filter(b => { const d = T(b[0]); return d >= j0 && d < j1; });
  return {j0, j1, E, A, B}; }
function ongletsJours() {
  $('#jours').innerHTML = JOURS.map(([k, n]) => `<button type="button" data-j="${k}" aria-pressed="${k === JOUR}">${esc(fJ.format(debutJour(k)))}<span class="n">${n}</span></button>`).join('') || `<p class="vide">${esc(t('aucune_donnee'))}</p>`;
  $('#jours').querySelectorAll('button').forEach(b => b.addEventListener('click', () => { JOUR = b.dataset.j; JOUR_CHOISI = JOUR !== JOURS[JOURS.length - 1][0]; ongletsJours(); gantt(); categories(); outils(); }));
}
function gantt() {
  const box = $('#gantt'); box.innerHTML = '';
  const J = donneesJour(JOUR);
  if (!J.E.length && !J.A.length && !J.B.length) { box.innerHTML = `<p class="vide">${esc(t('rien_jour'))}</p>`; $('#legende-cat').innerHTML = ''; return; }
  let a = Infinity, b = -Infinity;
  for (const x of J.E.concat(J.A)) { a = Math.min(a, x.a); b = Math.max(b, x.b); }
  for (const x of J.B) { const d = +T(x[0]); a = Math.min(a, d); b = Math.max(b, d + 6e5); }
  const t0 = new Date(a); t0.setMinutes(0, 0, 0); const t1 = new Date(b); if (t1.getMinutes() || t1.getSeconds()) { t1.setMinutes(0, 0, 0); t1.setHours(t1.getHours() + 1); }
  const span = Math.max(36e5, t1 - t0), W = largeur('#gantt', 720), G = 104, Dr = 12, x = d => G + (W - G - Dr) * (d - t0) / span;
  const lanes = [], rowH = 26;
  for (const c of D.categories) {
    const Ec = J.E.filter(e => e.s.categorie === c);
    if (c === 'agents') { const P = paquets(J.A.slice().sort((p, q) => p.a - q.a)), nr = P.reduce((m, p) => Math.max(m, p.r + 1), 0);
      if (Ec.length || P.length) lanes.push({c, Ec, P, h: Math.max(rowH, (Ec.length ? 26 : 5) + nr * 9 + 4)}); }
    else if (Ec.length) { const P = paquets(Ec.slice().sort((p, q) => p.a - q.a)), nr = P.reduce((m, p) => Math.max(m, p.r + 1), 0); lanes.push({c, Ec: P, P: [], h: Math.max(rowH, nr * 22 + 6)}); }
  }
  const top = 24, actH = 54, h = top + lanes.reduce((m, l) => m + l.h, 0) + 14 + actH + 20;
  const s = S('svg', {width: W, height: h, viewBox: `0 0 ${W} ${h}`, role: 'img', 'aria-label': t('chrono_aria')}, box);
  const pas = span > 12 * 36e5 ? 2 : 1;
  for (let d = new Date(t0); d <= t1; d = new Date(d.getTime() + 36e5)) { if (d.getHours() % pas) continue; const xx = x(d);
    S('line', {x1: xx, x2: xx, y1: top - 4, y2: h - 18, class: 'grille'}, s); S('text', {x: xx, y: 13, 'text-anchor': 'middle', class: 'ax'}, s).textContent = pad(d.getHours()) + ' h'; }
  let y = top;
  const CAT = t('cat');
  for (const l of lanes) {
    S('line', {x1: 0, x2: W - Dr, y1: y, y2: y, class: 'grille'}, s);
    S('text', {x: 0, y: y + 17, class: 'lane'}, s).textContent = CAT[l.c] || l.c;
    l.Ec.forEach(e => { const r = e.r || 0, yy = y + 4 + r * 22, w = Math.max(3, x(e.b) - x(e.a));
      const rc = S('rect', {x: x(e.a), y: yy, width: w, height: 17, rx: 3, class: 'cat-' + l.c + (e.s.fin ? '' : ' ouverte')}, s);
      titre(rc, `${e.s.titre} — ${quand(e.s.debut)} → ${e.s.fin ? heure(e.s.fin) : t('en_cours_m')} (${duree((finEt(e.s) - T(e.s.debut)) / 1000)})${e.s.source === 'reconstitue' ? ' · ' + t('reconstitue') : ''}${e.s.notes && e.s.notes.length ? ' · ' + e.s.notes.join(' ; ') : ''}`);
      if (w > 64) { const tx = S('text', {x: x(e.a) + 5, y: yy + 12.5, class: 'lbl'}, s); const n = Math.floor((w - 10) / 6.2); tx.textContent = e.s.titre.length > n ? e.s.titre.slice(0, Math.max(1, n - 1)) + '…' : e.s.titre; }
      (e.s.points || []).forEach(p => { const pd = T(p.quand); if (pd >= e.a && pd <= e.b) titre(S('circle', {cx: x(pd), cy: yy + 8.5, r: 3, class: 'point-etape'}, s), `${heure(pd)} · ${p.note}`); });
    });
    const base = y + (l.Ec.length ? 26 : 5);
    l.P.forEach(p => { const w = Math.max(2, x(p.b) - x(p.a));
      titre(S('rect', {x: x(p.a), y: base + p.r * 9, width: w, height: 7, rx: 2, class: 'cat-agents', 'fill-opacity': .85}, s),
        `${p.ag.description} — ${heure(p.ag.debut)} → ${heure(p.ag.fin)} (${duree(p.ag.duree_s)}) · ${p.ag.modele || '?'} · ${t('contexte_max')} ${tok(p.ag.contexte_max)} · ${t('vague')} ${p.ag.vague}`); });
    y += l.h;
  }
  S('line', {x1: 0, x2: W - Dr, y1: y, y2: y, class: 'grille'}, s);
  const ya = y + 14, mx = Math.max(1, ...J.B.map(b => b[1] + b[2])), bw = Math.max(1.5, (W - G - Dr) * 6e5 / span - 1);
  S('text', {x: 0, y: ya + 14, class: 'lane'}, s).textContent = t('journal_lane');
  S('text', {x: 0, y: ya + 28, class: 'ax'}, s).textContent = t('max_10', {n: mx});
  for (const b of J.B) { const xx = x(T(b[0])), hr = actH * b[1] / mx, he = actH * b[2] / mx, lib = `${heure(b[0])} · ${t('reels_essais', {r: b[1], e: b[2]})}`;
    titre(S('rect', {x: xx, y: ya + actH - hr, width: bw, height: Math.max(0, hr), class: 'reel'}, s), lib);
    if (b[2]) titre(S('rect', {x: xx, y: ya + actH - hr - he, width: bw, height: he, class: 'essai'}, s), lib); }
  S('line', {x1: G, x2: W - Dr, y1: ya + actH, y2: ya + actH, class: 'cadre'}, s);
  if (MAINT >= t0 && MAINT <= t1) { const xx = x(MAINT); S('line', {x1: xx, x2: xx, y1: top - 6, y2: ya + actH, class: 'maint'}, s); const mt = S('text', {x: xx > W - 150 ? xx - 4 : xx + 4, y: h - 4, 'text-anchor': xx > W - 150 ? 'end' : 'start', class: 'maint-t'}, s); mt.textContent = t('maintenant') + ' ' + heure(MAINT); }
  $('#legende-cat').innerHTML = lanes.map(l => `<span><i class="pastille bg-${l.c}"></i>${esc(CAT[l.c])}</span>`).join('') + `<span><i class="pastille bg-reel"></i>${esc(t('leg_reel'))}</span><span><i class="pastille bg-essai"></i>${esc(t('leg_essai'))}</span>`;
}
function categories() {
  const J = donneesJour(JOUR), R = [], CAT = t('cat');
  for (const c of D.categories) {
    if (c === 'agents') { const I = J.A.map(p => [+p.a, +p.b]); if (I.length) R.push({c, s: union(I), n: I.length, cumul: J.A.reduce((m, p) => m + (p.b - p.a) / 1000, 0)}); continue; }
    const I = J.E.filter(e => e.s.categorie === c).map(e => [+e.a, +e.b]); if (I.length) R.push({c, s: union(I), n: I.length}); }
  $('#titre-cat').textContent = t('temps_cat', {j: fJ.format(debutJour(JOUR))});
  if (!R.length) { $('#barres-cat').innerHTML = `<p class="vide">${esc(t('aucune_etape_jour'))}</p>`; $('#note-cat').textContent = ''; return; }
  const mx = Math.max(...R.map(r => r.s));
  $('#barres-cat').innerHTML = R.map(r => `<div class="barre"><span class="nom">${esc(CAT[r.c])}</span><span class="piste"><i class="bg-${r.c}" style="width:${(100 * r.s / mx).toFixed(1)}%"></i></span><span class="chiffre">${esc(duree(r.s))}${r.cumul ? ' · ' + esc(t('cumul')) + ' ' + esc(duree(r.cumul)) : ''}</span></div>`).join('');
  const att = R.find(r => r.c === 'attente'), tot = R.filter(r => r.c !== 'agents').reduce((m, r) => m + r.s, 0);
  $('#note-cat').textContent = (att && tot ? t('note_cat_att', {p: Math.round(100 * att.s / tot)}) : '') + t('note_cat');
}
function goulots() {
  const G = D.goulots || [], N = t('niveau');
  $('#goulots-aide').textContent = t('goulots_aide', {j: fJ.format(T(D.etat_au)), n: G.length, c: tok(D.seuils.contexte_agent), t: nb(D.seuils.trainard, 2), a: Math.round(100 * D.seuils.part_attente)});
  $('#cartes-goulots').innerHTML = G.length ? G.map(g => { const [ti, pr, pi] = textesGoulot(g);
    return `<div class="carte ${g.niveau}"><div class="haut"><span class="niv ${g.niveau}">${esc(N[g.niveau] || g.niveau)}</span><span class="code">${esc(g.code)}</span></div><strong>${esc(ti)}</strong><p>${esc(pr)}</p><p class="piste">${esc(t('piste', {p: pi}))}</p></div>`; }).join('') : `<p class="vide">${esc(t('aucun_goulot'))}</p>`;
  const V = (D.vagues || []).slice().reverse();
  $('#tab-vagues').innerHTML = `<thead><tr><th>${esc(t('th_debut'))}</th><th>${esc(t('th_lot'))}</th><th class="num">${esc(t('th_agents'))}</th><th class="num">${esc(t('th_duree'))}</th><th class="num">${esc(t('th_trainard'))}</th><th class="num">${esc(t('th_contexte'))}</th><th class="num">${esc(t('th_sortie'))}</th></tr></thead><tbody>` +
    V.map(v => `<tr><td class="mono" data-l="${esc(t('th_debut'))}" style="white-space:nowrap">${esc(fJ.format(T(v.debut)))}<br>${esc(heure(v.debut))}</td><td data-l="${esc(t('th_lot'))}">${esc(v.libelle)}<br><small class="aide">${esc(Object.entries(v.modeles).map(([m, n]) => n + ' × ' + m.replace('claude-', '')).join(', '))}</small></td><td class="num" data-l="${esc(t('th_agents'))}">${v.n}</td><td class="num" data-l="${esc(t('th_duree'))}">${esc(duree(v.mur_s))}</td>
      <td class="num" data-l="${esc(t('th_trainard'))}" style="${v.ratio >= D.seuils.trainard && v.n >= 3 ? 'color:var(--attention);font-weight:600' : ''}">${v.ratio == null ? '–' : '×' + nb(v.ratio, 2)}</td><td class="num" data-l="${esc(t('th_contexte'))}">${esc(tok(v.contexte_moyen))} / ${esc(tok(v.contexte_max))}${v.lourds ? ' <small style="color:var(--majeur)" title="' + esc(t('au_dessus')) + '">(' + v.lourds + ')</small>' : ''}</td><td class="num" data-l="${esc(t('th_sortie'))}">${esc(tok(v.sortie))}</td></tr>`).join('') + '</tbody>';
}
let FILTRE_AG = 'tous';
function nuage() {
  const jA = [...new Set(D.agents.map(a => jourLocal(a.debut)))].sort();
  $('#filtre-agents').innerHTML = ['tous'].concat(jA).map(k => `<button type="button" data-k="${k}" aria-pressed="${k === FILTRE_AG}">${k === 'tous' ? esc(t('tous')) : esc(fJ.format(debutJour(k)))}<span class="n">${k === 'tous' ? D.agents.length : D.agents.filter(a => jourLocal(a.debut) === k).length}</span></button>`).join('');
  $('#filtre-agents').querySelectorAll('button').forEach(b => b.addEventListener('click', () => { FILTRE_AG = b.dataset.k; nuage(); }));
  const A = D.agents.filter(a => FILTRE_AG === 'tous' || jourLocal(a.debut) === FILTRE_AG), box = $('#nuage'); box.innerHTML = '';
  if (!A.length) { box.innerHTML = `<p class="vide">${esc(t('aucun_agent'))}</p>`; $('#legende-agents').innerHTML = ''; return; }
  const W = largeur('#nuage', 560), H = 300, g = 52, b = 34, mxX = Math.max(10, Math.ceil(Math.max(...A.map(a => a.duree_s / 60)) / 10) * 10),
    mxY = Math.max(D.seuils.contexte_agent * 1.2, Math.ceil(Math.max(...A.map(a => a.contexte_max)) / 1e5) * 1e5);
  const x = v => g + (W - g - 12) * v / mxX, y = v => H - b - (H - b - 12) * v / mxY;
  const s = S('svg', {width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': t('nuage_aria')}, box);
  for (let v = 0; v <= mxY; v += 1e5) { S('line', {x1: g, x2: W - 12, y1: y(v), y2: y(v), class: 'grille'}, s); S('text', {x: g - 6, y: y(v) + 4, 'text-anchor': 'end', class: 'ax'}, s).textContent = tok(v); }
  const px = mxX > 60 ? 15 : mxX > 30 ? 10 : 5;
  for (let v = 0; v <= mxX; v += px) { S('text', {x: x(v), y: H - b + 16, 'text-anchor': 'middle', class: 'ax'}, s).textContent = v + ' min'; }
  S('text', {x: g, y: H - 2, class: 'ax'}, s).textContent = t('duree_agent');
  S('line', {x1: g, x2: W - 12, y1: y(D.seuils.contexte_agent), y2: y(D.seuils.contexte_agent), class: 'seuil'}, s);
  S('text', {x: W - 14, y: y(D.seuils.contexte_agent) - 5, 'text-anchor': 'end', class: 'seuil-t'}, s).textContent = t('charge', {c: tok(D.seuils.contexte_agent)});
  for (const a of A) titre(S('circle', {cx: x(a.duree_s / 60), cy: y(a.contexte_max), r: 5, class: 'pt m-' + famille(a.modele), 'fill-opacity': .82}, s),
    `${a.description} — ${fJ.format(T(a.debut))} ${heure(a.debut)} · ${a.modele || '?'} · ${duree(a.duree_s)} · ${t('contexte_max')} ${tok(a.contexte_max)} · ${t('sortie')} ${tok(a.sortie)} · ${t('appels', {n: a.appels_outils})} · ${a.vague}`);
  const C = {}; A.forEach(a => { const f = famille(a.modele); C[f] = (C[f] || 0) + 1; });
  const lourds = A.filter(a => a.contexte_max > D.seuils.contexte_agent).length, med = A.map(a => a.duree_s).sort((p, q) => p - q)[Math.floor(A.length / 2)];
  $('#legende-agents').innerHTML = Object.entries(C).map(([f, n]) => `<span><i class="pastille bg-m-${f}"></i>${esc(f)} · ${n}</span>`).join('') + `<span>${esc(t('leg_agents', {n: lourds, d: duree(med)}))}</span>`;
}
function outils() {
  const k = JOUR, M = {};
  for (const [h, d] of Object.entries(D.outils_heure || {})) { if (jourLocal(T(h + ':00:00Z')) !== k) continue;
    for (const [o, v] of Object.entries(d)) { const m = M[o] || (M[o] = [0, 0, 0]); m[0] += v[0]; m[1] += v[1]; m[2] += v[2]; } }
  const R = Object.entries(M).sort((p, q) => (q[1][0] + q[1][1]) - (p[1][0] + p[1][1])).slice(0, 15);
  const tr = R.reduce((m, r) => m + r[1][0], 0), te = Object.values(M).reduce((m, v) => m + v[1], 0);
  $('#outils-aide').textContent = t('outils_aide', {j: fJ.format(debutJour(k)), o: Object.keys(M).length, r: tr, e: te});
  if (!R.length) { $('#barres-outils').innerHTML = `<p class="vide">${esc(t('aucune_exec'))}</p>`; return; }
  const mx = Math.max(...R.map(r => r[1][0] + r[1][1]));
  $('#barres-outils').innerHTML = R.map(([o, v]) => `<div class="barre"><span class="nom mono" title="${esc(o)}">${esc(o)}</span><span class="piste"><i class="bg-reel" style="width:${(100 * v[0] / mx).toFixed(1)}%"></i><i class="bg-essai" style="width:${(100 * v[1] / mx).toFixed(1)}%"></i></span><span class="chiffre">${v[0]} ${esc(t('reel'))} · ${v[1]} ${esc(t('essai'))}${v[2] ? ' · ' + nb(v[2], 1) + ' s' : ''}</span></div>`).join('') +
    `<p class="legende"><span><i class="pastille bg-reel"></i>${esc(t('leg_reels'))}</span><span><i class="pastille bg-essai"></i>${esc(t('leg_essais'))}</span></p>`;
}
function journal() {
  const avec = $('#avec-essais').checked, L = D.journal_recent.filter(e => avec || !e.essai).slice(-60).reverse(), CAT = t('cat'), PH = t('phase');
  $('#liste-journal').innerHTML = L.length ? L.map(e => e.etape ? `<li class="etape"><span class="q">${esc(quand(e.quand))}</span><span class="o"><i class="pastille bg-${esc(e.categorie)}"></i> ${esc(CAT[e.categorie] || e.categorie)}</span><span class="r"><span class="ph">${esc(PH[e.phase] || e.phase)}</span>${esc(e.titre)}${e.note ? ' — ' + esc(e.note) : ''}${e.resultat && e.resultat !== 'ok' ? ' <span class="kv">' + esc(e.resultat) + '</span>' : ''}${e.source === 'reconstitue' ? ' <span class="kv">' + esc(t('reconstitue')) + '</span>' : ''}</span></li>` : `<li class="${e.essai ? 'essai' : ''}"><span class="q">${esc(quand(e.quand))}</span><span class="o" title="${esc(e.outil)} v${esc(e.version)}">${esc(e.outil)} <span style="color:var(--faint)">v${esc(e.version)}</span></span><span class="r">${esc(e.type)} ${Object.entries(e.resume || {}).map(([k, v]) => `<span class="kv">${esc(k)}=${esc(v)}</span>`).join('')}${e.essai ? '<span class="kv">' + esc(t('essai')) + '</span>' : ''}</span></li>`).join('') : `<li class="vide">${esc(t('aucun_evt'))}</li>`;
}
function attentes() {
  const A = D.attentes || {}, P = A.propositions || [], Sv = A.sauvegardes || {}, NC = Sv.non_confirmees || [], TY = t('type'), ST = t('statut'), RA = t('raison');
  const parType = {}; P.forEach(p => (parType[p.type || 'autre'] = parType[p.type || 'autre'] || []).push(p));
  const c1 = `<div class="case"><span class="etiq">${esc(t('c_decisions'))}</span><span class="grand">${P.length}</span>${P.length ? '<ul>' + Object.entries(parType).map(([ty, L]) => L.map(p => `<li>${esc(p.objet)} <small>· ${esc(TY[ty] || ty)} · ${esc(ST[p.statut] || p.statut)}${p.depuis ? ' · ' + esc(rel(p.depuis)) : ''}</small></li>`).join('')).join('') + '</ul>' : `<p class="vide">${esc(t('rien_reviser'))}</p>`}</div>`;
  const c2 = `<div class="case"><span class="etiq">${esc(t('c_sauvegarde'))}</span><span class="grand">${NC.length}</span><ul>
    <li>${PC_KO ? t('pc_inj', {q: esc(quand(A.pc.depuis))}) : esc(t('pc_ok'))}</li>
    <li>${esc(t('derniere', {q: Sv.derniere_complete ? quand(Sv.derniere_complete) : t('inconnue')}))}${Sv.derniere_complete ? ' <small>· ' + esc(rel(Sv.derniere_complete)) + '</small>' : ''}</li>
    ${NC.map(n => `<li>${esc(t('envoi_nc', {q: quand(n.quand)}))}${n.fichiers != null ? ' <small>· ' + esc(t('copies', {n: n.fichiers})) + '</small>' : ''}</li>`).join('')}
    ${DIRECT.actif ? `<li><small>${esc(t('instantane_sv', {q: quand(D0.etat_au)}))}</small></li>` : ''}</ul></div>`;
  const pcT = TACHES.filter(x => x.besoin_pc), E = A.etapes || [];
  const c3 = `<div class="case"><span class="etiq">${esc(t('c_attend'))}</span><span class="grand">${E.length + (PC_KO ? pcT.length : 0)}</span>${E.length || pcT.length ? '<ul>' +
    E.map(e => `<li>${esc(e.titre)} <small>· ${esc(RA[e.raison] || e.raison || t('attente_t'))} · ${esc(rel(e.depuis))}</small></li>`).join('') +
    pcT.map(x => { const o = x.actif === false ? [] : occurrences(x, MAINT, new Date(MAINT.getTime() + 8 * 864e5)); return `<li>${esc(champ(x, 'nom'))} <small>· ${esc(t(PC_KO ? 'a_besoin_pc' : 'utilise_pc'))}${o.length ? ' · ' + esc(t('prochaine_q', {q: quand(o[0])})) : ''}</small></li>`; }).join('') + '</ul>' : `<p class="vide">${esc(t('rien'))}</p>`}</div>`;
  const lm = D.lmstudio, et = lm && lm.etat;
  const c4 = `<div class="case"><span class="etiq">${esc(t('c_lm'))}</span><span class="grand">${lm ? esc(String((et && et.en_attente) || 0)) : '–'}</span>${!lm ? `<p class="vide">${esc(t('lm_absent'))}</p>` : !et ? `<ul><li>${esc(t('lm_jamais'))}</li><li>${esc(t('lm_file', {a: 0, l: lm.lots_entree || 0}))}</li></ul>` :
    `<ul><li>${esc(t('lm_statut', {s: et.statut || '?'}))}${et.raison_arret ? ' <small>· ' + esc(et.raison_arret) + '</small>' : ''}</li><li>${esc(t('lm_file', {a: et.en_attente || 0, l: lm.lots_entree || 0}))}</li><li>${esc(t('lm_traites', {t: et.traites || 0, e: et.erreurs || 0}))}</li>${et.modele ? `<li>${esc(t('lm_modele', {m: et.modele}))}</li>` : ''}${et.maj ? `<li><small>${esc(t('lm_maj', {q: String(et.maj).replace('T', ' ')}))}</small></li>` : ''}</ul>`}</div>`;
  $('#attentes').innerHTML = c1 + c2 + c3 + c4;
}

/* ----- textes fixes, bascule de langue, mode direct */
function textesFixes() {
  document.documentElement.lang = LANG;
  document.querySelectorAll('[data-t]').forEach(el => { el.textContent = t(el.dataset.t); });
  document.querySelectorAll('#langue button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.lang === LANG)));
  $('#langue').setAttribute('aria-label', t('langue'));
}
const DIRECT = {actif: false, B: null, curseur: '', sig: '', derniere: null, perdu: false, minuterie: null};
function indicateur() {
  const el = $('#mode');
  if (!DIRECT.actif) { el.className = 'mode instantane'; el.textContent = t('instantane'); el.title = t('instantane_aide'); return; }
  el.className = 'mode direct' + (DIRECT.perdu ? ' perdu' : '');
  el.textContent = DIRECT.perdu ? t('direct_perdu') : (DIRECT.derniere ? t('direct_maj', {h: fH.format(DIRECT.derniere)}) : t('direct'));
  el.title = ''; }
function tout() {
  MAINT = new Date(); prealable();
  JOURS = jours();
  if (!JOUR || !JOUR_CHOISI || !JOURS.some(j => j[0] === JOUR)) JOUR = JOURS.length ? JOURS[JOURS.length - 1][0] : jourLocal(MAINT);
  textesFixes(); indicateur();
  chips(); planificateur(); ongletsJours(); gantt(); categories(); goulots(); nuage(); outils(); journal(); attentes(); }
async function tirer() {
  let fin = false, n = 0, ch = 0, tours = 0;
  while (!fin && tours++ < 40) {
    const r = await fetch('/api/brut?apres=' + encodeURIComponent(DIRECT.curseur) + '&sig=' + encodeURIComponent(DIRECT.sig), {cache: 'no-store'});
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const res = AG.lireBrut(await r.text(), DIRECT.B);
    if (!res.meta) throw new Error('réponse sans méta');
    DIRECT.curseur = res.meta.curseur || DIRECT.curseur; DIRECT.sig = res.meta.sig || DIRECT.sig; fin = !!res.meta.fin; n += res.nouveaux; ch += res.changes; }
  return n + ch; }
async function boucle() {
  try { const k = await tirer(); DIRECT.perdu = false; DIRECT.derniere = new Date();
    if (k) { D = AG.agreger(DIRECT.B, {seuils: D0.seuils, categories: D0.categories, outil: D0.outil + ' · direct', sauvegardes: D0.attentes && D0.attentes.sauvegardes, analyserCron}); tout(); }
    else indicateur(); }
  catch (e) { DIRECT.perdu = true; indicateur(); }
  DIRECT.minuterie = setTimeout(boucle, 5000); }
async function essayerDirect() {
  if (!/^https?:$/.test(location.protocol)) return;
  try { const r = await fetch('/api/ping', {cache: 'no-store'}); if (!r.ok) return; const j = await r.json();
    if (!j || j.serveur !== 'serveur_tableau_de_bord') return; }
  catch (e) { return; }
  DIRECT.actif = true; DIRECT.B = AG.nouveauBrut(); indicateur(); boucle(); }

$('#avec-essais').addEventListener('change', journal);
document.querySelectorAll('#langue button').forEach(b => b.addEventListener('click', () => {
  LANG = b.dataset.lang; try { localStorage.setItem('tdb-langue', LANG); } catch (e) {} formats(); tout(); }));
let minuterie = null; window.addEventListener('resize', () => { clearTimeout(minuterie); minuterie = setTimeout(() => { planificateur(); gantt(); nuage(); }, 150); });
tout();
essayerDirect();
})();
</script>
'''

if __name__ == '__main__':
    sys.exit(main())
