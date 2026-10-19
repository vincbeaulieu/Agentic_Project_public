"""Tests unitaires de cc_lib_v4 : non-régression (suite v3 rejouée) ; registre central des dossiers : valeurs par défaut,
dernière version du registre prioritaire, clé inconnue prise comme nom de dossier ; evenement() écrit dans le dossier du
journal désigné par le registre."""
import os, json, unittest
from test_cc_lib_v3 import Noms, EcritureVersionnee, Registre, NomsRev, VersionLivrable   # noqa: F401 (non-régression)
from aide_tests_v1 import dossier_essai
import cc_lib_v4 as L4


class Chemins(unittest.TestCase):
    def test_defauts_et_registre(self):
        r = dossier_essai('chemins'); g = os.path.join(r, 'outils', '_gestion'); os.makedirs(g)
        self.assertEqual(L4.chemin('lecons', 'a.json', racine=r), os.path.join(r, 'lecons', 'a.json'))
        self.assertEqual(L4.chemins(r)['propositions'], 'propositions_a_reviser')
        with open(os.path.join(g, 'chemins_v1.json'), 'w', encoding='utf-8') as f: json.dump(dict(chemins=dict(lecons='lecons_v1_essai')), f)
        with open(os.path.join(g, 'chemins_v2.json'), 'w', encoding='utf-8') as f: json.dump(dict(chemins=dict(lecons='lecons_apprises')), f)
        self.assertEqual(L4.chemin('lecons', racine=r), os.path.join(r, 'lecons_apprises'))          # dernière version
        self.assertEqual(L4.chemin('inconnu', 'x', racine=r), os.path.join(r, 'inconnu', 'x'))

    def test_evenement_dans_le_journal_designe(self):
        f = L4.evenement('essai_cc_lib', 4, 'test', dict(a=1))
        self.assertTrue(f.startswith(L4.chemin('journal'))); self.assertTrue(os.path.exists(f))


if __name__ == '__main__':
    unittest.main()
