"""Tests de docx_couches_v2 (bibliothèque importée par d'autres outils). (a) Non-régression : toute la suite v1 (comptes de révisions par auteur,
refus d'un auteur, couches, comparaison, commentaires, codes de sortie 0 / 1) est rejouée sur la version 2. (b) Correction de la v2 : lancé en
ligne de commande sans argument (ou avec moins de trois), l'outil affiche la ligne USAGE de son en-tête et sort avec le code 2, sans trace ;
la v1 s'arrêtait sur une trace « ValueError » (code 1). Les fonctions de la bibliothèque sont inchangées (mêmes noms, mêmes signatures)."""
import os, sys, inspect, subprocess, unittest
from aide_tests_v2 import dossier_essai, chemin_version, importer_version, OUTILS
import test_docx_couches_v1 as T1

DC2 = importer_version('docx_couches', 2, 'docx_couches_v2_essai'); OUTIL2 = chemin_version('docx_couches', 2)


class SurV2:
    """Rejoue une classe de la suite v1 avec la version 2 (module et exécutable), puis restaure."""
    @classmethod
    def setUpClass(cls):
        cls._sauve = (T1.DC, T1.OUTIL, T1.q); T1.DC, T1.OUTIL, T1.q = DC2, OUTIL2, DC2.q

    @classmethod
    def tearDownClass(cls):
        T1.DC, T1.OUTIL, T1.q = cls._sauve


class RevisionsV1SurV2(SurV2, T1.Revisions):
    pass


class CouchesV1SurV2(SurV2, T1.Couches):
    pass


class CommentairesV1SurV2(SurV2, T1.Commentaires):
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
        d = dossier_essai('docx_couches_usage'); f = T1.ecrire_docx(os.path.join(d, 'doc_v1.docx'), T1.P1 + T1.P2 + T1.P3)
        for args in ([f], [f, 'Collègue A']):
            with self.subTest(args=args):
                r = self.lancer(*args)
                self.assertEqual(r.returncode, 2, r.stderr); self.assertEqual(r.stdout, ligne_usage() + '\n'); self.assertNotIn('Traceback', r.stderr)

    def test_appel_complet_sans_usage(self):
        d = dossier_essai('docx_couches_complet'); f = T1.ecrire_docx(os.path.join(d, 'doc_v1.docx'), T1.P1 + T1.P2 + T1.P3)
        ref = T1.ecrire_docx(os.path.join(d, 'reference_v1.docx'), T1.P1_REF + T1.P2)
        r = self.lancer(f, 'Collègue A', ref)
        self.assertEqual(r.returncode, 0, r.stderr); self.assertIn('refus conforme', r.stdout); self.assertNotIn('USAGE', r.stdout.upper())

    def test_bibliotheque_inchangee(self):
        def publiques(m): return {n: str(inspect.signature(o)) for n, o in vars(m).items() if inspect.isfunction(o) and o.__module__ == m.__name__}
        v1, v2 = publiques(T1.importer_version('docx_couches', 1, 'docx_couches_v1_compare')), publiques(DC2)
        self.assertTrue(v1); self.assertEqual(v1, v2)                               # mêmes fonctions, mêmes signatures
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(OUTILS, '_compat'), OUTILS, os.path.dirname(OUTIL2)]))
        r = subprocess.run([sys.executable, '-c', 'import docx_couches_v2'], capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual((r.returncode, r.stdout), (0, ''), r.stderr)                # importée comme bibliothèque : ni usage, ni sortie

    def test_entete_a_jour(self):
        with open(OUTIL2, encoding='utf-8') as f: s = f.read()
        self.assertIn('VERSION: 2\n', s); self.assertIn('BANC: tests/test_docx_couches_v2.py\n', s); self.assertNotIn('À DÉCRIRE', s)
        self.assertTrue(ligne_usage().startswith('USAGE: python3 docx_couches_v2.py '))


if __name__ == '__main__':
    unittest.main()
