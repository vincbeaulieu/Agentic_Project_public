"""
OUTIL: suivre_propositions
VERSION: 1
RESUME: Audit des propositions faites à l'utilisateur (skills, leçons, mémoire, guides, procédures, organigrammes, méthode) : registre versionné des événements de chaque proposition (proposée, présentée, modification demandée, acceptée, refusée, remplacée, à confirmer, retirée), avec date, source (chat, carte, message, détection, fichier) et citation courte ; détection automatique de l'état des skills (brouillon identique ou non à la skill enregistrée par l'utilisateur), des leçons (statut du fichier) et du mémoire (fichier d'approbation) ; rapports : index de ce qui attend la révision et audit complet. N'approuve jamais rien : il constate.
USAGE: python3 outils/suivre_propositions.py consigner <id> <evenement> [--type T] [--objet "…"] [--fichier chemin] [--source chat|carte|message|detection|fichier] [--note "…"] [--date "AAAA-MM-JJ HH:MM"]  |  importer <amorce.json>  |  detecter [--skills <dossier des skills enregistrées>] [--brouillons <dossier>]  |  rapport  |  etat
ENTREES: propositions_a_reviser/registre_propositions_vN.json ; skills_propositions/<nom>_SKILL_vN.md ; skills enregistrées (<dossier>/<nom>/SKILL.md, par défaut /root/.claude/skills/synced/*/ dans le cloud) ; lecons/LC-*_vN.json ; memoire/MEMOIRE_METHODOLOGIE_vN.md et memoire/statut/vN_approbation.json
SORTIES: propositions_a_reviser/registre_propositions_vN.json, INDEX_vN.md (en attente de révision), AUDIT_vN.md (historique complet) — nouvelles versions seulement si le contenu change ; événement dans journal/
CATEGORIE: gouvernance
BANC: tests/test_suivre_propositions_v1.py
REMPLACE: -
"""
import sys, os, re, json, glob, hashlib, datetime, collections
H = os.path.dirname(os.path.abspath(__file__)); O = H
while os.path.basename(O) != 'outils' and os.path.dirname(O) != O: O = os.path.dirname(O)
for p in (os.path.join(O, '_compat'), O):
    if p not in sys.path: sys.path.insert(0, p)
CC = os.path.dirname(O); VERSION = 1
DOSSIER = os.path.join(CC, 'propositions_a_reviser')
EVENEMENTS = ('proposee', 'presentee', 'modification_demandee', 'acceptee', 'refusee', 'remplacee', 'a_confirmer', 'retiree')
CLOS = ('acceptee', 'refusee', 'remplacee', 'retiree')
LIBELLE = {'proposee': 'en attente', 'presentee': 'en attente', 'modification_demandee': 'modification demandée', 'acceptee': 'acceptée',
           'refusee': 'refusée', 'remplacee': 'remplacée', 'a_confirmer': 'à confirmer', 'retiree': 'retirée'}


def opt(a, k, d=None): return a[a.index(k) + 1] if k in a else d


def num_v(f):
    m = re.search(r'_v(\d+)\.[^.]+$', f); return int(m.group(1)) if m else -1


def maintenant(): return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M')


def lire(f):
    with open(f, encoding='utf-8') as g: return g.read()


def ecrire_version(base, ext, contenu):
    """<base>_vN.<ext> dans DOSSIER, N = dernière + 1 ; rien d'écrit si la dernière version a déjà ce contenu."""
    os.makedirs(DOSSIER, exist_ok=True)
    V = sorted(glob.glob(os.path.join(DOSSIER, f'{base}_v*.{ext}')), key=num_v)
    if V and lire(V[-1]) == contenu: return V[-1], False
    n = num_v(V[-1]) + 1 if V else 1; f = os.path.join(DOSSIER, f'{base}_v{n}.{ext}')
    with open(f, 'x', encoding='utf-8') as g: g.write(contenu)
    return f, True


def charger():
    V = sorted(glob.glob(os.path.join(DOSSIER, 'registre_propositions_v*.json')), key=num_v)
    return json.loads(lire(V[-1])) if V else dict(propositions={})


def sauver(R):
    return ecrire_version('registre_propositions', 'json', json.dumps(R, ensure_ascii=False, indent=1, sort_keys=True))


def ajouter(R, pid, ev, type_=None, objet=None, fichier=None, source='chat', note='', date=None, unique=False):
    """Ajoute un événement ; unique=True : ne rien ajouter si un événement de même nature et même note existe déjà."""
    if ev not in EVENEMENTS: raise SystemExit(f'événement inconnu : {ev} (permis : {", ".join(EVENEMENTS)})')
    P = R['propositions'].setdefault(pid, dict(type=type_ or '?', objet=objet or pid, fichier=fichier, evenements=[]))
    for k, v in (('type', type_), ('objet', objet), ('fichier', fichier)):
        if v and (not P.get(k) or P.get(k) in ('?', pid)): P[k] = v
    if unique and any(e['evenement'] == ev and e.get('note', '') == note for e in P['evenements']): return False
    P['evenements'].append(dict(date=date or maintenant(), evenement=ev, source=source, note=note)); return True


def decrire(R, pid, type_=None, objet=None, fichier=None):
    """Complète la description d'une proposition existante (type, objet, fichier) sans toucher à ses événements."""
    P = R['propositions'].get(pid)
    if P is None: return
    for k, v in (('type', type_), ('objet', objet), ('fichier', fichier)):
        if v and (not P.get(k) or P.get(k) in ('?', pid)): P[k] = v


def statut(P):
    E = [e['evenement'] for e in P['evenements']]
    for ev in reversed(E):
        if ev in CLOS or ev in ('modification_demandee', 'a_confirmer'): return ev
    return 'proposee' if E else '?'


def corps(t):
    t = re.sub(r'(?s)^\s*---\n.*?\n---\n', '', t, count=1); return re.sub(r'\s+', ' ', t).strip()


def detecter_skills(R, brouillons, installees):
    """Brouillons <nom>_SKILL_vN.md comparés (sans l'en-tête) aux skills enregistrées <installees>/<nom>/SKILL.md."""
    n = 0; par_nom = collections.defaultdict(list)
    for f in glob.glob(os.path.join(brouillons, '*_SKILL_v*.md')): par_nom[os.path.basename(f).split('_SKILL_')[0]].append(f)
    for nom, F in par_nom.items():
        F.sort(key=num_v); inst = next((os.path.join(d, nom, 'SKILL.md') for d in installees if os.path.exists(os.path.join(d, nom, 'SKILL.md'))), None)
        ci = corps(lire(inst)) if inst else None; accepte = None
        for f in F:
            pid = f'S-{nom}-v{num_v(f)}'; rel = os.path.relpath(f, CC).replace(os.sep, '/')
            date = datetime.datetime.fromtimestamp(os.path.getmtime(f), datetime.timezone.utc).strftime('%Y-%m-%d %H:%M')
            if pid not in R['propositions']: n += ajouter(R, pid, 'proposee', 'skill', f'skill « {nom} » v{num_v(f)}', rel, 'detection', 'brouillon trouvé', date)
            decrire(R, pid, 'skill', f'skill « {nom} » v{num_v(f)}', rel)
            if ci is not None and corps(lire(f)) == ci:
                accepte = num_v(f)
                if statut(R['propositions'][pid]) != 'acceptee': n += ajouter(R, pid, 'acceptee', source='detection', note='identique à la skill enregistrée')
        for f in F:
            pid = f'S-{nom}-v{num_v(f)}'
            if accepte and num_v(f) < accepte and statut(R['propositions'][pid]) != 'remplacee':
                n += ajouter(R, pid, 'remplacee', source='detection', note=f'v{accepte} enregistrée')
        if ci is not None and accepte is None:
            h = hashlib.sha256(ci.encode()).hexdigest()[:12]; pid = f'S-{nom}-v{num_v(F[-1])}'
            n += ajouter(R, pid, 'a_confirmer', source='detection', note=f'skill enregistrée différente de tous les brouillons (empreinte {h})', unique=True)
    return n


def detecter_fichiers(R):
    """Leçons (statut du fichier) et mémoire (fichier d'approbation) ; versions antérieures remplacées."""
    n = 0; L = collections.defaultdict(list)
    for f in glob.glob(os.path.join(CC, 'lecons', 'LC-*_v*.json')): L[os.path.basename(f).split('_v')[0]].append(f)
    for lc, F in L.items():
        F.sort(key=num_v)
        for f in F:
            d = json.loads(lire(f)); pid = f'L-{lc}-v{num_v(f)}'; rel = os.path.relpath(f, CC).replace(os.sep, '/')
            if pid not in R['propositions']: n += ajouter(R, pid, 'proposee', 'lecon', f"leçon {lc} v{num_v(f)} : {d.get('titre', '')[:80]}", rel, 'fichier', '', (d.get('date') or '')[:10] or None)
            decrire(R, pid, 'lecon', f"leçon {lc} v{num_v(f)} : {d.get('titre', '')[:80]}", rel)
            if d.get('statut') == 'validee' and statut(R['propositions'][pid]) not in ('acceptee', 'remplacee'): n += ajouter(R, pid, 'acceptee', source='fichier', note='statut « validée »')
            if f != F[-1] and statut(R['propositions'][pid]) != 'remplacee': n += ajouter(R, pid, 'remplacee', source='fichier', note=f'v{num_v(F[-1])} existe')
    M = sorted(glob.glob(os.path.join(CC, 'memoire', 'MEMOIRE_METHODOLOGIE_v*.md')), key=num_v)
    for f in M:
        v = num_v(f); pid = f'M-v{v}'; rel = os.path.relpath(f, CC).replace(os.sep, '/')
        if pid not in R['propositions']: n += ajouter(R, pid, 'proposee', 'memoire', f'mémoire méthodologique v{v}', rel, 'fichier')
        decrire(R, pid, 'memoire', f'mémoire méthodologique v{v}', rel)
        if os.path.exists(os.path.join(CC, 'memoire', 'statut', f'v{v}_approbation.json')) and statut(R['propositions'][pid]) != 'acceptee':
            n += ajouter(R, pid, 'acceptee', source='fichier', note='fichier d’approbation')
        elif f != M[-1] and statut(R['propositions'][pid]) not in CLOS: n += ajouter(R, pid, 'remplacee', source='fichier', note=f'v{num_v(M[-1])} proposée')
    return n


def rapport(R):
    P = R['propositions']; par_type = collections.defaultdict(list)
    for pid, p in sorted(P.items()): par_type[p['type']].append(pid)
    att = [pid for pid, p in sorted(P.items()) if statut(p) not in CLOS]
    idx = ['# Propositions à réviser par l’utilisateur', '', 'Généré par `suivre_propositions` : rien ici n’est approuvé par Claude. Les fichiers restent à leur place ; l’index les référence.', '',
           f'{len(att)} proposition(s) en attente sur {len(P)}.', '']
    for t in sorted(par_type):
        L = [pid for pid in par_type[t] if pid in att]
        if not L: continue
        idx += [f'## {t} ({len(L)})', '', '| Proposition | Objet | Fichier | État | Depuis |', '|---|---|---|---|---|']
        idx += [f"| {pid} | {P[pid]['objet']} | `{P[pid].get('fichier') or '—'}` | {LIBELLE[statut(P[pid])]} | {P[pid]['evenements'][-1]['date']} |" for pid in L] + ['']
    aud = ['# Audit des propositions', '', 'Chaque proposition et ses événements : proposée, présentée, modification demandée (dans le chat), acceptée, refusée, remplacée, à confirmer.', '']
    cpt = collections.Counter(LIBELLE[statut(p)] for p in P.values())
    aud += ['État : ' + ', '.join(f'{v} {k}' for k, v in sorted(cpt.items())) + '.', '']
    for t in sorted(par_type):
        aud += [f'## {t}', '']
        for pid in par_type[t]:
            p = P[pid]; aud += [f"### {pid} — {p['objet']} — {LIBELLE[statut(p)]}", ''] + ([f"Fichier : `{p['fichier']}`", ''] if p.get('fichier') else [])
            aud += ['| Date | Événement | Source | Note |', '|---|---|---|---|'] + [f"| {e['date']} | {e['evenement']} | {e['source']} | {e.get('note', '').replace('|', '/')} |" for e in p['evenements']] + ['']
    return ecrire_version('INDEX', 'md', '\n'.join(idx) + '\n'), ecrire_version('AUDIT', 'md', '\n'.join(aud) + '\n')


def evenement_journal(action, details):
    try:
        from cc_lib_v1 import evenement; evenement('suivre_propositions', VERSION, action, details)
    except Exception: pass


def main(a):
    if not a or a[0] not in ('consigner', 'importer', 'detecter', 'rapport', 'etat'): print('USAGE: ' + __doc__.split('USAGE: ')[1].split('\n')[0]); return 2
    R = charger(); c = a[0]
    if c == 'consigner':
        ajouter(R, a[1], a[2], opt(a, '--type'), opt(a, '--objet'), opt(a, '--fichier'), opt(a, '--source', 'chat'), opt(a, '--note', ''), opt(a, '--date'))
        print(sauver(R)[0])
    elif c == 'importer':
        n = 0
        for e in json.loads(lire(a[1])):
            n += ajouter(R, e['id'], e['evenement'], e.get('type'), e.get('objet'), e.get('fichier'), e.get('source', 'chat'), e.get('note', ''), e.get('date'), unique=True)
        print(f'{n} événement(s) importé(s) ;', sauver(R)[0])
    elif c == 'detecter':
        inst = [opt(a, '--skills')] if opt(a, '--skills') else sorted(glob.glob('/root/.claude/skills/synced/*/'))
        n = detecter_skills(R, opt(a, '--brouillons', os.path.join(CC, 'skills_propositions')), inst) + detecter_fichiers(R)
        print(f'{n} événement(s) détecté(s) ;', sauver(R)[0])
    elif c == 'rapport':
        (fi, _), (fa, _) = rapport(R); print(fi); print(fa)
    elif c == 'etat':
        for pid, p in sorted(R['propositions'].items()): print(f"{LIBELLE[statut(p)]:22} {pid:45} {p['objet'][:70]}")
    evenement_journal(c, dict(propositions=len(R['propositions'])))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
