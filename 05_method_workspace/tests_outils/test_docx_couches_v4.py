"""Tests de docx_couches_v4. (a) Non-régression : suite v3 rejouée sur la version 4 (et, par elle, v1 et v2). (b) Ajout : refuser les
déplacements suivis d'un auteur — source rétablie (moveFrom déplié, texte rendu), copie déplacée retirée (moveTo, marque moveTo), plages
de déplacement retirées — sur un déplacement du moteur v3 qui imbrique les révisions d'un autre auteur ; refuser l'autre auteur seulement
laisse le déplacement en place. Témoin : la v3 ne redonne pas l'origine."""
import unittest
from aide_tests_v2 import importer_version, chemin_version, dossier_essai
import test_docx_couches_v1 as T1
import test_docx_couches_v2 as T2
import test_docx_couches_v3 as T3
import test_moteur_revision_multi_v3 as TM

DC4 = importer_version('docx_couches', 4, 'docx_couches_v4_essai'); OUTIL4 = chemin_version('docx_couches', 4)
DC3 = importer_version('docx_couches', 3, 'docx_couches_v3_temoin')


class SurV4:
    @classmethod
    def setUpClass(cls):
        cls._s = (T1.DC, T1.OUTIL, T1.q, T2.DC2, T2.OUTIL2, T3.DC3, T3.OUTIL3)
        T1.DC, T1.OUTIL, T1.q = DC4, OUTIL4, DC4.q; T2.DC2, T2.OUTIL2 = DC4, OUTIL4; T3.DC3, T3.OUTIL3 = DC4, OUTIL4

    @classmethod
    def tearDownClass(cls): T1.DC, T1.OUTIL, T1.q, T2.DC2, T2.OUTIL2, T3.DC3, T3.OUTIL3 = cls._s


class RevisionsSurV4(SurV4, T1.Revisions): pass
class CouchesSurV4(SurV4, T1.Couches): pass
class CommentairesSurV4(SurV4, T1.Commentaires): pass
class LigneSurV4(SurV4, T3.LigneSurV3): pass
class CorrigeV2SurV4(SurV4, T3.CorrigeV2SurV3): pass
class AjoutsV3SurV4(SurV4, T3.Ajouts):
    def test_entete(self): pass                                       # en-tête de la v3 ; celui de la v4 est contrôlé ci-dessous
    def test_signatures(self):                                        # la v4 ajoute _plages : les signatures de la v3 restent identiques
        import inspect
        sig = lambda M: {k: str(inspect.signature(v)) for k, v in vars(M).items() if inspect.isfunction(v) and v.__module__ == M.__name__}
        s3, s4 = sig(DC3), sig(DC4)
        self.assertEqual({k: s4.get(k) for k in s3}, s3)
class IntegrationV3SurV4(SurV4, T3.Integration): pass


class Deplacements(unittest.TestCase):
    def setUp(self):
        self.f, self.out = TM.Deplacement().deplacer(TM.M3)

    def test_refus_du_deplacement(self):
        R = TM.lire(self.out); n = DC4.refuser(R, TM.AUTEUR)
        self.assertEqual(DC4.couches(R), DC4.couches(TM.lire(self.f)))
        self.assertTrue(n.get('moveFrom') and n.get('par_moveTo'))
        self.assertEqual([e for t in ('moveFromRangeStart', 'moveFromRangeEnd', 'moveToRangeStart', 'moveToRangeEnd') for e in R.iter(DC4.q(t))], [])

    def test_refus_autre_auteur_garde_le_deplacement(self):
        import os, re, zipfile
        d = os.path.dirname(self.f); g = os.path.join(d, 'sans_marque_v1.docx')       # paragraphe déplacé sans marque insérée par l'autre auteur
        z = zipfile.ZipFile(self.f); F = {n: z.read(n) for n in z.namelist()}
        F['word/document.xml'] = re.sub(rb'<w:pPr><w:rPr><w:ins [^>]*/?>(</w:ins>)?</w:rPr></w:pPr>', b'', F['word/document.xml'], count=1)
        with zipfile.ZipFile(g, 'w') as zo:
            for n, b_ in F.items(): zo.writestr(n, b_)
        D = TM.M3.DocR(g, author=TM.AUTEUR, init='EC'); D.move_block('000000B2', '000000B2', '000000B3', 'apres')
        out = os.path.join(d, 'sans_marque_v2.docx'); D.save(out)
        R = TM.lire(out); DC4.refuser(R, TM.AUTRE)
        self.assertTrue(list(R.iter(DC4.q('moveFrom'))) and list(R.iter(DC4.q('moveTo'))))
        self.assertEqual([e for e in R.iter(DC4.q('ins'), DC4.q('del')) if e.get(DC4.q('author')) == TM.AUTRE], [])

    def test_temoin_v3(self):
        R = TM.lire(self.out); DC3.refuser(R, TM.AUTEUR)
        self.assertNotEqual(DC4.couches(R), DC4.couches(TM.lire(self.f)))

    def test_entete(self):
        s = open(OUTIL4, encoding='utf-8').read(); self.assertIn('VERSION: 4', s); self.assertNotIn('À DÉCRIRE', s)


if __name__ == '__main__':
    unittest.main()
