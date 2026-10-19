"""Tests de appliquer_suivi_v2. (a) Non-régression : toute la suite v1 (remplacement tolérant, ligne de commande nominale, révision d'un autre
auteur préservée, échecs explicites « ÉCHEC <id> » en code 2, sortie existante non écrasée) est rejouée sur la version 2. (b) Correction de la
v2 : appelé sans argument (ou avec moins de quatre arguments positionnels), l'outil affiche la ligne USAGE de son en-tête et sort avec le
code 2, sans trace et sans rien écrire ; la v1 s'arrêtait sur une trace « ValueError » (code 1). Un appel complet n'affiche pas d'usage."""
import os, sys, subprocess, unittest
from aide_tests_v2 import dossier_essai, chemin_version, importer_version, OUTILS
import test_appliquer_suivi_v1 as T1

AS2 = importer_version('appliquer_suivi', 2, 'appliquer_suivi_v2_essai'); OUTIL2 = chemin_version('appliquer_suivi', 2)


class SurV2:
    """Rejoue une classe de la suite v1 avec la version 2 (module et exécutable), puis restaure."""
    @classmethod
    def setUpClass(cls):
        cls._sauve = (T1.AS, T1.OUTIL); T1.AS, T1.OUTIL = AS2, OUTIL2

    @classmethod
    def tearDownClass(cls):
        T1.AS, T1.OUTIL = cls._sauve


class RemplacementV1SurV2(SurV2, T1.RemplacementTolerant):
    pass


class LigneV1SurV2(SurV2, T1.LigneDeCommande):
    def test_sans_argument_message_usage(self): pass   # remplacé par Corrige.test_sans_argument_message_usage


def ligne_usage():
    """Ligne USAGE de l'en-tête du brouillon, telle qu'elle est écrite dans le fichier."""
    with open(OUTIL2, encoding='utf-8') as f:
        return next(l.rstrip('\n') for l in f if l.startswith('USAGE: '))


class Corrige(unittest.TestCase):
    def lancer(self, *args):
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(OUTILS, '_compat'), OUTILS]))
        return subprocess.run([sys.executable, OUTIL2, *args], capture_output=True, text=True, env=env, timeout=120)

    def test_sans_argument_message_usage(self):
        r = self.lancer()
        self.assertEqual(r.returncode, 2, r.stderr); self.assertEqual(r.stdout, ligne_usage() + '\n')
        self.assertNotIn('Traceback', r.stderr); self.assertEqual(r.stderr, '')

    def test_arguments_insuffisants(self):
        d = dossier_essai('appliquer_suivi_usage')
        for args in (['ops_x'], ['ops_x', 'entree_v1.docx'], ['ops_x', 'entree_v1.docx', 'sortie_v1.docx'], ['--auteur', 'Collègue B']):
            with self.subTest(args=args):
                r = self.lancer(*[os.path.join(d, a) if a.endswith(('.docx', '.json')) else a for a in args])
                self.assertEqual(r.returncode, 2, r.stderr); self.assertEqual(r.stdout, ligne_usage() + '\n'); self.assertNotIn('Traceback', r.stderr)
        self.assertEqual(os.listdir(d), [])                                          # rien n'est écrit

    def test_appel_complet_sans_usage(self):
        d = dossier_essai('appliquer_suivi_complet'); T1.ecrire_docx(os.path.join(d, 'entree_v1.docx'))
        with open(os.path.join(d, 'ops_vide.py'), 'w', encoding='utf-8') as g: g.write('OPS = []\n')
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(OUTILS, '_compat'), OUTILS, d]))
        r = subprocess.run([sys.executable, OUTIL2, 'ops_vide', os.path.join(d, 'entree_v1.docx'), os.path.join(d, 'sortie_v1.docx'),
                            os.path.join(d, 'journal_v1.json')], capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr); self.assertNotIn('USAGE', r.stdout.upper()); self.assertIn('0 opérations', r.stdout)
        self.assertTrue(os.path.exists(os.path.join(d, 'sortie_v1.docx')))

    def test_entete_a_jour(self):
        with open(OUTIL2, encoding='utf-8') as f: s = f.read()
        self.assertIn('VERSION: 2\n', s); self.assertIn('BANC: tests/test_appliquer_suivi_v2.py\n', s); self.assertNotIn('À DÉCRIRE', s)
        self.assertTrue(ligne_usage().startswith('USAGE: python3 appliquer_suivi_v2.py '))


if __name__ == '__main__':
    unittest.main()
