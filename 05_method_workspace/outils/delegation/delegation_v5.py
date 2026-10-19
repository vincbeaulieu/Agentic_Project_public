"""
OUTIL: delegation
VERSION: 5
RESUME: Registre des délégations à des agents : chaque délégation déclare son type de tâche, son brief, son schéma de sortie et son évaluateur déterministe ; chaque résultat d'agent est noté (qualité, alignement, rapidité, ressources, compacité, automatisation) ; chaque type de tâche liste ses étapes automatisables sans LLM. Vérifie qu'aucune délégation n'est sans évaluateur ni résultat.
USAGE: python3 delegation_v5.py ouvrir <delegation.json> | resultat <resultat.json> | type <type_tache.json> | verifier | bilan
ENTREES: JSON (voir taches/LISEZMOI des champs dans ce docstring)
SORTIES: delegations/<id>_v1.json, delegations/<id>_<agent>_resultat_vN.json, taches/<type>_vN.json, delegations/bilan_delegations_vN.md ; événements
CATEGORIE: memoire
BANC: tests/test_delegation_v5.py
REMPLACE: delegation_v4 (appelé sans commande, il plantait sur IndexError au lieu d'afficher l'usage ; une commande inconnue ou sans fichier passait en silence ou plantait : désormais usage et code 2, 16 oct. 2026) ; v4 : delegation_v3 (« verifier » et « bilan » ne reconnaissaient que les identifiants D-0001 (regex sur le nom de fichier) alors que « ouvrir » en accepte d'autres : les vraies délégations D-20261015-… étaient ignorées en silence (« 0 délégations » avec 6 fichiers présents). v4 classe chaque JSON du dossier d'après son contenu (délégation : id + type_tache ; résultat : id + agent + verdict_evaluateur), signale les fichiers hors schéma et les noms de fichier incohérents avec leur contenu, et échoue (code 1) si le dossier contient des JSON mais qu'aucun n'est reconnu ; « ouvrir » et « resultat » refusent un identifiant ou un nom d'agent vide ou contenant / ou \\) ; v3 : delegation_v2 (le dossier des types de tâches, désigné par la clé « taches », contient aussi le planificateur et des étapes reconstituées : v2 les prenait pour des types et plantait (KeyError « etapes_automatisables ») ; v3 ne retient comme type qu'un fichier au schéma de type (champs type et etapes_automatisables) et signale les autres comme « hors schéma », sans erreur ; une délégation sans « agents » est signalée au lieu de planter) ; v2 : delegation_v1 (noms de dossiers de l'espace écrits en dur, remplacés par le registre central cc_lib_v4.chemin) ; v1 : -

Champs. Délégation : id (D-… ; ex. D-0001, D-20261015-tests-A06), date, type_tache, brief, schema_sortie, evaluateur (commande), agents [{nom, modele, perimetre}], dossier.
Résultat : id, agent, verdict_evaluateur (« BILAN conforme »…), mesures {qualite, alignement, duree_min, tokens, outils_appels, octets_sortie, part_automatique}, constats [...], remarques.
Type de tâche : type, description, schema_sortie, evaluateur, etapes_automatisables [{etape, statut: automatisee|a_faire|non_automatisable, outil}].
"""
import sys, os, re, json, glob
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
from cc_lib_v1 import RACINE_CC, ecrire_versionne
from cc_lib_v4 import chemin, evenement     # dossiers de l'espace et journal désignés par le registre central
CC = RACINE_CC                              # racine de l'espace, comme avant


def dossiers():
    """(dossier des délégations, dossier des types de tâches), d'après le registre central des dossiers."""
    return chemin('delegations', racine=CC), chemin('taches', racine=CC)


def _ecrire(d, base, obj, champs):
    manq = [c for c in champs if c not in obj]
    if manq: raise SystemExit(f'champs manquants : {manq}')
    p, cree = ecrire_versionne(d, base, 'json', json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + '\n')
    print(('écrit ' if cree else 'inchangé ') + os.path.relpath(p, CC)); return p, cree


def _derniers(d, rx):
    par = {}
    for f in glob.glob(os.path.join(d, '*.json')):
        m = re.match(rx, os.path.basename(f))
        if m:
            k, v = m.group(1), int(m.group(2))
            if k not in par or v > par[k][0]: par[k] = (v, f)
    return {k: json.load(open(f, encoding='utf-8')) for k, (v, f) in sorted(par.items())}


def _versions(d):
    """v4 : chaque JSON du dossier classé d'après son CONTENU, jamais d'après un motif de nom (v3 ignorait en silence les
    identifiants hors motif). Retourne (délégations, résultats, hors_schema, noms_incoherents, nb_json, nb_reconnus) ; pour chaque clé, la
    version la plus haute (numéro _vN du nom de fichier)."""
    dels, res, hors, incoh = {}, {}, [], []
    fichiers = sorted(glob.glob(os.path.join(d, '*.json')))
    for f in fichiers:
        b = os.path.basename(f); m = re.search(r'_v(\d+)\.json$', b); v = int(m.group(1)) if m else 0
        try:
            with open(f, encoding='utf-8') as g: o = json.load(g)
        except (ValueError, OSError) as e:
            hors.append(f'{b} (illisible : {e.__class__.__name__})'); continue
        if isinstance(o, dict) and o.get('id') and 'agent' in o and 'verdict_evaluateur' in o:
            k, cible, attendu = f"{o['id']}_{o['agent']}", res, f"{o['id']}_{o['agent']}_resultat_v"
        elif isinstance(o, dict) and o.get('id') and 'type_tache' in o:
            k, cible, attendu = o['id'], dels, f"{o['id']}_v"
        else:
            hors.append(b); continue
        if not b.startswith(attendu): incoh.append(f'{b} (contenu : {k})')
        if k not in cible or v > cible[k][0]: cible[k] = (v, o)
    return ({k: o for k, (v, o) in sorted(dels.items())}, {k: o for k, (v, o) in sorted(res.items())}, hors, incoh, len(fichiers), len(fichiers) - len(hors))


def _nom_sur(x, quoi):
    if not isinstance(x, str) or not x.strip() or '/' in x or '\\' in x:
        raise SystemExit(f'{quoi} invalide (vide ou contenant / ou \\) : {x!r}')


COMMANDES = {'ouvrir': 1, 'resultat': 1, 'type': 1, 'verifier': 0, 'bilan': 0}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDES or len(sys.argv) < 2 + COMMANDES[sys.argv[1]]:
        print('appel invalide' + (f' : commande « {sys.argv[1]} »' if len(sys.argv) > 1 else ' : aucune commande'))
        print('USAGE:', __doc__.split('USAGE:')[1].split('ENTREES:')[0].strip())
        raise SystemExit(2)
    c = sys.argv[1]; DD, DT = dossiers()
    if c == 'ouvrir':
        o = json.load(open(sys.argv[2], encoding='utf-8')); _nom_sur(o.get('id'), 'identifiant')
        _, cree = _ecrire(DD, o['id'], o, ('id', 'date', 'type_tache', 'brief', 'schema_sortie', 'evaluateur', 'agents', 'dossier'))
        if cree: evenement('delegation', 5, 'ouverture', dict(id=o['id'], type=o['type_tache'], agents=[a['nom'] for a in o['agents']]))
    elif c == 'resultat':
        o = json.load(open(sys.argv[2], encoding='utf-8')); _nom_sur(o.get('id'), 'identifiant'); _nom_sur(o.get('agent'), 'nom d’agent')
        _, cree = _ecrire(DD, f"{o['id']}_{o['agent']}_resultat", o, ('id', 'agent', 'verdict_evaluateur', 'mesures', 'constats'))
        if cree: evenement('delegation', 5, 'resultat', dict(id=o['id'], agent=o['agent'], verdict=o['verdict_evaluateur'], mesures=o['mesures']))
    elif c == 'type':
        o = json.load(open(sys.argv[2], encoding='utf-8'))
        _ecrire(DT, o['type'], o, ('type', 'description', 'schema_sortie', 'evaluateur', 'etapes_automatisables'))
    elif c in ('verifier', 'bilan'):
        dels, res, hors_d, incoh, nb_json, nb_rec = _versions(DD)
        tous = _derniers(DT, r'^(.+)_v(\d+)\.json$')
        types = {k: o for k, o in tous.items() if isinstance(o, dict) and 'type' in o and isinstance(o.get('etapes_automatisables'), list)}
        hors = sorted(k for k in tous if k not in types)
        pb = []
        for k, o in dels.items():
            if not o.get('evaluateur'): pb.append(f'{k} : sans évaluateur')
            if not isinstance(o.get('agents'), list): pb.append(f'{k} : sans liste d’agents'); continue
            for a in o['agents']:
                if f"{k}_{a['nom']}" not in res: pb.append(f"{k} : pas de résultat pour {a['nom']}")
            if o['type_tache'] not in types: pb.append(f"{k} : type de tâche {o['type_tache']} non décrit ({os.path.relpath(DT, CC)}/)")
        for t, o in types.items():
            af = [e['etape'] for e in o['etapes_automatisables'] if e['statut'] == 'a_faire']
            if af: pb.append(f'type {t} : {len(af)} étape(s) à automatiser : ' + ' ; '.join(af[:5]))
        if c == 'verifier':
            print(f'{len(dels)} délégations, {len(res)} résultats, {len(types)} types ; à reprendre : {len(pb)}' + (f' ; fichiers hors schéma ignorés dans {os.path.relpath(DT, CC)}/ : ' + ', '.join(hors) if hors else ''))
            print(f'   décompte : {nb_json} JSON dans {os.path.relpath(DD, CC)}/ : {nb_rec} reconnu(s), {len(hors_d)} hors schéma')
            if hors_d: print('   hors schéma (ni délégation ni résultat) : ' + ', '.join(hors_d))
            for x in incoh: print('   nom de fichier incohérent avec son contenu :', x)
            for x in pb: print('  ', x)
            vide = nb_json > 0 and not dels and not res
            if vide: print(f'ERREUR : {nb_json} fichier(s) JSON présents, aucun reconnu comme délégation ou résultat')
            sys.exit(1 if vide or incoh or any('sans évaluateur' in x or 'pas de résultat' in x for x in pb) else 0)
        L = ['# Bilan des délégations', '', 'Généré par `outils/delegation.py bilan`.', '',
             '| Délégation | Agent | Verdict de l’évaluateur | Qualité | Alignement | Durée (min) | Tokens | Part automatique |', '|---|---|---|---|---|---|---|---|']
        for k, o in sorted(res.items()):
            m = o['mesures']
            L.append(f"| {o['id']} | {o['agent']} | {o['verdict_evaluateur']} | {m.get('qualite')} | {m.get('alignement')} | {m.get('duree_min')} | {m.get('tokens')} | {m.get('part_automatique')} |")
        L += ['', '## Types de tâches et automatisation', '']
        for t, o in types.items():
            L.append(f"### {t}"); L.append(o['description'])
            for e in o['etapes_automatisables']: L.append(f"- [{e['statut']}] {e['etape']}" + (f" — `{e['outil']}`" if e.get('outil') else ''))
            L.append('')
        L += ['## À reprendre', ''] + [f'- {x}' for x in pb]
        p, cree = ecrire_versionne(DD, 'bilan_delegations', 'md', '\n'.join(L) + '\n')
        print(os.path.basename(p), 'nouvelle version' if cree else 'inchangé')


if __name__ == '__main__':
    main()
