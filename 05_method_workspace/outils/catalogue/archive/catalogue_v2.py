"""
OUTIL: catalogue
VERSION: 2
RESUME: Dictionnaire des outils généré automatiquement depuis l'en-tête standard de chaque script (OUTIL, VERSION, RESUME, USAGE, ENTREES, SORTIES, CATEGORIE, BANC, REMPLACE) ; version courante, versions antérieures, dernier résultat de banc ; signale les en-têtes incomplets. Écrit une nouvelle version du catalogue seulement si son contenu change.
USAGE: python3 outils/catalogue.py
ENTREES: scripts *.py avec en-tête standard
SORTIES: catalogue/catalogue_outils_vN.md et catalogue/catalogue_outils_vN.json (nouvelle version si changement) ; événement dans journal/
CATEGORIE: memoire
BANC: -
REMPLACE: catalogue_v1 (organisation par dossier d'outil : version courante = le fichier de outils/<outil>/, versions archivées comptées ; outils PowerShell, cmd et documents listés ; raccourci à utiliser indiqué) ; v1 : -
"""
import sys, os, re, json, glob
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
from cc_lib_v1 import RACINE_CC, lire_entete, CHAMPS_ENTETE, ecrire_versionne, evenement


def dernier_banc(outil, version):
    rdir = os.path.join(RACINE_CC, 'bancs', outil, 'resultats')
    if not os.path.isdir(rdir): return None
    c = sorted(f for f in os.listdir(rdir) if f.startswith(f'resultat_{outil}_v{version}_'))
    if not c: return None
    r = json.load(open(os.path.join(rdir, c[-1]), encoding='utf-8'))
    return dict(f1=r['qualite']['f1'], cas=f"{r['alignement']['cas_exacts']}/{r['alignement']['cas_total']}",
                duree_s=r['rapidite']['duree_mediane_s'], deterministe=r['automatisation']['deterministe'], date=r['date'])


def main():
    O = os.path.join(RACINE_CC, 'outils'); outils, incomplets = {}, []
    for d in sorted(os.listdir(O)):
        p = os.path.join(O, d)
        if not os.path.isdir(p) or d.startswith('_') or d in ('__pycache__', 'archive'): continue
        for f in sorted(glob.glob(os.path.join(p, f'{d}_v*.*'))):
            ext = f.rsplit('.', 1)[-1]
            e = lire_entete(f) if ext == 'py' else {k: v for k, v in (re.match(r'^\s*#\s*([A-Z]+):\s*(.*)$', l).groups() for l in open(f, encoding='utf-8', errors='replace').read(4000).splitlines() if re.match(r'^\s*#\s*[A-Z]+:', l))}
            if ext == 'md': e = dict(OUTIL=d, VERSION=re.search(r'_v(\d+)\.md$', f).group(1), RESUME=open(f, encoding='utf-8').readline().strip('# \n'), CATEGORIE='document', USAGE='lire', REMPLACE='-')
            e.setdefault('OUTIL', d); e.setdefault('VERSION', re.search(r'_v(\d+)\.', f).group(1))
            manq = [c for c in CHAMPS_ENTETE if c not in e]
            if manq and ext == 'py': incomplets.append(dict(fichier=os.path.relpath(f, RACINE_CC), manquants=manq))
            e['fichier'] = os.path.relpath(f, os.path.dirname(RACINE_CC)); e['raccourci'] = f'outils/{d}.py' if ext == 'py' else f'outils/{d}/'
            e['archivees'] = len(glob.glob(os.path.join(p, 'archive', f'{d}_v*.{ext}')))
            outils.setdefault(e['OUTIL'], []).append(e)
    lignes = ['# Catalogue des outils', '',
              'Généré par `outils/catalogue_v2.py` à partir des en-têtes. Ne pas éditer à la main : relancer le générateur.', '',
              '| Outil | Version courante | Catégorie | Résumé | Banc |', '|---|---|---|---|---|']
    js = []
    for nom in sorted(outils):
        vs = sorted(outils[nom], key=lambda e: int(re.sub(r'\D', '', e['VERSION']) or 0))
        cur = vs[-1]; b = dernier_banc(nom, cur['VERSION'])
        btxt = f"F1 {b['f1']}, {b['cas']} cas, {b['duree_s']} s" if b else ('à créer' if cur.get('BANC', '-') not in ('-', '') else '—')
        lignes.append(f"| `{nom}` | v{cur['VERSION']} | {cur.get('CATEGORIE', '')} | {cur.get('RESUME', '')} | {btxt} |")
        js.append(dict(outil=nom, version=cur['VERSION'], raccourci=cur.get('raccourci'), archivees=cur.get('archivees'), categorie=cur.get('CATEGORIE'), resume=cur.get('RESUME'), usage=cur.get('USAGE'),
                       entrees=cur.get('ENTREES'), sorties=cur.get('SORTIES'), fichier=cur['fichier'], banc=b,
                       remplace=cur.get('REMPLACE'), versions=[v['VERSION'] for v in vs]))
        js[-1]['versions'] = [str(x) for x in range(1, int(re.sub(r'\D', '', cur['VERSION']) or 1) + 1)]
    lignes += ['', '## Usage', '']
    for o in js:
        lignes += [f"### `{o['outil']}` v{o['version']}", f"- Lancer : `python3 {o['raccourci']}`" if str(o['raccourci']).endswith('.py') else f"- Dossier : `{o['raccourci']}`", f"- Fichier : `{o['fichier']}`", f"- Usage : `{o['usage']}`",
                   f"- Entrées : {o['entrees']}", f"- Sorties : {o['sorties']}",
                   f"- Versions archivées : {o['archivees']} ; remplace : {o['remplace']}", '']
    if incomplets:
        lignes += ['## En-têtes incomplets', ''] + [f"- `{x['fichier']}` : {', '.join(x['manquants'])}" for x in incomplets]
    cdir = os.path.join(RACINE_CC, 'catalogue')
    pm, cm = ecrire_versionne(cdir, 'catalogue_outils', 'md', '\n'.join(lignes) + '\n')
    pj, cj = ecrire_versionne(cdir, 'catalogue_outils', 'json', json.dumps(js, ensure_ascii=False, indent=1, sort_keys=True) + '\n')
    evenement('catalogue', 2, 'catalogue', dict(outils=len(js), incomplets=len(incomplets), fichier=os.path.basename(pm), nouveau=cm or cj))
    print(f"{len(js)} outils ; {len(incomplets)} en-tête(s) incomplet(s) ; {os.path.basename(pm)} ({'nouvelle version' if cm else 'inchangé'})")
    for x in incomplets: print('   incomplet :', x['fichier'], x['manquants'])


if __name__ == '__main__':
    main()
