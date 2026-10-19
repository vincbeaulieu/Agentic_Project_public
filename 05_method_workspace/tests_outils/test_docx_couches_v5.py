"""Tests de docx_couches_v5. (a) Non-régression : suite v4 rejouée sur la version 5 (et, par elle, v3, v2, v1). (b) Correction : l'empreinte
des propriétés ignore l'identifiant et les dates d'une mise en forme suivie (rPrChange, pPrChange) ; elle distingue toujours une vraie
différence de propriétés (ancienne mise en forme différente). Témoin : la v4 distingue deux rPr qui ne diffèrent que par l'identifiant."""
import unittest
from lxml import etree
from aide_tests_v2 import importer_version, chemin_version
import test_docx_couches_v4 as T4

DC5 = importer_version('docx_couches', 5, 'docx_couches_v5_essai'); OUTIL5 = chemin_version('docx_couches', 5)
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


class SurV5:
    @classmethod
    def setUpClass(cls):
        cls._s5 = (T4.DC4, T4.OUTIL4); T4.DC4, T4.OUTIL4 = DC5, OUTIL5
        T4.SurV4.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        T4.SurV4.tearDownClass.__func__(cls); T4.DC4, T4.OUTIL4 = cls._s5


class RevisionsSurV5(SurV5, T4.T1.Revisions): pass
class CouchesSurV5(SurV5, T4.T1.Couches): pass
class CommentairesSurV5(SurV5, T4.T1.Commentaires): pass
class DeplacementsV4SurV5(SurV5, T4.Deplacements):
    def test_temoin_v3(self): pass
    def test_entete(self): pass


def rpr(i, ancien='<w:lang w:val="en-GB"/>', date='2026-10-15T17:02:00Z'):
    return etree.fromstring(f'<w:rPr xmlns:w="{W}"><w:sz w:val="19"/><w:rPrChange w:id="{i}" w:author="A" w:date="{date}"><w:rPr>{ancien}</w:rPr></w:rPrChange></w:rPr>')


class Empreinte(unittest.TestCase):
    def test_identifiant_et_date_ignores(self):
        self.assertEqual(DC5._canon(rpr(1)), DC5._canon(rpr(2, date='2026-10-16T00:00:00Z')))

    def test_vraie_difference(self):
        self.assertNotEqual(DC5._canon(rpr(1)), DC5._canon(rpr(1, ancien='<w:lang w:val="fr-FR"/>')))

    def test_temoin_v4(self):
        DC4 = importer_version('docx_couches', 4, 'docx_couches_v4_temoin5')
        self.assertNotEqual(DC4._canon(rpr(1)), DC4._canon(rpr(2)))

    def test_entete(self):
        s = open(OUTIL5, encoding='utf-8').read(); self.assertIn('VERSION: 5', s); self.assertNotIn('À DÉCRIRE', s)


if __name__ == '__main__':
    unittest.main()
