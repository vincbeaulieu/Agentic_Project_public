"""Tests de supprimer_fils_v1 : suppression de fils de commentaires entiers, dans toutes les parties.
- un fil (racine + 2 réponses) supprimé : commentaires, commentEx, commentId, commentExtensible, marqueurs et références retirés ;
  témoin : les réponses partent avec la racine (sans le calcul des fils, elles resteraient) ;
- run de référence retiré s'il ne porte plus rien, gardé s'il porte du texte ; conteneur de révision vidé retiré ;
- autres fils intacts (texte, auteur, date, parent) ; texte du document inchangé ;
- contrôle intégré : conforme ; il détecte un ancrage cassé (témoin) ;
- racine inconnue ou réponse donnée comme racine : refus (code 4) ; jamais d'écrasement (code 3) ; usage (code 2)."""
import os, json, zipfile, unittest
from lxml import etree
from aide_tests_v2 import dossier_essai, importer_version

M = importer_version('supprimer_fils', 1, 'supprimer_fils_v1_essai')
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NSD = f'xmlns:w="{W}" xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"'


def comment(i, auteur, texte, pid):
    return f'<w:comment w:id="{i}" w:author="{auteur}" w:date="2026-10-1{i}T00:00:00Z"><w:p w14:paraId="{pid}"><w:r><w:t>{texte}</w:t></w:r></w:p></w:comment>'


def paquet(d, nom='essai_v1.docx'):
    com = f'<w:comments {NSD}>' + comment(1, 'Collegue', 'racine A', 'A1') + comment(2, 'Claude', 'reponse A', 'A2') + comment(3, 'Utilisateur', 'reponse A bis', 'A3') + comment(4, 'Collegue', 'racine B', 'B1') + '</w:comments>'
    ext = ('<w15:commentsEx xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml">'
           '<w15:commentEx w15:paraId="A1" w15:done="0"/><w15:commentEx w15:paraId="A2" w15:paraIdParent="A1" w15:done="0"/>'
           '<w15:commentEx w15:paraId="A3" w15:paraIdParent="A1" w15:done="0"/><w15:commentEx w15:paraId="B1" w15:done="0"/></w15:commentsEx>')
    cid = ('<w16cid:commentsIds xmlns:w16cid="http://schemas.microsoft.com/office/word/2016/wordml/cid">'
           + ''.join(f'<w16cid:commentId w16cid:paraId="{p}" w16cid:durableId="0000000{k}"/>' for k, p in enumerate(('A1', 'A2', 'A3', 'B1'))) + '</w16cid:commentsIds>')
    cex = ('<w16cex:commentsExtensible xmlns:w16cex="http://schemas.microsoft.com/office/word/2018/wordml/cex">'
           + ''.join(f'<w16cex:commentExtensible w16cex:durableId="0000000{k}" w16cex:dateUtc="2026-10-16T00:00:00Z"/>' for k in range(4)) + '</w16cex:commentsExtensible>')
    ref = lambda i: f'<w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr><w:commentReference w:id="{i}"/></w:r>'
    corps = (f'<w:document {NSD}><w:body><w:p>'
             + ''.join(f'<w:commentRangeStart w:id="{i}"/>' for i in (1, 2, 3)) + '<w:r><w:t>texte ancré A</w:t></w:r>'
             + ''.join(f'<w:commentRangeEnd w:id="{i}"/>' for i in (1, 2, 3)) + ref(1)
             + f'<w:ins w:id="90" w:author="X" w:date="2026-10-16T00:00:00Z">{ref(2)}</w:ins>'
             + '<w:r><w:t>garde</w:t><w:commentReference w:id="3"/></w:r>'
             + '</w:p><w:p><w:commentRangeStart w:id="4"/><w:r><w:t>texte B</w:t></w:r><w:commentRangeEnd w:id="4"/>' + ref(4) + '</w:p><w:sectPr/></w:body></w:document>')
    f = os.path.join(d, nom)
    with zipfile.ZipFile(f, 'w') as z:
        for k, v in (('word/document.xml', corps), ('word/comments.xml', com), ('word/commentsExtended.xml', ext),
                     ('word/commentsIds.xml', cid), ('word/commentsExtensible.xml', cex), ('word/people.xml', '<w15:people xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml"/>')):
            z.writestr(k, v)
    return f


def lire(f):
    z = zipfile.ZipFile(f); return {n: z.read(n) for n in z.namelist()}


class Suppression(unittest.TestCase):
    def setUp(self):
        self.d = dossier_essai('supprimer_fils_v1'); self.f = paquet(self.d)
        self.L = os.path.join(self.d, 'fils_v1.json'); json.dump(['1'], open(self.L, 'w'))

    def test_fil_entier(self):
        s = os.path.join(self.d, 'essai_v2.docx'); self.assertEqual(M.main([self.f, s, '--fils', self.L]), 0)
        F = lire(s); C = M.fils(F)
        self.assertEqual(sorted(C), ['4'])                                                         # témoin : réponses 2 et 3 parties aussi
        for part, motif in (('word/commentsExtended.xml', b'A'), ('word/commentsIds.xml', b'"A'), ('word/commentsExtensible.xml', b'00000000')):
            self.assertNotIn(motif, F[part], part)
        self.assertIn(b'B1', F['word/commentsExtended.xml']); self.assertIn(b'00000003', F['word/commentsExtensible.xml'])
        doc = etree.fromstring(F['word/document.xml'])
        self.assertEqual(sorted(e.get(f'{{{W}}}id') for e in doc.iter(f'{{{W}}}commentRangeStart')), ['4'])
        self.assertEqual(sorted(e.get(f'{{{W}}}id') for e in doc.iter(f'{{{W}}}commentReference')), ['4'])
        self.assertEqual(len(list(doc.iter(f'{{{W}}}ins'))), 0)                                    # conteneur de révision vidé retiré
        self.assertEqual([t.text for t in doc.iter(f'{{{W}}}t')], ['texte ancré A', 'garde', 'texte B'])   # texte inchangé
        self.assertEqual(F['word/people.xml'], lire(self.f)['word/people.xml'])

    def test_controle_detecte_un_ancrage_casse(self):
        F = lire(self.f); avant = dict(F); bilan, ids = M.supprimer(F, ['1'])
        self.assertEqual(M.controler(avant, F, ids), [])
        F['word/document.xml'] = F['word/document.xml'].replace(b'<w:commentRangeEnd w:id="4"/>', b'')
        self.assertTrue(any('ancrage du commentaire 4' in e for e in M.controler(avant, F, ids)))

    def test_refus(self):
        s = os.path.join(self.d, 'essai_v3.docx')
        json.dump(['2'], open(self.L, 'w')); self.assertEqual(M.main([self.f, s, '--fils', self.L]), 4)   # réponse, pas une racine
        json.dump({'racines': ['99']}, open(self.L, 'w')); self.assertEqual(M.main([self.f, s, '--fils', self.L]), 4)
        self.assertFalse(os.path.exists(s))
        json.dump(['4'], open(self.L, 'w')); self.assertEqual(M.main([self.f, s, '--fils', self.L]), 0)
        self.assertEqual(M.main([self.f, s, '--fils', self.L]), 3); self.assertEqual(M.main([]), 2)


if __name__ == '__main__':
    unittest.main()
