"""Tests unitaires de microtaches (version courante) : règles déterministes appliquées après le modèle, lecture des valeurs."""
import unittest
from aide_tests_v1 import importer
M = importer('microtaches')


class RegleRemplacement(unittest.TestCase):
    def d(self, t): return {'type': 'MT-DEMANDE', 'texte': t}

    def test_cas_F310_pas_X_mais_Y(self):   # leçon LC-008 : « ce n'est pas X qu'il faut indiquer ici mais Y » = remplacement
        self.assertEqual(M.regle(self.d("c'est pas l'objectif du projet qu'il faut indiquer ici mais l'objectif du rapport"), 'supprimer'), ('modifier', 'R-REMPLACEMENT'))

    def test_une_phrase_suffit(self):
        self.assertEqual(M.regle(self.d('À retirer : redondant. Une phrase suffit : outils, reproductible.'), 'supprimer')[0], 'modifier')

    def test_question_simple_inchangee(self):
        self.assertEqual(M.regle(self.d('Pas français'), 'question'), ('question', None))

    def test_modifier_jamais_degrade(self):
        self.assertEqual(M.regle(self.d('remplacer par X'), 'modifier'), ('modifier', None))


class RegleManque(unittest.TestCase):
    def p(self, a, b): return {'type': 'MT-PRESENCE', 'a': a, 'b': b}

    def test_reference_perdue_rend_partiel(self):
        self.assertEqual(M.regle(self.p('Exigence A [1] et exigence B [2].', 'Exigence A [1].'), 'oui'), ('partiel', 'R-MANQUE'))

    def test_nombre_perdu_rend_partiel(self):
        self.assertEqual(M.regle(self.p('Série de 128 mesures.', 'Série de mesures.'), 'oui')[0], 'partiel')

    def test_tout_present_reste_oui(self):
        self.assertEqual(M.regle(self.p('Série de 128 mesures [3].', 'La série (128 mesures) [3].'), 'oui'), ('oui', None))


class Valeur(unittest.TestCase):
    def test_json_et_brut(self):
        self.assertEqual(M.valeur('{"r": "non"}'), 'non'); self.assertEqual(M.valeur('partiel'), 'partiel'); self.assertIsNone(M.valeur('???'))


if __name__ == '__main__':
    unittest.main()
