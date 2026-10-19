"""Tests de tester_outils_v4 : message d'échec lisible (ligne de l'exception et différence qui suit, au lieu de la seule dernière
ligne « ?   ^ » de la v3) ; tests ignorés comptés et nommés ; fumée d'une candidate nouvelle chargée depuis candidat/ (la v3 répondait
« introuvable ») ; option --test d'une seule classe, lancée par le programme candidat lui-même, avec un test ignoré à dessein ; environnement (PYTHONPATH) restauré avant chaque test."""
import os, sys, json, glob, subprocess, unittest
from aide_tests_v2 import chemin_version, importer_version, chemin

T4 = importer_version('tester_outils', 4)
PROG = chemin_version('tester_outils', 4)
TRACE = '''Traceback (most recent call last):
  File "test_x.py", line 12, in test_y
    self.assertEqual(a, b)
AssertionError: Lists differ: ['1 délégations', '   décompte : 3'] != ['1 délégations']

First list contains 1 additional elements.
First extra element 1:
'   décompte : 3'

- ['1 délégations', '   décompte : 3']
?                  ^
'''


class MessageEchec(unittest.TestCase):
    def test_bloc_de_l_exception(self):
        m = T4.message_echec(TRACE)
        self.assertTrue(m.startswith('AssertionError: Lists differ'), m); self.assertIn("'   décompte : 3'", m)
        self.assertNotEqual(m.strip(), '?                  ^')                          # le défaut de la v3 : la seule dernière ligne

    def test_sans_exception_reconnue(self):
        self.assertEqual(T4.message_echec('ligne 1\nligne 2'), 'ligne 1\nligne 2')


class Ignores(unittest.TestCase):
    def test_noms_et_raisons(self):
        self.assertEqual(T4.ignores_lisibles([('test_a (m.C.test_a)', 'livrables réels absents')]),
                         [dict(test='test_a (m.C.test_a)', raison='livrables réels absents')])


class FauxMoteur:
    def __init__(self): self.charges = []
    def versions(self, outil): return {2: ('/x/outils/%s/%s_v2.py' % (outil, outil), False)}
    def courante(self, outil, ext='py'): return 2, '/x/outils/%s/%s_v2.py' % (outil, outil)
    def importer(self, nom, version=None): self.charges.append(('adoptee', nom, version)); return 'adoptee'
    def _charger_module(self, nom, chemin): self.charges.append(('candidate', nom, chemin)); return 'candidate'


class Candidats(unittest.TestCase):
    def test_fumee_charge_la_candidate(self):
        R = FauxMoteur(); T4.candidats(R, 'outil_essai=3')
        self.assertEqual(R.courante('outil_essai')[0], 3)
        self.assertEqual(R.importer('outil_essai', 3), 'candidate')
        self.assertTrue(R.charges[-1][2].endswith(os.path.join('outil_essai', 'candidat', 'outil_essai_v3.py')), R.charges)
        self.assertEqual(R.importer('autre_outil', 2), 'adoptee')                       # les autres outils : inchangés


class EnvironnementIsole(unittest.TestCase):
    def test_pythonpath_restaure_avant_chaque_test(self):
        avant = os.environ.get('PYTHONPATH')
        try:
            os.environ['PYTHONPATH'] = '/espace_essai_pollue/outils'                     # pollution, comme celle d'un moteur d'essai
            r = T4.Resultat(__import__('io').StringIO(), True, 0); r.startTest(self)
            self.assertEqual(os.environ.get('PYTHONPATH'), T4.ENV_INITIAL['PYTHONPATH'])
            self.assertNotEqual(os.environ.get('PYTHONPATH'), '/espace_essai_pollue/outils')
        finally:
            if avant is None: os.environ.pop('PYTHONPATH', None)
            else: os.environ['PYTHONPATH'] = avant


class Demonstration(unittest.TestCase):
    @unittest.skipIf(os.environ.get('CC_DEMO_IGNORE') == '1', 'démonstration : test ignoré à dessein')
    def test_ignore_si_demande(self):
        self.assertTrue(True)


class LigneDeCommande(unittest.TestCase):
    def test_option_test_et_ignores_comptes(self):
        avant = set(glob.glob(chemin('tests', 'rapports', 'rapport_tests_*.json')))
        r = subprocess.run([sys.executable, PROG, '--test', 'test_tester_outils_v4.Demonstration'], capture_output=True, text=True,
                           env=dict(os.environ, CC_DEMO_IGNORE='1'), timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('1 tests, 0 échec(s), 1 ignoré(s)', r.stdout); self.assertIn('non lancée : --test seul', r.stdout)
        nouveaux = sorted(set(glob.glob(chemin('tests', 'rapports', 'rapport_tests_*.json'))) - avant)
        with open(nouveaux[-1], encoding='utf-8') as g: R = json.load(g)
        self.assertEqual((R['unitaires']['ignores'], R['test']), (1, 'test_tester_outils_v4.Demonstration'))
        self.assertIn('démonstration', R['unitaires']['ignores_details'][0]['raison'])


if __name__ == '__main__':
    unittest.main()
