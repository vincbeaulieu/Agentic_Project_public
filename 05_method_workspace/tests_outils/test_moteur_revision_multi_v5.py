"""Tests de moteur_revision_multi_v5. (a) Non-régression : suite v4 rejouée sur la version 5. (b) Correction : à la source d'un déplacement,
la suppression d'un autre auteur reste hors de notre moveFrom (leurs insertions y restent imbriquées) ; le contrôle du suivi du skill docx
(validate.py --original --author) passe, vers l'aval comme vers l'amont ; témoin : la v4 échoue (texte supprimé par l'autre auteur rendu
visible au refus de notre déplacement). Refus = origine et tout accepter inchangés."""
import os, sys, zipfile, unittest
import xml.etree.ElementTree as ET
from aide_tests_v2 import importer_version
import test_moteur_revision_multi_v4 as T4

M5 = importer_version('moteur_revision_multi', 5, 'moteur_revision_multi_v5_essai')
M4 = importer_version('moteur_revision_multi', 4, 'moteur_revision_multi_v4_temoin')
q, W = T4.q, T4.W


class SurV5:
    @classmethod
    def setUpClass(cls):
        cls._s5 = (T4.M4, T4.T3.M3, T4.T3.T1.M, T4.T3.T2.M2); T4.M4 = T4.T3.M3 = T4.T3.T1.M = T4.T3.T2.M2 = M5

    @classmethod
    def tearDownClass(cls): T4.M4, T4.T3.M3, T4.T3.T1.M, T4.T3.T2.M2 = cls._s5


class DocRV1SurV5(SurV5, T4.DocRV1SurV4): pass
class CorrigeV2SurV5(SurV5, T4.CorrigeV2SurV4): pass
class DeplacementV3SurV5(SurV5, T4.DeplacementV3SurV4):
    def test_revisions_imbriquees_et_marque_gardee(self): pass       # v5 : la suppression de l'autre auteur reste hors du moveFrom (voir ci-dessous)
class ReconnaissableV4SurV5(SurV5, T4.Reconnaissable):
    def test_temoin_v3_vers_amont(self): pass


def texte_apres_refus(M, amont):
    f, out = T4.deplacer(M, amont)
    sys.path.insert(0, '/mnt/skills/public/docx/scripts/office')
    from validators.redlining import RedliningValidator
    V = RedliningValidator.__new__(RedliningValidator); V.namespaces = {'w': W}
    a = ET.fromstring(zipfile.ZipFile(f).read('word/document.xml')); b = ET.fromstring(zipfile.ZipFile(out).read('word/document.xml'))
    new, ta, tb = V._compare_part(a, b)
    return ta, tb, out


class Source(unittest.TestCase):
    def test_suppression_hors_du_movefrom(self):
        for amont in (False, True):
            f, out = T4.deplacer(M5, amont); R = T4.T3.lire(out)
            for e in R.iter(q('del')):
                if e.get(q('author')) == T4.AUTRE and T4.T3.T1.ln(e.getparent()) != 'rPr':
                    dans_copie = any(T4.T3.T1.ln(a) == 'moveTo' for a in e.iterancestors())
                    if not dans_copie: self.assertFalse(any(T4.T3.T1.ln(a) == 'moveFrom' for a in e.iterancestors()))

    def test_controle_du_suivi(self):
        for amont in (False, True):
            ta, tb, out = texte_apres_refus(M5, amont); self.assertEqual(ta, tb, f'amont={amont}')

    def test_temoin_v4(self):
        ta, tb, out = texte_apres_refus(M4, False); self.assertNotEqual(ta, tb)


if __name__ == '__main__':
    unittest.main()
