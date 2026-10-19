"""Tests unitaires de donnees_entrainement : collecte immuable sans doublon, résolution or > argent, utilisateur > Claude."""
import os, sys, json, unittest
from aide_tests_v1 import importer, dossier_essai
D = importer('donnees_entrainement')


class Jeu(unittest.TestCase):
    def setUp(self):
        self.E0 = D.E; self.E = dossier_essai('entrainement'); D.E = self.E
        os.makedirs(os.path.join(self.E, 'taches'))
        json.dump(dict(tache='t', entree=['texte'], traits=['ngrammes'], classes=['x', 'y'], poids=dict(or_=1, argent=0.4, bronze=0.1) | {'or': 1.0}),
                  open(os.path.join(self.E, 'taches', 't_v1.json'), 'w'))
        self.w = dossier_essai('travail')
        with open(os.path.join(self.w, 'taches.jsonl'), 'w') as f:
            for i in ('a', 'b'): f.write(json.dumps(dict(id=i, texte='texte ' + i)) + '\n')

    def tearDown(self): D.E = self.E0

    def collecte(self, etiq, q, src):
        f = os.path.join(self.w, f'{src}.json'); json.dump(etiq, open(f, 'w'))
        D.collecter(['t', '--taches', os.path.join(self.w, 'taches.jsonl'), '--etiquettes', f, '--qualite', q, '--source', src, '--travail', 'essai'])

    def test_or_prime_et_pas_de_doublon(self):
        self.collecte({'a': 'x', 'b': 'x'}, 'argent', 'modele')
        self.collecte({'a': 'x', 'b': 'x'}, 'argent', 'modele')                 # même source : rien de nouveau
        self.collecte({'a': 'y'}, 'or', 'reference')
        S, J = D.charger_jeu('t'); J = {x['origines'][0]: x for x in J}
        self.assertEqual(J['a']['etiquette'], 'y'); self.assertEqual(J['a']['qualite'], 'or'); self.assertEqual(J['b']['qualite'], 'argent')
        self.assertEqual(len(os.listdir(os.path.join(self.E, 'donnees', 't'))), 2)

    def test_utilisateur_prime_sur_claude(self):
        self.collecte({'a': 'x'}, 'or', 'reference')
        self.collecte({'a': 'y'}, 'or', 'utilisateur')
        S, J = D.charger_jeu('t'); self.assertEqual(J[0]['etiquette'], 'y')

    def test_classe_inconnue_ignoree(self):
        self.collecte({'a': 'z'}, 'or', 'reference'); self.assertFalse(os.path.isdir(os.path.join(self.E, 'donnees', 't')))


if __name__ == '__main__':
    unittest.main()
