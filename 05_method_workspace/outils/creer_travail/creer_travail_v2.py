"""
OUTIL: creer_travail
VERSION: 2
RESUME: Crée (ou complète sans rien écraser) un dossier de travail conforme aux règles O/E : 00_sources (copie des sources, lecture seule, sha256_sources_v1.txt, puis v2, v3… quand des sources s'ajoutent au rejeu), 01_plan, 90_scripts, 95_journal, 98_livrables, 99_livrables_modifiables, TRAVAIL_v1.json et LISEZMOI_v1.md.
USAGE: python3 creer_travail_v2.py <racine> <NN_sujet> --sujet "<texte>" --version-cible <M.0.0> [--auteur "Reevaluation - Claude"] [--couverture 0 23] [--relecteurs "A;B"] [--source <fichier> …]
ENTREES: fichiers sources (copiés tels quels, jamais déplacés)
SORTIES: arborescence du dossier ; événement dans journal/
CATEGORIE: organisation
BANC: tests/test_creer_travail_v2.py
REMPLACE: creer_travail_v1 (au rejeu, une source ajoutée était copiée sans que son empreinte soit écrite : une nouvelle version sha256_sources_v(N+1).txt reprend désormais toutes les empreintes sans toucher à la précédente, et une source absente arrête l'outil avant toute création) ; v1 : -
"""
import sys, os, re, json, shutil, stat, hashlib, argparse
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
from cc_lib_v1 import evenement
SOUS = ('00_sources', '01_plan', '90_scripts', '95_journal', '98_livrables', '99_livrables_modifiables')


def ecrire_empreintes(dossier, nouvelles):
    """Écrit sha256_sources_v(N+1).txt (v1 s'il n'y en a pas encore) avec toutes les empreintes : celles de la dernière version, puis
    celles des sources qui n'y figurent pas encore. Rien n'est écrit si aucune source n'est nouvelle ; une version existante n'est jamais modifiée."""
    versions = [int(m.group(1)) for x in os.listdir(dossier) for m in [re.fullmatch(r'sha256_sources_v(\d+)\.txt', x)] if m]
    derniere = max(versions, default=0); lignes = []
    if derniere:
        with open(os.path.join(dossier, f'sha256_sources_v{derniere}.txt'), encoding='utf-8') as f: lignes = f.read().splitlines()
    connus = {l.split('  ', 1)[1] for l in lignes if '  ' in l}
    ajout = [l for l in nouvelles if l.split('  ', 1)[1] not in connus]
    if not ajout: return
    fsha = os.path.join(dossier, f'sha256_sources_v{derniere + 1}.txt')
    with open(fsha, 'x', encoding='utf-8') as f: f.write('\n'.join(lignes + ajout) + '\n')
    os.chmod(fsha, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('racine'); ap.add_argument('nom'); ap.add_argument('--sujet', required=True); ap.add_argument('--version-cible', required=True)
    ap.add_argument('--auteur', default='Reevaluation - Claude'); ap.add_argument('--couverture', nargs=2, type=int)
    ap.add_argument('--relecteurs', default=''); ap.add_argument('--source', nargs='*', default=[])
    a = ap.parse_args()
    absentes = [f for f in a.source if not os.path.isfile(f)]
    if absentes: sys.exit('SOURCE ABSENTE : ' + ' ; '.join(absentes))             # avant de créer quoi que ce soit
    d = os.path.join(a.racine, a.nom)
    for s in SOUS: os.makedirs(os.path.join(d, s), exist_ok=True)
    nouvelles = []
    for f in a.source:
        dst = os.path.join(d, '00_sources', os.path.basename(f))
        if not os.path.exists(dst): shutil.copy2(f, dst)
        os.chmod(dst, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        nouvelles.append(f"{hashlib.sha256(open(dst, 'rb').read()).hexdigest()}  00_sources/{os.path.basename(f)}")
    ecrire_empreintes(os.path.join(d, '00_sources'), nouvelles)
    ft = os.path.join(d, 'TRAVAIL_v1.json')
    if not os.path.exists(ft):
        src = f"00_sources/{os.path.basename(a.source[0])}" if a.source else None
        json.dump(dict(sujet=a.sujet, source=src, auteur_revisions=a.auteur, version_cible=a.version_cible,
                       couverture=a.couverture, auteurs_relecteurs=[x for x in a.relecteurs.split(';') if x]),
                  open(ft, 'x', encoding='utf-8'), ensure_ascii=False, indent=1)
    fl = os.path.join(d, 'LISEZMOI_v1.md')
    if not os.path.exists(fl):
        open(fl, 'x', encoding='utf-8').write(
            f"# {a.nom} : {a.sujet}\n\n| Dossier | Contenu |\n|---|---|\n| `00_sources/` | Fichiers reçus, lecture seule, empreintes dans `sha256_sources_v1.txt` |\n"
            "| `01_plan/` … `89_…/` | Étapes du travail, dans l'ordre |\n| `90_scripts/` | Scripts propres à ce travail |\n"
            "| `95_journal/` | Audit, manifestes d'empreintes, évaluations |\n| `98_livrables/` | Livrables finaux, lecture seule, empreintes |\n"
            "| `99_livrables_modifiables/` | Copies des livrables, modifiables par l'usager |\n\n## État\n\nÀ compléter.\n")
    evenement('creer_travail', 2, 'creation', dict(dossier=a.nom, sources=[os.path.basename(f) for f in a.source]))
    print('dossier prêt :', d)


if __name__ == '__main__':
    main()
