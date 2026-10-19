"""Tests de evaluer_travail_v10. (a) Non-régression : suite v9 rejouée sur la version 10 (dont, par elle, la suite v8). (b) Correction :
en mode acceptation, une mise en forme suivie (rPrChange) posée par un autre auteur sur le run de référence d'un commentaire disparaît
avec le fil supprimé ; v9 la comptait comme une révision perdue (D3) ; v10 l'exclut du décompte. Témoin : la même révision posée sur un
run de texte, retirée, reste signalée (D3). La constante VERSION interne vaut 10."""
import os, json, unittest
import test_evaluer_travail_v9 as T9
from aide_tests_v2 import chemin_version

EVAL10 = chemin_version('evaluer_travail', 10)
CHG = '<w:rPrChange w:id="{i}" w:author="Collegue X" w:date="2026-10-16T00:00:00Z"><w:rPr/></w:rPrChange>'


class SurV10:
    @classmethod
    def setUpClass(cls):
        cls._s10 = (T9.EVAL9, T9.T5.EVAL, T9.T7.EVAL7, T9.T8.EVAL8)
        T9.EVAL9 = T9.T5.EVAL = T9.T7.EVAL7 = T9.T8.EVAL8 = EVAL10

    @classmethod
    def tearDownClass(cls): T9.EVAL9, T9.T5.EVAL, T9.T7.EVAL7, T9.T8.EVAL8 = cls._s10


class N3SurV10(SurV10, T9.T8.N3SurV8): pass
class TemoinsSurV10(SurV10, T9.T8.TemoinsSurV8): pass
class AnnexeSurV10(SurV10, T9.T8.AnnexeSurV8): pass
class MiseEnFormeSurV10(SurV10, T9.MiseEnFormeSurV9): pass


class AcceptationSurV10(SurV10, T9.Acceptation):
    def test_version_interne(self):
        self.assertIn("OUTIL, VERSION = 'evaluer_travail', 10", open(EVAL10, encoding='utf-8').read())


class ReferenceMiseEnForme(SurV10, T9.Acceptation):
    """La référence du commentaire 1 porte une mise en forme suivie d'un autre auteur."""
    def dossier(self, cas=None):
        sauve = T9.source

        def source(dossier, nom):
            f = sauve(dossier, nom)
            def t(F):
                x = F['word/document.xml']
                x = x.replace(b'<w:r><w:commentReference w:id="1"/></w:r>', ('<w:r><w:rPr><w:rStyle w:val="CommentReference"/>' + CHG.format(i=201) + '</w:rPr><w:commentReference w:id="1"/></w:r>').encode(), 1)
                if cas == 'texte_mis_en_forme':
                    x = x.replace(b'<w:t xml:space="preserve">Second paragraphe </w:t>', b'<w:t xml:space="preserve">Second paragraphe </w:t>', 1)
                F['word/document.xml'] = x
            T9.reecrire(f, t); return f
        T9.source = source
        try: return super().dossier(None if cas == 'texte_mis_en_forme' else cas)
        finally: T9.source = sauve

    def test_reference_mise_en_forme_conforme(self):
        self.assertEqual(self.regles(self.dossier()), [])

    def test_temoin_mise_en_forme_de_texte_retiree(self):
        d = self.dossier()
        out = os.path.join(d, '98_livrables', 'Rapport_v2.0.0.docx'); mod = os.path.join(d, '99_livrables_modifiables', 'Rapport_v2.0.0.docx')
        src = os.path.join(d, '00_sources', 'Rapport_v1.0.0.docx')
        os.chmod(src, 0o644)
        T9.reecrire(src, lambda F: F.__setitem__('word/document.xml', F['word/document.xml'].replace(
            b'<w:r><w:rPr><w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr><w:t xml:space="preserve">Texte </w:t></w:r>',
            ('<w:r><w:rPr><w:sz w:val="22"/><w:szCs w:val="22"/>' + CHG.format(i=202) + '</w:rPr><w:t xml:space="preserve">Texte </w:t></w:r>').encode(), 1)))
        self.assertEqual(self.regles(d), ['D3'])          # la source porte une révision de texte que le produit n'a pas : signalé

    # les cas hérités de T9.Acceptation ne sont pas rejoués ici (déjà dans AcceptationSurV10)
    test_conforme = test_fil_non_liste = test_fil_liste_present = test_revision_restante = test_autre_auteur_accepte = test_texte_change = None
    test_version_interne = None


if __name__ == '__main__':
    unittest.main()
