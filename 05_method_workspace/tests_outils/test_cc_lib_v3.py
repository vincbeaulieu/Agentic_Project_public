"""Tests unitaires de cc_lib_v3 : non-régression (suite v2 rejouée), qualificatif de passe « -revN » reconnu dans les noms,
version d'un livrable par la convention générale v(X+1).0.0, et règle propre à un document consignée dans TRAVAIL
(decision_version, approuvée par l'utilisateur) prioritaire ; les outils gardent leur versionnage _vN."""
import unittest
from test_cc_lib_v2 import Noms, EcritureVersionnee, Registre   # noqa: F401 (non-régression)
import cc_lib_v3 as L3


class NomsRev(unittest.TestCase):
    def test_qualificatif_rev(self):
        d = L3.analyser_nom('Rapport_Etude_v6.0.4-rev1.docx')
        self.assertEqual((d['nom'], d['ver'], d['rev'], d['forme']), ('Rapport_Etude', '6.0.4', '-rev1', 'semver'))
        d = L3.analyser_nom('Rapport_v6.0.5-rev1_journal.docx'); self.assertEqual((d['rev'], d['variante']), ('-rev1', 'journal'))

    def test_noms_anciens_inchanges(self):
        self.assertEqual(L3.analyser_nom('microtaches_v6.py')['ver'], '6'); self.assertIsNone(L3.analyser_nom('microtaches_v6.py')['rev'])
        self.assertEqual(L3.analyser_nom('Rapport_v3.7.2a.docx')['qui'], 'a')
        self.assertEqual(L3.analyser_nom('essai_20261015_1200.json')['forme'], 'horodatage')
        self.assertIsNone(L3.analyser_nom('LISEZMOI.md'))


class VersionLivrable(unittest.TestCase):
    def test_convention_generale(self):
        self.assertEqual(L3.version_livrable('00_sources/Rapport_v6.0.4.docx'), '7.0.0')
        self.assertEqual(L3.version_livrable('doc_v1.txt'), '2.0.0')
        self.assertEqual(L3.version_livrable('Rapport_v6.0.4-rev1.docx'), '7.0.0')   # la règle du rapport n'est pas une convention d'outil
        self.assertIsNone(L3.version_livrable('LISEZMOI.md'))

    def test_decision_du_document(self):
        T = dict(source='00_sources/Rapport_Etude_v6.0.4-rev1.docx')
        self.assertEqual(L3.version_attendue(T), ('7.0.0', 'convention'))
        T['decision_version'] = dict(valeur='6.0.5-rev1', approuvee_par='utilisateur')
        self.assertEqual(L3.version_attendue(T), ('6.0.5-rev1', 'decision'))
        T['decision_version'] = dict(valeur='9.0.0', approuvee_par='claude')                # jamais auto-approuvée
        self.assertEqual(L3.version_attendue(T), ('7.0.0', 'convention'))


if __name__ == '__main__':
    unittest.main()
