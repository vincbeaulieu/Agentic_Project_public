"""Tests unitaires de cc_lib_v5 : racine de l'espace trouvée d'elle-même (marqueur outils/_gestion/) et racine fausse qui
échoue bruyamment. Tests négatifs (LC-032) : on prouve d'abord que le défaut existe (cc_lib_v1 importée depuis son rangement,
sans le raccourci de compatibilité, donne en silence la racine outils/cc_lib : cas du 16 oct. 2026, « 0 délégation »), puis que
v5 importée de la même façon lève ImportError ; importée par outils/_compat, elle trouve la bonne racine. Non-régression :
registre central des dossiers et journal (comme test_cc_lib_v4), avec la racine de v5. Les sous-processus tournent en mode
isolé (-I) : ni PYTHONPATH ni dossier courant n'interviennent, seuls les chemins donnés par le test."""
import os, sys, json, subprocess, unittest
from unittest import mock
from test_cc_lib_v3 import Noms, EcritureVersionnee, Registre, NomsRev, VersionLivrable   # noqa: F401 (non-régression)
from aide_tests_v2 import dossier_essai, chemin_version, OUTILS
import cc_lib_v4 as L4
from aide_tests_v2 import importer_version

L5 = importer_version('cc_lib', 5, alias='cc_lib_v5_essai')
RACINE = os.path.dirname(OUTILS)
D5, D4, D1 = (os.path.dirname(chemin_version('cc_lib', v)) for v in (5, 4, 1))
COMPAT = os.path.join(OUTILS, '_compat')


def python_isole(chemins, code):
    """Lance python -I avec sys.path préfixé des chemins donnés ; rend (code de sortie, sortie, erreurs)."""
    prog = f'import sys; sys.path[:0] = {chemins!r}\n' + code
    r = subprocess.run([sys.executable, '-I', '-c', prog], capture_output=True, text=True, timeout=60, cwd=RACINE)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


class Racine(unittest.TestCase):
    def test_racine_trouvee_et_identique_a_v4(self):
        self.assertEqual(L5.RACINE_CC, RACINE)
        self.assertEqual(os.path.abspath(L4.RACINE_CC), L5.RACINE_CC)
        self.assertTrue(os.path.isdir(os.path.join(L5.RACINE_CC, 'outils', '_gestion')))

    def test_racine_espace_remonte_depuis_un_sous_dossier(self):
        self.assertEqual(L5.racine_espace(os.path.join(OUTILS, 'cc_lib', 'archive')), RACINE)
        self.assertEqual(L5.racine_espace(dossier_essai('cc_lib_v5_sous_dossier')), RACINE)

    def test_sans_marqueur_echec_bruyant(self):
        hors = os.path.dirname(RACINE)
        d, sans = hors, True   # défaut bien injecté : aucun dossier au-dessus de l'espace ne porte le marqueur
        while True:
            sans = sans and not os.path.isdir(os.path.join(d, 'outils', '_gestion'))
            if os.path.dirname(d) == d: break
            d = os.path.dirname(d)
        self.assertTrue(sans, 'un dossier parent de l’espace porte outils/_gestion : test non concluant')
        with self.assertRaises(ImportError) as e: L5.racine_espace(hors)
        self.assertIn('racine de l’espace introuvable', str(e.exception))

    def test_verifier_racine(self):
        self.assertEqual(L5.verifier_racine(RACINE), RACINE)
        with self.assertRaises(ImportError) as e: L5.verifier_racine(os.path.join(OUTILS, 'cc_lib'))
        self.assertIn('outils/<outil>.py', str(e.exception))


class ImportHorsRaccourci(unittest.TestCase):
    def test_defaut_v1_silencieux(self):
        """Le défaut existe : v1 importée depuis son rangement donne outils/cc_lib comme racine, sans aucune erreur."""
        code, out, err = python_isole([D1], 'import cc_lib_v1; print(cc_lib_v1.RACINE_CC)')
        self.assertEqual(code, 0, err)
        self.assertEqual(out, os.path.dirname(D1))
        self.assertNotEqual(out, RACINE)

    def test_v5_hors_raccourci_echoue(self):
        code, out, err = python_isole([D5, D4, D1], 'import cc_lib_v5')
        self.assertNotEqual(code, 0, out)
        self.assertIn('ImportError', err); self.assertIn('hors raccourci', err)

    def test_v5_par_compat_trouve_la_racine(self):
        code, out, err = python_isole([COMPAT, D5], 'import cc_lib_v5; print(cc_lib_v5.RACINE_CC)')
        self.assertEqual((code, out), (0, RACINE), err)


class Chemins(unittest.TestCase):
    def test_defauts_et_registre(self):
        r = dossier_essai('chemins_v5'); g = os.path.join(r, 'outils', '_gestion'); os.makedirs(g)
        self.assertEqual(L5.chemin('lecons', 'a.json', racine=r), os.path.join(r, 'lecons', 'a.json'))
        self.assertEqual(L5.chemins(r)['propositions'], 'propositions_a_reviser')
        with open(os.path.join(g, 'chemins_v1.json'), 'x', encoding='utf-8') as f: json.dump(dict(chemins=dict(lecons='lecons_v1_essai')), f)
        with open(os.path.join(g, 'chemins_v2.json'), 'x', encoding='utf-8') as f: json.dump(dict(chemins=dict(lecons='lecons_apprises')), f)
        self.assertEqual(L5.chemin('lecons', racine=r), os.path.join(r, 'lecons_apprises'))
        self.assertEqual(L5.chemin('inconnu', 'x', racine=r), os.path.join(r, 'inconnu', 'x'))

    def test_meme_resultat_que_v4_sur_l_espace(self):
        for cle in ('journal', 'lecons', 'delegations', 'taches', 'tests'):
            self.assertEqual(L5.chemin(cle), L4.chemin(cle), cle)

    def test_racine_mockee_par_les_tests_des_outils(self):
        r = dossier_essai('chemins_v5_mock')
        with mock.patch.object(L5, 'RACINE_CC', r):
            self.assertTrue(L5.chemin('lecons').startswith(r + os.sep))
            f = L5.evenement('essai_cc_lib', 5, 'test', dict(a=1))
        self.assertTrue(f.startswith(L5.chemin('journal', racine=r))); self.assertTrue(os.path.exists(f))

    def test_evenement_dans_le_journal_designe(self):
        f = L5.evenement('essai_cc_lib', 5, 'test', dict(a=1))
        self.assertTrue(f.startswith(L5.chemin('journal'))); self.assertTrue(os.path.exists(f))


if __name__ == '__main__':
    unittest.main()
