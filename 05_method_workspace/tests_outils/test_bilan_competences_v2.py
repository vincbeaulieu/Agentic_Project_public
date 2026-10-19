"""Tests unitaires de bilan_competences v2 (registre central des dossiers, cc_lib_v4.chemin). Aucune suite précédente.
(a) Non-régression : sur un espace fictif aux noms par défaut (journal, bancs, leçons, délégations), la v2 écrit le même
bilan que la v1 (seule la ligne « Généré par » change) ; relancée, elle n'écrit pas de nouvelle version.
(b) Registre : dans un espace fictif dont outils/_gestion/chemins_v1.json renomme ces dossiers et celui du catalogue, la v2
compte les événements, bancs, leçons et délégations des dossiers renommés (pas les leurres aux noms par défaut), cite les
chemins renommés dans le bilan et écrit le bilan dans le dossier du catalogue renommé.
Le journal réel n'est pas lu : d'autres exécutions peuvent y écrire pendant les tests. Les essais n'écrivent que dans
tests/_test_execution/ (dossier_essai) ; aucun nom de dossier de l'espace n'est écrit en dur."""
import os, io, re, sys, json, glob, unittest, contextlib
from unittest import mock
sys.dont_write_bytecode = True          # aucun cache .pyc écrit hors de tests/ par les versions essayées
from aide_tests_v2 import dossier_essai, chemin_version, importer_version, chemin, RACINE_CC
import cc_lib_v4

OUTIL = 'bilan_competences'
RENOMMES = dict(journal='renomme_journal', bancs='renomme_bancs', lecons='renomme_lecons', delegations='renomme_delegations',
                catalogue='renomme_catalogue')


def muet(f):
    s = io.StringIO()
    with contextlib.redirect_stdout(s): f()
    return s.getvalue()


def ecrire(f, texte):
    os.makedirs(os.path.dirname(f), exist_ok=True)
    with open(f, 'x', encoding='utf-8') as g: g.write(texte)


def lire(f):
    with open(f, encoding='utf-8') as g: return g.read()


def num(f): return int(re.search(r'_v(\d+)\.md$', f).group(1))
def rel(p, r): return os.path.relpath(p, r).replace(os.sep, '/')


def evaluation(dossier, verdict, alignement, ecarts):
    return dict(date='2026-10-15T10:00:00Z', outil='evaluer_travail', version=4, type='evaluation',
                donnees=dict(dossier=dossier, verdict=verdict, alignement=alignement, regles_en_ecart=ecarts))


def peupler(r, complet, f1):
    """Contenu des dossiers que désigne le registre au moment de l'appel. complet=False : leurre réduit (1 événement, 5 leçons, 4 délégations)."""
    j = chemin('journal', '2026-10-15', racine=r)
    ev = [evaluation('20_sujet_fictif', 'CONFORME', 0.95, ['N3'])]
    if complet:
        ev += [evaluation('11_essai_fictif', 'NON CONFORME', 0.5, ['E1']),                   # dossier d'essai : hors du tableau
               dict(date='2026-10-15T10:01:00Z', outil='chercher_outil', version=2, type='recherche', donnees=dict(requete='x', resultats=1)),
               dict(date='2026-10-15T10:02:00Z', outil='chercher_outil', version=2, type='recherche', donnees=dict(requete='y', resultats=0, banc=True))]
        ecrire(os.path.join(j, '20261015_100300_illisible.json'), '{')                        # ignoré
    for i, e in enumerate(ev): ecrire(os.path.join(j, f'20261015_10000{i}_{e["outil"]}_v{e["version"]}_{i:08x}.json'), json.dumps(e))
    ecrire(chemin('bancs', 'outil_a', 'resultats', 'resultat_outil_a_v1_20261015_100000.json', racine=r), json.dumps(dict(
        outil='outil_a', version=1, qualite=dict(f1=f1), alignement=dict(cas_exacts=3, cas_total=4), rapidite=dict(duree_mediane_s=0.05),
        ressources=dict(cpu_median_s=0.04, rss_max_ko=12000), consultees=dict(octets_lus_median=2048), compacite=dict(lignes_code=120),
        automatisation=dict(deterministe=True, sans_llm=True))))
    for i in range(1, (2 if complet else 5) + 1): ecrire(chemin('lecons', f'LC-{i:03d}_v1.json', racine=r), '{}')
    for i in range(1, (1 if complet else 4) + 1): ecrire(chemin('delegations', f'D-{i:03d}_v1.json', racine=r), '{}')


def lancer(v, r):
    M = importer_version(OUTIL, v)
    with mock.patch.object(M, 'RACINE_CC', r): return muet(M.main)


class NonRegression(unittest.TestCase):
    def test_meme_bilan_que_v1(self):
        r = dossier_essai('bilan_v1_v2'); peupler(r, True, 0.9)
        lancer(1, r); s = lancer(2, r)
        md = sorted(glob.glob(chemin('catalogue', '*.md', racine=r)), key=num); self.assertEqual(len(md), 2); self.assertIn('nouvelle version', s)
        a, b = lire(md[0]).splitlines(), lire(md[1]).splitlines()
        self.assertEqual(a[:2] + a[3:], b[:2] + b[3:]); self.assertIn('_v1.py', a[2]); self.assertIn('_v2.py', b[2])
        t = lire(md[1])
        for ligne in ('4 événements journalisés.', '| chercher_outil | v2 | recherche | 2 |', '| evaluer_travail | v4 | evaluation | 2 |',
                      '| 2026-10-15T10:00:00Z | 20_sujet_fictif | CONFORME | 95.0% | N3 |',
                      '| outil_a | v1 | 0.9 | 3/4 | 0.05 | 0.04 | 12000 | 2048 | 120 | True | True |'):
            self.assertIn(ligne, t)
        self.assertNotIn('11_essai_fictif', t)
        self.assertIn(f"- Fichiers de leçons : 2 (registre : `{rel(chemin('lecons', 'registre_lecons_vN.md', racine=r), r)}`).", t)
        self.assertIn(f"- Fichiers de délégations : 1 (bilan : `{rel(chemin('delegations', 'bilan_delegations_vN.md', racine=r), r)}`).", t)
        self.assertIn('inchangé', lancer(2, r)); self.assertEqual(len(glob.glob(chemin('catalogue', '*', racine=r))), 2)   # déterministe


class Registre(unittest.TestCase):
    def test_dossiers_renommes(self):
        r = dossier_essai('bilan_registre')
        peupler(r, False, 0.1)                                                    # leurres, aux noms par défaut (pas encore de registre)
        leurres = set(os.listdir(r))
        ecrire(chemin('outils', '_gestion', 'chemins_v1.json', racine=r), json.dumps(dict(chemins=RENOMMES)))
        for k, v in RENOMMES.items(): self.assertEqual(chemin(k, racine=r), os.path.join(r, v))
        peupler(r, True, 0.9)                                                     # dossiers renommés
        self.assertIn('nouvelle version', lancer(2, r))
        self.assertEqual(set(os.listdir(r)), leurres | {os.path.basename(chemin('outils', racine=r))} | set(RENOMMES.values()))
        md = glob.glob(chemin('catalogue', '*.md', racine=r)); self.assertEqual(len(md), 1)     # bilan dans le catalogue renommé
        t = lire(md[0])
        self.assertIn('4 événements journalisés.', t); self.assertIn('| outil_a | v1 | 0.9 |', t); self.assertNotIn('| 0.1 |', t)
        lecons = rel(chemin('lecons', 'registre_lecons_vN.md', racine=r), r); deleg = rel(chemin('delegations', 'bilan_delegations_vN.md', racine=r), r)
        self.assertIn(f'- Fichiers de leçons : 2 (registre : `{lecons}`).', t); self.assertIn(f'- Fichiers de délégations : 1 (bilan : `{deleg}`).', t)


class Entete(unittest.TestCase):
    def test_banc_et_remplace(self):
        e = cc_lib_v4.lire_entete(chemin_version(OUTIL, 2))
        self.assertEqual(e['VERSION'], '2')
        self.assertEqual(e['BANC'], 'tests/' + os.path.basename(__file__))   # chemin logique (clé « tests »), stable si le dossier est renommé
        self.assertEqual(e['REMPLACE'], f"{OUTIL}_v1 (noms de dossiers de l'espace écrits en dur, remplacés par le registre central cc_lib_v4.chemin) ; v1 : -")


if __name__ == '__main__':
    unittest.main()
