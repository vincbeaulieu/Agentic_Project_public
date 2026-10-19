"""
OUTIL: bilan_competences
VERSION: 2
RESUME: Trace d'apprentissage agrégée à partir du journal immuable : exécutions par outil et version, évolution de l'alignement par dossier évalué, résultats de banc par version (performance au sens large), leçons et délégations ; nouvelle version du bilan seulement si le contenu change.
USAGE: python3 bilan_competences_v2.py
ENTREES: journal/AAAA-MM-JJ/*.json ; bancs/*/resultats ; lecons ; delegations
SORTIES: catalogue/bilan_competences_vN.md
CATEGORIE: memoire
BANC: tests/test_bilan_competences_v2.py
REMPLACE: bilan_competences_v1 (noms de dossiers de l'espace écrits en dur, remplacés par le registre central cc_lib_v4.chemin) ; v1 : -
"""
import sys, os, json, glob, collections
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
from cc_lib_v4 import RACINE_CC, ecrire_versionne, chemin


def rel(p):
    """Chemin relatif à la racine de l'espace, avec « / » sur toutes les plateformes (bilan identique cloud et PC)."""
    return os.path.relpath(p, RACINE_CC).replace(os.sep, '/')


def main():
    ev = []
    for f in sorted(glob.glob(chemin('journal', '*', '*.json', racine=RACINE_CC))):
        try: ev.append(json.load(open(f, encoding='utf-8')))
        except Exception: pass
    reel = [e for e in ev if not (e.get('donnees') or {}).get('banc')]
    L = ['# Bilan des compétences', '', 'Généré par `outils/bilan_competences_v2.py` depuis le journal immuable.', '',
         f'{len(ev)} événements journalisés.', '', '## Exécutions par outil', '', '| Outil | Version | Type | Nombre |', '|---|---|---|---|']
    c = collections.Counter((e['outil'], e['version'], e['type']) for e in ev)
    L += [f'| {o} | v{v} | {t} | {n} |' for (o, v, t), n in sorted(c.items())]
    L += ['', '## Évaluations des dossiers de travail (alignement)', '', '| Date | Dossier | Verdict | Alignement | Règles en écart |', '|---|---|---|---|---|']
    for e in ev:
        if e['outil'] == 'evaluer_travail' and e['type'] == 'evaluation' and not str(e['donnees'].get('dossier', '')).startswith(('11_essai', '12_essai', '1_essai')):
            dd = e['donnees']; L.append(f"| {e['date']} | {dd['dossier']} | {dd['verdict']} | {dd['alignement']:.1%} | {', '.join(dd['regles_en_ecart'])} |")
    L += ['', '## Bancs d’essai (dernier résultat par version)', '',
          '| Outil | Version | F1 | Cas exacts | Durée (s) | CPU (s) | RSS (Ko) | Octets lus | Lignes | Déterministe | Sans LLM |', '|---|---|---|---|---|---|---|---|---|---|---|']
    for d in sorted(glob.glob(chemin('bancs', '*', 'resultats', racine=RACINE_CC))):
        der = {}
        for f in sorted(glob.glob(os.path.join(d, '*.json'))):
            r = json.load(open(f, encoding='utf-8')); der[r['version']] = r
        for v, r in sorted(der.items()):
            L.append(f"| {r['outil']} | v{v} | {r['qualite']['f1']} | {r['alignement']['cas_exacts']}/{r['alignement']['cas_total']} | {r['rapidite']['duree_mediane_s']} | "
                     f"{r['ressources']['cpu_median_s']} | {r['ressources']['rss_max_ko']} | {r['consultees']['octets_lus_median']} | {r['compacite']['lignes_code']} | "
                     f"{r['automatisation']['deterministe']} | {r['automatisation']['sans_llm']} |")
    nl = len(glob.glob(chemin('lecons', 'LC-*_v*.json', racine=RACINE_CC))); nd = len(glob.glob(chemin('delegations', 'D-*_v*.json', racine=RACINE_CC)))
    L += ['', f'## Leçons et délégations', '', f"- Fichiers de leçons : {nl} (registre : `{rel(chemin('lecons', 'registre_lecons_vN.md', racine=RACINE_CC))}`).",
          f"- Fichiers de délégations : {nd} (bilan : `{rel(chemin('delegations', 'bilan_delegations_vN.md', racine=RACINE_CC))}`).", '']
    p, cree = ecrire_versionne(chemin('catalogue', racine=RACINE_CC), 'bilan_competences', 'md', '\n'.join(L) + '\n')
    print(os.path.basename(p), 'nouvelle version' if cree else 'inchangé')


if __name__ == '__main__':
    main()
