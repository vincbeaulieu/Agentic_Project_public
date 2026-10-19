"""
OUTIL: file_lmstudio
VERSION: 1
RESUME: Côté cloud de la file de micro-tâches LM Studio : installe l'ouvrier sur le PC (worker_lmstudio + lanceur + consignes), dépose des lots de micro-tâches (priorité, modèle, consigne nommée : le texte de la consigne n'est pas répété), récolte les résultats rapatriés et les convertit au format de microtaches (combiner, evaluer). La charge passe par des fichiers (device_commit_files / device_stage_files), jamais par la conversation.
USAGE: python3 file_lmstudio_v1.py installer <dossier_travail>
       python3 file_lmstudio_v1.py deposer <microtaches.jsonl> <dossier_travail> --lot NOM --modele M [--prio 2] [--ids id1,id2|@fichier] [--type MT-DEMANDE]
       python3 file_lmstudio_v1.py recolter <dossier_travail> --lot NOM
ENTREES: microtaches_vN.jsonl (microtaches) ; résultats rapatriés dans /mnt/user-data/uploads/Revision/00_espace_cloud_claude/file_lmstudio/sortie/
SORTIES: <dossier_travail>/file/entree/<lot>_vN.jsonl (copie de travail) ; envoi préparé dans /mnt/user-data/outputs/file_lmstudio/ ; liste JSON pour device_commit_files ; <dossier_travail>/file/sortie/<lot>_resultats_vN.json (lignes [modèle, id, valeur, ms, tokens, 0]) ; événement dans journal/
CATEGORIE: delegation_locale
BANC: -
REMPLACE: -
"""
import sys, os, re, json, shutil, glob
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
from cc_lib_v1 import evenement, ecrire_versionne, derniere_version
sys.path.insert(0, '/home/claude/07_excel_update/scripts')
from sync_cloud_pc import REV                                   # racine Revision sur le PC
M = __import__('microtaches_v4')
ENVOI = '/mnt/user-data/outputs/file_lmstudio'
RAPATRIE = '/mnt/user-data/uploads/Revision/00_espace_cloud_claude/file_lmstudio'
PC = REV + r'\00_espace_cloud_claude\file_lmstudio'
CONSIGNE = {'MT-PRESENCE': 'MT-PRESENCE_v1', 'MT-DEMANDE': 'MT-DEMANDE_v1'}
def opt(a, k, d=None): return a[a.index(k) + 1] if k in a else d


def envoyer(rel, contenu, bom=False):
    f = os.path.join(ENVOI, rel); os.makedirs(os.path.dirname(f), exist_ok=True)
    if os.path.exists(f): os.remove(f)                          # zone d'envoi (transport), pas une version
    with open(f, 'wb') as g: g.write((b'\xef\xbb\xbf' if bom else b'') + contenu.encode('utf-8'))
    return dict(stagedPath=f, devicePath=PC + '\\' + rel.replace('/', '\\'))


def installer(a):
    d = a[0]; L = []
    for nom in ('worker_lmstudio', 'lancer_worker_lmstudio'):
        src = derniere_version(H, nom, 'ps1' if nom == 'worker_lmstudio' else 'cmd')
        L.append(envoyer('outil/' + os.path.basename(src), open(src, encoding='utf-8').read(), bom=src.endswith('.ps1')))
    for ty, nom in CONSIGNE.items():
        ecrire_versionne(os.path.join(d, 'file', 'consignes'), nom, 'txt', M.CONSIGNES[ty])
        L.append(envoyer(f'consignes/{nom}.txt', M.CONSIGNES[ty]))
    evenement('file_lmstudio', 1, 'installer', dict(fichiers=len(L))); print(json.dumps(L, ensure_ascii=False))


def deposer(a):
    src, d = a[0], a[1]; lot, modele = opt(a, '--lot'), opt(a, '--modele'); prio = float(opt(a, '--prio', 2))
    ids = opt(a, '--ids'); ty = opt(a, '--type')
    if ids and ids.startswith('@'): ids = set(json.load(open(ids[1:], encoding='utf-8')))
    elif ids: ids = set(ids.split(','))
    X = [x for x in M.charger(src) if (not ids or x['id'] in ids) and (not ty or x['type'] == ty)]
    lignes = [json.dumps(dict(id=x['id'], prio=prio, modele=modele, consigne=CONSIGNE[x['type']], u=M.entree(x),
                              valeurs=M.VALEURS[x['type']], max_tokens=40), ensure_ascii=False, sort_keys=True) for x in X]
    contenu = '\n'.join(lignes) + '\n'
    ch, _ = ecrire_versionne(os.path.join(d, 'file', 'entree'), lot, 'jsonl', contenu)
    nom = os.path.basename(ch)[:-6]                              # le lot porte sa version : <lot>_vN
    L = [envoyer(f'entree/{nom}.jsonl', contenu)]
    evenement('file_lmstudio', 1, 'deposer', dict(lot=nom, taches=len(X), modele=modele, prio=prio))
    print(f'{len(X)} tâche(s) ; lot {nom}'); print(json.dumps(L, ensure_ascii=False))


def recolter(a):
    d, lot = a[0], opt(a, '--lot')
    f = os.path.join(RAPATRIE, 'sortie', f'{lot}_resultats.jsonl')
    R = [json.loads(l) for l in open(f, encoding='utf-8') if l.strip()]
    rows = [[r['modele'], r['id'], r.get('r'), r.get('ms'), r.get('tokens'), 0] for r in R]
    ch, cree = ecrire_versionne(os.path.join(d, 'file', 'sortie'), f'{lot}_resultats', 'json', json.dumps(rows, ensure_ascii=False))
    err = sum(1 for r in R if r.get('erreur'))
    evenement('file_lmstudio', 1, 'recolter', dict(lot=lot, resultats=len(R), erreurs=err))
    print(f'{len(R)} résultat(s), {err} erreur(s) -> {ch}')


if __name__ == '__main__':
    {'installer': installer, 'deposer': deposer, 'recolter': recolter}[sys.argv[1]](sys.argv[2:])
