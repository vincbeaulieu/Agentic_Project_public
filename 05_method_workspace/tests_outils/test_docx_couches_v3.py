"""Tests de docx_couches_v3. (a) Non-régression : la suite v1 (comptes, refus d'un auteur, couches, commentaires, ligne de commande) et les
corrections de la v2 (USAGE, code 2) sont rejouées sur la v3. (b) Ajouts de la v3 : refuser les modifications de mise en forme suivies d'un
auteur — w:rPrChange (anciennes propriétés du passage rétablies) et w:pPrChange (anciennes propriétés du paragraphe rétablies, marque et
section gardées) —, celles d'un autre auteur intactes ; un w:rPr ou w:pPr vide compte comme absent ; intégration : refuser la passe de
harmoniser_mise_en_forme v2 redonne le document reçu (« refus conforme »), ce que la v2 ne voyait pas (écarts à tort)."""
import os, sys, unittest
from lxml import etree
from aide_tests_v2 import dossier_essai, chemin_version, importer_version
import test_docx_couches_v1 as T1
import test_docx_couches_v2 as T2

DC3 = importer_version('docx_couches', 3, 'docx_couches_v3_essai'); OUTIL3 = chemin_version('docx_couches', 3)
q = DC3.q


class SurV3:
    @classmethod
    def setUpClass(cls):
        cls._s1 = (T1.DC, T1.OUTIL, T1.q); cls._s2 = (T2.DC2, T2.OUTIL2)
        T1.DC, T1.OUTIL, T1.q = DC3, OUTIL3, DC3.q; T2.DC2, T2.OUTIL2 = DC3, OUTIL3

    @classmethod
    def tearDownClass(cls):
        T1.DC, T1.OUTIL, T1.q = cls._s1; T2.DC2, T2.OUTIL2 = cls._s2


class RevisionsSurV3(SurV3, T1.Revisions): pass
class CouchesSurV3(SurV3, T1.Couches): pass
class CommentairesSurV3(SurV3, T1.Commentaires): pass


class LigneSurV3(SurV3, T1.LigneDeCommande):
    def test_sans_argument_message_usage(self): pass


class CorrigeV2SurV3(SurV3, T2.Corrige):
    def test_bibliotheque_inchangee(self): pass                     # remplacé : la v3 garde les signatures de la v2 (Ajouts.test_signatures)
    def test_entete_a_jour(self): pass                              # remplacé par Ajouts.test_entete


A = f'w:author="Passe - Claude" w:date="{T1.D}"'
B = f'w:author="Collègue B" w:date="{T1.D}"'


def corps(xml): return T1.corps(xml)


class Ajouts(unittest.TestCase):
    def test_refus_rprchange(self):
        root = corps(f'<w:p><w:r><w:rPr><w:sz w:val="22"/><w:szCs w:val="22"/><w:rPrChange w:id="5" {A}><w:rPr><w:b/></w:rPr></w:rPrChange></w:rPr><w:t>x</w:t></w:r></w:p>')
        self.assertEqual(DC3.refuser(root, 'Passe - Claude').get('rPrChange'), 1)
        rp = next(root.iter(q('rPr'))); self.assertEqual([DC3.ln(x) for x in rp], ['b'])

    def test_refus_pprchange_garde_marque_et_section(self):
        root = corps(f'<w:p><w:pPr><w:pStyle w:val="Heading1"/><w:keepNext/><w:rPr><w:del w:id="7" {B}/></w:rPr><w:pPrChange w:id="6" {A}><w:pPr><w:jc w:val="both"/></w:pPr></w:pPrChange></w:pPr><w:r><w:t>y</w:t></w:r></w:p>')
        self.assertEqual(DC3.refuser(root, 'Passe - Claude').get('pPrChange'), 1)
        ppr = next(root.iter(q('pPr'))); self.assertEqual([DC3.ln(x) for x in ppr], ['jc', 'rPr'])
        self.assertEqual(ppr.find(q('rPr')).find(q('del')).get(q('author')), 'Collègue B')    # suppression de marque d'un autre auteur gardée

    def test_autre_auteur_intact(self):
        root = corps(f'<w:p><w:r><w:rPr><w:sz w:val="22"/><w:rPrChange w:id="5" {B}><w:rPr/></w:rPrChange></w:rPr><w:t>x</w:t></w:r></w:p>')
        self.assertEqual(DC3.refuser(root, 'Passe - Claude'), {}); self.assertIsNotNone(next(root.iter(q('rPrChange'))))

    def test_vide_egal_absent(self):
        a = DC3.couches(corps('<w:p><w:pPr><w:rPr/></w:pPr><w:r><w:rPr/><w:t>z</w:t></w:r></w:p>'))
        b = DC3.couches(corps('<w:p><w:r><w:t>z</w:t></w:r></w:p>'))
        self.assertEqual(a, b)

    def test_signatures(self):
        import inspect
        def publiques(m): return {n: str(inspect.signature(o)) for n, o in vars(m).items() if inspect.isfunction(o) and o.__module__ == m.__name__}
        v2 = publiques(importer_version('docx_couches', 2, 'docx_couches_v2_compare')); v3 = publiques(DC3)
        self.assertEqual(v2, v3)

    def test_entete(self):
        with open(OUTIL3, encoding='utf-8') as f: s = f.read()
        self.assertIn('VERSION: 3\n', s); self.assertIn('BANC: tests/test_docx_couches_v3.py\n', s); self.assertNotIn('À DÉCRIRE', s)


class Integration(unittest.TestCase):
    """Refuser la passe de harmoniser_mise_en_forme v2 (tailles, marques supprimées, alignements, fragments) redonne le document reçu."""
    def test_refus_de_l_harmonisation(self):
        import test_controler_mise_en_forme_v2 as TC
        HM = importer_version('harmoniser_mise_en_forme', 2, 'harmoniser_v2_pour_couches')
        p, run, ins, dele = TC.p, TC.run, TC.ins, TC.dele
        corps_ = (p(run('Avant.')) + p() + p(run('1 Contexte', None), 'Heading1') + p(run('Corps ') + ins('ajout'))
                  + p(dele('5.7 Mise en œuvre') + run('24')) + p(dele('Paragraphe supprimé.'), marque_sup='Collègue A') + p(run('2 Méthode', None), 'Heading1'))
        d = dossier_essai('docx_couches_v3_integration'); src = TC.docx(d, 'doc_v1.docx', corps_); out = os.path.join(d, 'doc_v2.docx')
        self.assertEqual(HM.main([src, out]), 0)
        n, ec = DC3.comparer_refus(out, 'Harmonisation - Claude', src)
        self.assertEqual(ec, []); self.assertTrue(n.get('rPrChange') and n.get('pPrChange') and n.get('par_del') and n.get('del'))
        n2, ec2 = importer_version('docx_couches', 2, 'docx_couches_v2_temoin').comparer_refus(out, 'Harmonisation - Claude', src)
        self.assertTrue(ec2)                                          # témoin : la v2 voyait des écarts à tort


if __name__ == '__main__':
    unittest.main()
