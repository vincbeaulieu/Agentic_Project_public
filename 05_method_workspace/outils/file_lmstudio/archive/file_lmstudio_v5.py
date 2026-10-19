"""
OUTIL: file_lmstudio
VERSION: 5
RESUME: Côté cloud de la file de micro-tâches LM Studio : installe l'ouvrier sur le PC (worker_lmstudio + lanceur + consignes), dépose des lots de micro-tâches (priorité, modèle, consigne nommée : le texte de la consigne n'est pas répété), récolte les résultats rapatriés et les convertit au format de microtaches (combiner, evaluer). La charge passe par des fichiers (device_commit_files / device_stage_files), jamais par la conversation.
USAGE: (sur le PC, de préférence) python3 file_lmstudio_v5.py installer <dossier_travail>
       python3 file_lmstudio_v5.py deposer <microtaches.jsonl> <dossier_travail> --lot NOM --modele M [--prio 2] [--ids id1,id2|@fichier] [--type MT-DEMANDE]
       python3 file_lmstudio_v5.py deposer-embeddings <microtaches.jsonl> <dossier_travail> --lot NOM [--modele text-embedding-nomic-embed-text-v1.5] [--prio 3]
       python3 file_lmstudio_v5.py recolter <dossier_travail> --lot NOM
ENTREES: microtaches_vN.jsonl (microtaches) ; résultats rapatriés dans /mnt/user-data/uploads/Revision/00_espace_cloud_claude/file_lmstudio/sortie/
SORTIES: <dossier_travail>/file/entree/<lot>_vN.jsonl (copie de travail) ; envoi préparé dans /mnt/user-data/outputs/file_lmstudio/ ; liste JSON pour device_commit_files ; <dossier_travail>/file/sortie/<lot>_resultats_vN.json (lignes [modèle, id, valeur, ms, tokens, 0]) ; événement dans journal/
CATEGORIE: delegation_locale
BANC: -
REMPLACE: file_lmstudio_v4 (mode local détecté depuis la racine de l'espace de compétences et non plus depuis le dossier du script, qui a changé avec l'organisation par dossier d'outil) ; v4 : file_lmstudio_v3 (ouvrier, lanceur et README trouvés dans leur dossier d'outil par le moteur des raccourcis ; README déployé avec l'ouvrier) ; v3 : file_lmstudio_v2 (microtaches courant via le registre ; recolter verse les embeddings dans le cache du répertoire d'entraînement, clé = empreinte du texte) ; v2 remplaçait file_lmstudio_v1 (mode local : lancé sur le PC, dans la VM, l'outil écrit et lit directement dans Revision\00_espace_cloud_claude\file_lmstudio, sans transit par le cloud ; + deposer-embeddings : textes des demandes, phrases A et extraits B des présences, pour les classifieurs déterministes)
"""
import sys, os, re, json, shutil, glob
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
from cc_lib_v1 import evenement, ecrire_versionne, derniere_version, RACINE_CC
from cc_lib_v2 import importer
M = importer('microtaches')
LOCALE = os.path.join(os.path.dirname(RACINE_CC), '00_espace_cloud_claude', 'file_lmstudio')   # Revision/… quand l'outil tourne sur le PC
LOCAL = os.path.isdir(LOCALE)                                    # vrai quand l'outil tourne sur le PC (VM)
if LOCAL:
    ENVOI = RAPATRIE = LOCALE; PC = None
else:
    sys.path.insert(0, '/home/claude/07_excel_update/scripts')
    from sync_cloud_pc import REV                               # racine Revision sur le PC
    ENVOI = '/mnt/user-data/outputs/file_lmstudio'
    RAPATRIE = '/mnt/user-data/uploads/Revision/00_espace_cloud_claude/file_lmstudio'
    PC = REV + r'\00_espace_cloud_claude\file_lmstudio'
CONSIGNE = {'MT-PRESENCE': 'MT-PRESENCE_v1', 'MT-DEMANDE': 'MT-DEMANDE_v1'}
def opt(a, k, d=None): return a[a.index(k) + 1] if k in a else d


def envoyer(rel, contenu, bom=False):
    f = os.path.join(ENVOI, rel); os.makedirs(os.path.dirname(f), exist_ok=True)
    if LOCAL:                                                    # sur le PC : jamais d'écrasement
        if os.path.exists(f): raise SystemExit('existe déjà : ' + f)
        t = f + '.tmp'
        with open(t, 'wb') as g: g.write((b'\xef\xbb\xbf' if bom else b'') + contenu.encode('utf-8'))
        os.rename(t, f); return dict(local=f)
    if os.path.exists(f): os.remove(f)                          # zone d'envoi (transport), pas une version
    with open(f, 'wb') as g: g.write((b'\xef\xbb\xbf' if bom else b'') + contenu.encode('utf-8'))
    return dict(stagedPath=f, devicePath=PC + '\\' + rel.replace('/', '\\'))


def installer(a):
    d = a[0]; L = []
    import _raccourci_v2 as RC
    for nom, ext, ou in (('worker_lmstudio', 'ps1', 'outil/'), ('lancer_worker_lmstudio', 'cmd', 'outil/'), ('README_file_lmstudio', 'md', '')):
        src = RC.chemin_outil(nom, ext=ext)
        L.append(envoyer(ou + os.path.basename(src), open(src, encoding='utf-8').read(), bom=src.endswith('.ps1')))
    for ty, nom in CONSIGNE.items():
        ecrire_versionne(os.path.join(d, 'file', 'consignes'), nom, 'txt', M.CONSIGNES[ty])
        L.append(envoyer(f'consignes/{nom}.txt', M.CONSIGNES[ty]))
    evenement('file_lmstudio', 5, 'installer', dict(fichiers=len(L))); print(json.dumps(L, ensure_ascii=False))


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
    evenement('file_lmstudio', 5, 'deposer', dict(lot=nom, taches=len(X), modele=modele, prio=prio))
    print(f'{len(X)} tâche(s) ; lot {nom}'); print(json.dumps(L, ensure_ascii=False))


def deposer_embeddings(a):
    src, d = a[0], a[1]; lot = opt(a, '--lot'); modele = opt(a, '--modele', 'text-embedding-nomic-embed-text-v1.5'); prio = float(opt(a, '--prio', 3))
    L = []
    for x in M.charger(src):
        if x['type'] == 'MT-DEMANDE': L.append((x['id'] + '#t', x['texte']))
        else: L += [(x['id'] + '#a', x['a']), (x['id'] + '#b', x['b'])]
    contenu = ''.join(json.dumps(dict(id=i, prio=prio, modele=modele, type='embedding', u=u), ensure_ascii=False, sort_keys=True) + '\n' for i, u in L)
    ch, _ = ecrire_versionne(os.path.join(d, 'file', 'entree'), lot, 'jsonl', contenu)
    nom = os.path.basename(ch)[:-6]; E = [envoyer(f'entree/{nom}.jsonl', contenu)]
    evenement('file_lmstudio', 5, 'deposer_embeddings', dict(lot=nom, taches=len(L), modele=modele))
    print(f'{len(L)} embedding(s) ; lot {nom}'); print(json.dumps(E, ensure_ascii=False))


def recolter(a):
    d, lot = a[0], opt(a, '--lot')
    f = os.path.join(RAPATRIE, 'sortie', f'{lot}_resultats.jsonl')
    R = [json.loads(l) for l in open(f, encoding='utf-8') if l.strip()]
    if R and isinstance(R[0].get('r'), list):                  # embeddings : {id: vecteur}
        ch, cree = ecrire_versionne(os.path.join(d, 'file', 'sortie'), f'{lot}_vecteurs', 'json', json.dumps({r['id']: r['r'] for r in R if r.get('r')}))
        import hashlib
        textes = {json.loads(l)['id']: json.loads(l) for l in open(os.path.join(d, 'file', 'entree', f'{lot}.jsonl'), encoding='utf-8') if l.strip()}
        cache = {hashlib.sha256(textes[r['id']]['u'].encode()).hexdigest()[:16]: r['r'] for r in R if r.get('r') and r['id'] in textes}
        modele = R[0]['modele'].replace('/', '_'); cd = os.path.join(RACINE_CC, 'entrainement', 'traits', modele)
        c2, _ = ecrire_versionne(cd, f'vecteurs_{lot}', 'json', json.dumps(cache))
        print(f'{len(R)} vecteur(s) -> {ch} ; cache d’entraînement : {os.path.relpath(c2, RACINE_CC)}'); return
    rows = [[r['modele'], r['id'], r.get('r'), r.get('ms'), r.get('tokens'), 0] for r in R]
    ch, cree = ecrire_versionne(os.path.join(d, 'file', 'sortie'), f'{lot}_resultats', 'json', json.dumps(rows, ensure_ascii=False))
    err = sum(1 for r in R if r.get('erreur'))
    evenement('file_lmstudio', 5, 'recolter', dict(lot=lot, resultats=len(R), erreurs=err))
    print(f'{len(R)} résultat(s), {err} erreur(s) -> {ch}')


if __name__ == '__main__':
    {'installer': installer, 'deposer': deposer, 'deposer-embeddings': deposer_embeddings, 'recolter': recolter}[sys.argv[1]](sys.argv[2:])
