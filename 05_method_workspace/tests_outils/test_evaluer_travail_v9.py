"""Tests de evaluer_travail_v9. (a) Non-régression : suite v8 (et, par elle, v7, v6, v5) rejouée sur la version 9. (b) Mode « acceptation »
de TRAVAIL (révisions d'auteurs désignés acceptées, fils adressés supprimés, sur décision de l'utilisateur) :
- passe conforme (accepter_auteurs puis supprimer_fils) : aucun constat D2, D3, D5 ;
- témoins : fil non listé supprimé (D2) ; fil listé encore présent (D2) ; révision de l'auteur accepté restante (D3) ; révision d'un autre
  auteur acceptée aussi (D3, révisions différentes de l'attendu) ; texte changé hors révision (D3, vue « tout accepté » différente) ;
- la constante VERSION interne vaut 9."""
import os, json, shutil, zipfile, unittest
from aide_tests_v2 import dossier_essai, chemin_version, importer_version
import test_evaluer_travail_v5 as T5
import test_evaluer_travail_v7 as T7
import test_evaluer_travail_v8 as T8
import test_controler_mise_en_forme_v2 as TC

EVAL9 = chemin_version('evaluer_travail', 9)
ACC = importer_version('accepter_auteurs', 1, 'accepter_auteurs_pour_eval9')
SUP = importer_version('supprimer_fils', 1, 'supprimer_fils_pour_eval9')
A, B = 'Finition - Claude', 'Collegue X'


class SurV9:
    @classmethod
    def setUpClass(cls):
        cls._s = (T5.EVAL, T7.EVAL7, T8.EVAL8); T5.EVAL = EVAL9; T7.EVAL7 = EVAL9; T8.EVAL8 = EVAL9

    @classmethod
    def tearDownClass(cls): T5.EVAL, T7.EVAL7, T8.EVAL8 = cls._s


class N3SurV9(SurV9, T8.N3SurV8): pass
class TemoinsSurV9(SurV9, T8.TemoinsSurV8): pass
class AnnexeSurV9(SurV9, T8.AnnexeSurV8): pass
class MiseEnFormeSurV9(SurV9, T8.MiseEnForme):
    def test_version_interne(self): pass          # vaut 8 dans la suite v8 ; remplacé par Acceptation.test_version_interne (9)


W15 = 'http://schemas.microsoft.com/office/word/2012/wordml'


def commentaires():
    c = lambda i, a, t, pid: (f'<w:comment w:id="{i}" w:author="{a}" w:date="2026-10-16T00:00:00Z"><w:p w14:paraId="{pid}"><w:r><w:t>{t}</w:t></w:r></w:p></w:comment>')
    com = (f'<w:comments {TC.NS} xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml">' + c(1, B, 'demande un', '0A000001') + c(2, 'Correction - Claude', '[Correction rev1 | Traité] fait', '0A000002')
           + c(3, B, 'demande trois', '0A000003') + '</w:comments>')
    ext = (f'<w15:commentsEx xmlns:w15="{W15}"><w15:commentEx w15:paraId="0A000001" w15:done="0"/>'
           '<w15:commentEx w15:paraId="0A000002" w15:paraIdParent="0A000001" w15:done="0"/><w15:commentEx w15:paraId="0A000003" w15:done="0"/></w15:commentsEx>')
    return com, ext


def source(dossier, nom):
    ins = lambda a, t, i: f'<w:ins w:id="{i}" w:author="{a}" w:date="2026-10-16T00:00:00Z"><w:r><w:t xml:space="preserve">{t}</w:t></w:r></w:ins>'
    dele = lambda a, t, i: f'<w:del w:id="{i}" w:author="{a}" w:date="2026-10-16T00:00:00Z"><w:r><w:delText xml:space="preserve">{t}</w:delText></w:r></w:del>'
    ref = lambda i: f'<w:r><w:commentReference w:id="{i}"/></w:r>'
    corps = (f'<w:p><w:commentRangeStart w:id="1"/><w:commentRangeStart w:id="2"/>{TC.run("Texte ")}{ins(A, "ajout ", 101)}{dele(B, "retrait ", 102)}'
             f'<w:commentRangeEnd w:id="1"/><w:commentRangeEnd w:id="2"/>{ref(1)}{ref(2)}</w:p>'
             f'<w:p><w:commentRangeStart w:id="3"/>{TC.run("Second paragraphe ")}{ins(B, "suggestion", 103)}<w:commentRangeEnd w:id="3"/>{ref(3)}</w:p>')
    f = TC.docx(dossier, nom, corps)
    z = zipfile.ZipFile(f); F = {n: z.read(n) for n in z.namelist()}; z.close(); os.remove(f)
    F['word/comments.xml'], F['word/commentsExtended.xml'] = (x.encode() for x in commentaires())
    with zipfile.ZipFile(f, 'w') as zo:
        for n, b in F.items(): zo.writestr(n, b)
    return f


def reecrire(f, transformer):
    z = zipfile.ZipFile(f); F = {n: z.read(n) for n in z.namelist()}; z.close(); os.remove(f); transformer(F)
    with zipfile.ZipFile(f, 'w') as zo:
        for n, b in F.items(): zo.writestr(n, b)


class Acceptation(SurV9, unittest.TestCase):
    def dossier(self, cas=None):
        d = T5.CAS._conforme(dossier_essai(f'eval9_acceptation_{cas or "conforme"}'))
        for f in os.listdir(d):
            if f.startswith('TRAVAIL_'): os.remove(os.path.join(d, f))
        T5.CAS._ecrire(d, 'TRAVAIL_v1.json', json.dumps(dict(sujet='essai', source='00_sources/Rapport_v1.0.0.docx', auteur_revisions=A, version_cible='2.0.0',
                                                             couverture=None, auteurs_relecteurs=[],
                                                             acceptation=dict(auteurs=[A], fils_supprimes='01_analyse/fils_supprimes_v1.json'))))
        T5.CAS._ecrire(d, '01_analyse/fils_supprimes_v1.json', json.dumps(['1']))
        src = source(os.path.join(d, '00_sources'), 'Rapport_v1.0.0.docx')
        mid = os.path.join(d, '01_analyse', 'accepte_v1.docx'); out = os.path.join(d, '98_livrables', 'Rapport_v2.0.0.docx')
        auteurs = [A, B] if cas == 'autre_auteur' else [A]
        if cas == 'sans_acceptation': shutil.copy2(src, mid)
        else: ACC.traiter(src, mid, auteurs)
        racines = ['1', '3'] if cas == 'fil_non_liste' else [] if cas == 'fil_present' else ['1']
        if racines: SUP.traiter(mid, out, racines)
        else: shutil.copy2(mid, out)
        if cas == 'texte_change': reecrire(out, lambda F: F.__setitem__('word/document.xml', F['word/document.xml'].replace(b'Second', b'Deuxieme', 1)))
        shutil.copy2(out, os.path.join(d, '99_livrables_modifiables', 'Rapport_v2.0.0.docx'))
        return d

    def regles(self, d):
        j = os.path.join(os.path.dirname(d), f'constats_{os.path.basename(d)}.json')
        T5.lancer(EVAL9, d, '--sans-xsd', '--sans-manifeste', '--json', j)
        with open(j, encoding='utf-8') as g: return sorted({k['regle'] for k in json.load(g)['constats'] if k['regle'] in ('D2', 'D3', 'D5', 'L3')})

    def test_conforme(self): self.assertEqual(self.regles(self.dossier()), [])
    def test_fil_non_liste(self): self.assertEqual(self.regles(self.dossier('fil_non_liste')), ['D2'])
    def test_fil_liste_present(self): self.assertEqual(self.regles(self.dossier('fil_present')), ['D2'])
    def test_revision_restante(self): self.assertIn('D3', self.regles(self.dossier('sans_acceptation')))
    def test_autre_auteur_accepte(self): self.assertEqual(self.regles(self.dossier('autre_auteur')), ['D3'])
    def test_texte_change(self): self.assertEqual(self.regles(self.dossier('texte_change')), ['D3'])

    def test_version_interne(self):
        self.assertIn("OUTIL, VERSION = 'evaluer_travail', 9", open(EVAL9, encoding='utf-8').read())


if __name__ == '__main__':
    unittest.main()
