"""
OUTIL: delegation
VERSION: 1
RESUME: Registre des délégations à des agents : chaque délégation déclare son type de tâche, son brief, son schéma de sortie et son évaluateur déterministe ; chaque résultat d'agent est noté (qualité, alignement, rapidité, ressources, compacité, automatisation) ; chaque type de tâche liste ses étapes automatisables sans LLM. Vérifie qu'aucune délégation n'est sans évaluateur ni résultat.
USAGE: python3 delegation_v1.py ouvrir <delegation.json> | resultat <resultat.json> | type <type_tache.json> | verifier | bilan
ENTREES: JSON (voir taches/LISEZMOI des champs dans ce docstring)
SORTIES: delegations/<id>_v1.json, delegations/<id>_<agent>_resultat_vN.json, taches/<type>_vN.json, delegations/bilan_delegations_vN.md ; événements
CATEGORIE: memoire
BANC: -
REMPLACE: -

Champs. Délégation : id (D-0001), date, type_tache, brief, schema_sortie, evaluateur (commande), agents [{nom, modele, perimetre}], dossier.
Résultat : id, agent, verdict_evaluateur (« BILAN conforme »…), mesures {qualite, alignement, duree_min, tokens, outils_appels, octets_sortie, part_automatique}, constats [...], remarques.
Type de tâche : type, description, schema_sortie, evaluateur, etapes_automatisables [{etape, statut: automatisee|a_faire|non_automatisable, outil}].
"""
import sys, os, re, json, glob
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
from cc_lib_v1 import RACINE_CC, ecrire_versionne, evenement
DD, DT = os.path.join(RACINE_CC, 'delegations'), os.path.join(RACINE_CC, 'taches')


def _ecrire(d, base, obj, champs):
    manq = [c for c in champs if c not in obj]
    if manq: raise SystemExit(f'champs manquants : {manq}')
    p, cree = ecrire_versionne(d, base, 'json', json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + '\n')
    print(('écrit ' if cree else 'inchangé ') + os.path.relpath(p, RACINE_CC)); return p, cree


def _derniers(d, rx):
    par = {}
    for f in glob.glob(os.path.join(d, '*.json')):
        m = re.match(rx, os.path.basename(f))
        if m:
            k, v = m.group(1), int(m.group(2))
            if k not in par or v > par[k][0]: par[k] = (v, f)
    return {k: json.load(open(f, encoding='utf-8')) for k, (v, f) in sorted(par.items())}


def main():
    c = sys.argv[1]
    if c == 'ouvrir':
        o = json.load(open(sys.argv[2], encoding='utf-8'))
        _, cree = _ecrire(DD, o['id'], o, ('id', 'date', 'type_tache', 'brief', 'schema_sortie', 'evaluateur', 'agents', 'dossier'))
        if cree: evenement('delegation', 1, 'ouverture', dict(id=o['id'], type=o['type_tache'], agents=[a['nom'] for a in o['agents']]))
    elif c == 'resultat':
        o = json.load(open(sys.argv[2], encoding='utf-8'))
        _, cree = _ecrire(DD, f"{o['id']}_{o['agent']}_resultat", o, ('id', 'agent', 'verdict_evaluateur', 'mesures', 'constats'))
        if cree: evenement('delegation', 1, 'resultat', dict(id=o['id'], agent=o['agent'], verdict=o['verdict_evaluateur'], mesures=o['mesures']))
    elif c == 'type':
        o = json.load(open(sys.argv[2], encoding='utf-8'))
        _ecrire(DT, o['type'], o, ('type', 'description', 'schema_sortie', 'evaluateur', 'etapes_automatisables'))
    elif c in ('verifier', 'bilan'):
        dels = _derniers(DD, r'^(D-\d{4})_v(\d+)\.json$')
        res = _derniers(DD, r'^(D-\d{4}_.+)_resultat_v(\d+)\.json$')
        types = _derniers(DT, r'^(.+)_v(\d+)\.json$')
        pb = []
        for k, o in dels.items():
            if not o.get('evaluateur'): pb.append(f'{k} : sans évaluateur')
            for a in o['agents']:
                if f"{k}_{a['nom']}" not in res: pb.append(f"{k} : pas de résultat pour {a['nom']}")
            if o['type_tache'] not in types: pb.append(f"{k} : type de tâche {o['type_tache']} non décrit (taches/)")
        for t, o in types.items():
            af = [e['etape'] for e in o['etapes_automatisables'] if e['statut'] == 'a_faire']
            if af: pb.append(f'type {t} : {len(af)} étape(s) à automatiser : ' + ' ; '.join(af[:5]))
        if c == 'verifier':
            print(f'{len(dels)} délégations, {len(res)} résultats, {len(types)} types ; à reprendre : {len(pb)}')
            for x in pb: print('  ', x)
            sys.exit(1 if any('sans évaluateur' in x or 'pas de résultat' in x for x in pb) else 0)
        L = ['# Bilan des délégations', '', 'Généré par `outils/delegation_v1.py bilan`.', '',
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
