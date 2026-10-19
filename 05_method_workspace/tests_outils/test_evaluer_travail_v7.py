"""Tests de evaluer_travail_v7. (a) Non-régression : suites v6 et v5 (N3, témoins vides) rejouées sur la version 7.
(b) Ajout : les contrôles d'une révision (D2 commentaires conservés, D3 refus = source…) ne visent que le docx du même document
que la source ; un document annexe (journal des modifications) livré à côté n'est pas pris pour une révision du rapport."""
import os, json, zipfile, unittest
from aide_tests_v2 import dossier_essai, chemin_version
import test_evaluer_travail_v5 as T5
import test_evaluer_travail_v6 as T6

EVAL7 = chemin_version('evaluer_travail', 7)
W = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
     'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"')


class SurV7:
    @classmethod
    def setUpClass(cls): cls._sauve = T5.EVAL; T5.EVAL = EVAL7

    @classmethod
    def tearDownClass(cls): T5.EVAL = cls._sauve


class N3SurV7(SurV7, T5.N3):
    pass


class TemoinsSurV7(SurV7, T6.Temoins):
    pass


def docx(f, texte, commentaire=None):
    os.makedirs(os.path.dirname(f), exist_ok=True)
    with zipfile.ZipFile(f, 'w') as z:
        z.writestr('word/document.xml', f'<w:document {W}><w:body><w:p w14:paraId="00000001"><w:r><w:t>{texte}</w:t></w:r></w:p></w:body></w:document>')
        if commentaire:
            z.writestr('word/comments.xml', f'<w:comments {W}><w:comment w:id="0" w:author="Collègue" w:date="2026-10-01T00:00:00Z">'
                                            f'<w:p w14:paraId="0000000C"><w:r><w:t>{commentaire}</w:t></w:r></w:p></w:comment></w:comments>')


class DocumentAnnexe(SurV7, unittest.TestCase):
    def test_journal_non_controle_comme_revision(self):
        d = T5.CAS._conforme(dossier_essai('eval7_annexe'))
        T = dict(sujet='essai', source='00_sources/Rapport_v1.0.0.docx', auteur_revisions='Reevaluation - Claude', version_cible='2.0.0', couverture=None, auteurs_relecteurs=[])
        for f in os.listdir(d):
            if f.startswith('TRAVAIL_'): os.remove(os.path.join(d, f))
        T5.CAS._ecrire(d, 'TRAVAIL_v1.json', json.dumps(T))
        docx(os.path.join(d, '00_sources', 'Rapport_v1.0.0.docx'), 'Texte.', 'Un commentaire.')
        docx(os.path.join(d, '98_livrables', 'Journal_v2.0.0.docx'), 'Journal des modifications.')
        docx(os.path.join(d, '99_livrables_modifiables', 'Journal_v2.0.0.docx'), 'Journal des modifications.')
        K, s = T5.constats(d)
        self.assertFalse({k for k in K if k[0] in ('D2', 'D3', 'D4', 'D5', 'L3') and 'Journal' in k[1]}, s)
        docx(os.path.join(d, '98_livrables', 'Rapport_v2.0.0.docx'), 'Texte.')                     # le même document : contrôlé
        docx(os.path.join(d, '99_livrables_modifiables', 'Rapport_v2.0.0.docx'), 'Texte.')
        j2 = os.path.join(os.path.dirname(d), 'constats_2.json'); c, s = T5.lancer(EVAL7, d, '--sans-xsd', '--sans-manifeste', '--json', j2)
        K = {(k['regle'], k['chemin']) for k in json.load(open(j2, encoding='utf-8'))['constats']}
        self.assertIn(('D2', '98_livrables/Rapport_v2.0.0.docx'), K, s)


if __name__ == '__main__':
    unittest.main()
