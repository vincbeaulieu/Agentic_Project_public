"""
OUTIL: verifier_sauvegarde
VERSION: 1
RESUME: Contrôle déterministe de la sauvegarde locale : liste les fichiers du cloud (dossiers NN_…, fichiers racine) dont le contenu actuel n'a pas encore été confirmé sur le PC (état de sync_cloud_pc_v4), avec l'âge du plus ancien ; échoue si un fichier attend depuis plus que le seuil (15 min par défaut).
USAGE: python3 verifier_sauvegarde_v1.py [--seuil-min 15] [--details]
ENTREES: /home/claude/.sync_cloud_pc/etat.json ; inventaire de 07_excel_update/scripts/sync_cloud_pc_v4.py
SORTIES: « SAUVEGARDE À JOUR » ou « SAUVEGARDE EN RETARD : N fichiers, le plus ancien depuis X min » ; code 0 / 1 ; événement dans journal/
CATEGORIE: sauvegarde
BANC: -
REMPLACE: -
"""
import sys, os, json, time
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
from cc_lib_v1 import evenement
sys.path.insert(0, '/home/claude/07_excel_update/scripts')
import sync_cloud_pc_v4 as V
import sync_cloud_pc as S


def main():
    seuil = float(sys.argv[sys.argv.index('--seuil-min') + 1]) if '--seuil-min' in sys.argv else 15.0
    E = V.charger(); now = time.time()
    par_dossier = {}
    for p, h in E['pc'].items(): par_dossier.setdefault(p.split('/')[0], set()).add(h)
    tous = set(E['pc'].values()); attente = []
    for full, rel, dest, cat in V.inventaire():
        h = S.h16(full)
        if E['envoyes'].get(rel) == h or E['pc'].get(dest) == h: continue
        if cat == 'dossier' and h in par_dossier.get(dest.split('/')[0], ()): continue
        if cat == 'hors' and h in tous: continue
        attente.append((now - os.path.getmtime(full), rel))
    attente.sort(reverse=True)
    vieux = [a for a in attente if a[0] > seuil * 60]
    if not attente: print('SAUVEGARDE À JOUR : tous les fichiers du cloud sont confirmés sur le PC')
    else:
        print(f"SAUVEGARDE {'EN RETARD' if vieux else 'EN COURS'} : {len(attente)} fichier(s) non confirmés, le plus ancien depuis {attente[0][0] / 60:.0f} min")
        if '--details' in sys.argv or vieux:
            for age, rel in attente[:25]: print(f'   {age / 60:5.0f} min  {rel}')
    evenement('verifier_sauvegarde', 1, 'controle', dict(en_attente=len(attente), en_retard=len(vieux), seuil_min=seuil))
    return 1 if vieux else 0


if __name__ == '__main__':
    sys.exit(main())
