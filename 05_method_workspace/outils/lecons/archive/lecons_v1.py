"""
OUTIL: lecons
VERSION: 1
RESUME: Registre des leçons apprises : une leçon = un fichier JSON immuable (une nouvelle version à chaque modification), avec règle, application, preuve, contrôle automatique associé (outil:règle) ou « manuel », statut (proposée / validée) et skills où elle est enregistrée ; génère le registre lisible ; vérifie que chaque leçon validée a un contrôle.
USAGE: python3 lecons_v1.py ajouter <fichier_lecon.json> | lister | verifier
ENTREES: JSON {id, titre, date, source, regle, application, preuve, controle, statut, skills}
SORTIES: lecons/<id>_v<N>.json ; lecons/registre_lecons_vN.md (si changement) ; événement dans journal/
CATEGORIE: memoire
BANC: -
REMPLACE: skills/orchestration-agents-recursive/lecons_v1.md (repris en LC-001 à LC-007)
"""
import sys, os, re, json, glob
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
from cc_lib_v1 import RACINE_CC, ecrire_versionne, evenement
D = os.path.join(RACINE_CC, 'lecons')
CHAMPS = ('id', 'titre', 'date', 'source', 'regle', 'application', 'preuve', 'controle', 'statut', 'skills')


def toutes():
    par = {}
    for f in glob.glob(os.path.join(D, 'LC-*_v*.json')):
        m = re.match(r'^(LC-\d{3})_v(\d+)\.json$', os.path.basename(f))
        if m and (m.group(1) not in par or int(m.group(2)) > par[m.group(1)][0]): par[m.group(1)] = (int(m.group(2)), f)
    return {k: json.load(open(f, encoding='utf-8')) for k, (v, f) in sorted(par.items())}


def ajouter(fj):
    L = json.load(open(fj, encoding='utf-8'))
    for l in (L if isinstance(L, list) else [L]):
        manq = [c for c in CHAMPS if c not in l]
        if manq: raise SystemExit(f"{l.get('id')} : champs manquants {manq}")
        p, cree = ecrire_versionne(D, l['id'], 'json', json.dumps(l, ensure_ascii=False, indent=1, sort_keys=True) + '\n')
        print(('ajoutée ' if cree else 'inchangée ') + os.path.basename(p))
        if cree: evenement('lecons', 1, 'lecon', dict(id=l['id'], statut=l['statut'], controle=l['controle']))


def lister():
    T = toutes()
    lignes = ['# Registre des leçons', '', 'Généré par `outils/lecons_v1.py lister`. Une leçon modifiée = une nouvelle version de son fichier.', '',
              '| Id | Leçon | Statut | Contrôle automatique | Skills |', '|---|---|---|---|---|']
    for k, l in T.items():
        lignes.append(f"| {k} | {l['titre']} | {l['statut']} | {l['controle']} | {', '.join(l['skills'])} |")
    lignes.append('')
    for k, l in T.items():
        lignes += [f"## {k} — {l['titre']}", f"- Date et source : {l['date']} · {l['source']}", f"- Règle : {l['regle']}",
                   f"- Application : {l['application']}", f"- Preuve : {l['preuve']}", '']
    p, cree = ecrire_versionne(D, 'registre_lecons', 'md', '\n'.join(lignes) + '\n')
    print(f'{len(T)} leçons ; {os.path.basename(p)} ({"nouvelle version" if cree else "inchangé"})')


def verifier():
    T = toutes(); regles = {r['id'] for r in json.load(open(os.path.join(RACINE_CC, 'regles', 'regles_travail_v1.json'), encoding='utf-8'))['regles']}
    pb = 0
    for k, l in T.items():
        if l['statut'] == 'validee' and (not l['controle'] or l['controle'] == 'manuel'):
            print(f'{k} : validée sans contrôle automatique (à automatiser)'); pb += 1
        for c in re.findall(r'evaluer_travail:(\w+)', l['controle']):
            if c not in regles: print(f'{k} : règle {c} inconnue'); pb += 1
    print('leçons vérifiées :', len(T), '; à reprendre :', pb)
    return pb


if __name__ == '__main__':
    c = sys.argv[1]
    if c == 'ajouter': ajouter(sys.argv[2])
    elif c == 'lister': lister()
    elif c == 'verifier': sys.exit(1 if verifier() else 0)
