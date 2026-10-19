"""Tests unitaires de file_lmstudio (version courante) : lot de micro-tâches bien formé, consigne citée et non répétée, valeurs permises."""
import os, json, unittest
from aide_tests_v1 import importer, dossier_essai
F = importer('file_lmstudio')


class Depot(unittest.TestCase):
    def setUp(self):
        self.sauve = (F.ENVOI, F.LOCAL); F.ENVOI = dossier_essai('envoi'); F.LOCAL = True
        self.w = dossier_essai('travail'); self.src = os.path.join(self.w, 'mt.jsonl')
        with open(self.src, 'w') as f:
            f.write(json.dumps(dict(id='D-1', type='MT-DEMANDE', texte='Faire plus simple')) + '\n')
            f.write(json.dumps(dict(id='P-1', type='MT-PRESENCE', a='A', b='B')) + '\n')

    def tearDown(self): F.ENVOI, F.LOCAL = self.sauve

    def test_deposer_demandes(self):
        F.deposer([self.src, self.w, '--lot', 'l', '--modele', 'm', '--prio', '1', '--type', 'MT-DEMANDE'])
        L = [json.loads(x) for x in open(os.path.join(F.ENVOI, 'entree', 'l_v1.jsonl'))]
        self.assertEqual(len(L), 1); t = L[0]
        self.assertEqual((t['consigne'], t['modele'], t['prio']), ('MT-DEMANDE_v1', 'm', 1.0))
        self.assertIn('modifier', t['valeurs']); self.assertNotIn('systeme', t)

    def test_pas_d_ecrasement_local(self):
        F.deposer([self.src, self.w, '--lot', 'l', '--modele', 'm', '--type', 'MT-DEMANDE'])
        with self.assertRaises(SystemExit): F.envoyer('entree/l_v1.jsonl', 'x')

    def test_embeddings_paires(self):
        F.deposer_embeddings([self.src, self.w, '--lot', 'e'])
        ids = [json.loads(x)['id'] for x in open(os.path.join(F.ENVOI, 'entree', 'e_v1.jsonl'))]
        self.assertEqual(ids, ['D-1#t', 'P-1#a', 'P-1#b'])


if __name__ == '__main__':
    unittest.main()
