"""Tests de accepter_auteurs_v1 : acceptation des révisions de certains auteurs seulement, les autres gardées telles quelles.
- insertion de l'auteur visé : contenu gardé, conteneur retiré ; insertion d'un autre auteur intacte ;
- suppression de l'auteur visé : contenu retiré, marqueurs de commentaire et signets gardés ; suppression d'un autre auteur intacte ;
- imbrications : suppression visée dans l'insertion d'un autre (contenu retiré, insertion de l'autre gardée) ; insertion visée dans
  la suppression d'un autre (contenu reste supprimé par l'autre) ;
- mise en forme suivie (rPrChange, pPrChange) validée pour l'auteur visé seulement ;
- marque de paragraphe supprimée : le paragraphe se fond dans le suivant, qui garde ses propriétés ; chaîne de deux marques ;
  marque devant un tableau : paragraphe vide retiré, paragraphe avec texte laissé et signalé ; marque d'un paragraphe de section
  laissée et signalée ; marque insérée validée ;
- rangée supprimée retirée ; tableau entièrement supprimé retiré ; ancrage de commentaire d'une rangée retirée gardé ;
- champ coupé par une suppression : laissé et signalé (témoin : retirer le casserait) ;
- propriété : accepter A puis tous les autres = accepter tous les auteurs d'un coup (vue « tout accepté » inchangée) ;
- paquet : image rendue orpheline retirée avec sa relation ; image encore employée gardée ; jamais d'écrasement (code 3) ;
  ligne de commande sans argument : code 2."""
import os, io, zipfile, unittest
from lxml import etree
from aide_tests_v2 import dossier_essai, importer_version

M = importer_version('accepter_auteurs', 1, 'accepter_auteurs_v1_essai')
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS = f'xmlns:w="{W}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"'
A, B = 'Passe - Claude', 'Collegue'


def doc(corps):
    return etree.fromstring(f'<w:document {NS}><w:body>{corps}<w:sectPr/></w:body></w:document>')


def ins(a, x, i=1): return f'<w:ins w:id="{i}" w:author="{a}" w:date="2026-10-16T00:00:00Z">{x}</w:ins>'
def dele(a, x, i=2): return f'<w:del w:id="{i}" w:author="{a}" w:date="2026-10-16T00:00:00Z">{x}</w:del>'
def r(t): return f'<w:r><w:t xml:space="preserve">{t}</w:t></w:r>'
def rd(t): return f'<w:r><w:delText xml:space="preserve">{t}</w:delText></w:r>'
def p(x, ppr=''): return f'<w:p>{"<w:pPr>" + ppr + "</w:pPr>" if ppr else ""}{x}</w:p>'
def marque(kind, a): return f'<w:rPr><w:{kind} w:id="9" w:author="{a}" w:date="2026-10-16T00:00:00Z"/></w:rPr>'


def textes(root):
    """Vue « tout accepté » simple : texte hors suppressions, paragraphe par paragraphe."""
    out = []
    for pp in root.iter(f'{{{W}}}p'):
        out.append(''.join(t.text or '' for t in pp.iter(f'{{{W}}}t') if not any(M.ln(x) == 'del' for x in t.iterancestors())))
    return out


def auteurs(root): return {a for (_, a) in M.auteurs_revisions(root)}


class Contenu(unittest.TestCase):
    def test_insertions_et_suppressions(self):
        R = doc(p(r('a') + ins(A, r('B')) + ins(B, r('C'), 3) + dele(A, '<w:commentRangeStart w:id="7"/>' + rd('D') + '<w:bookmarkStart w:id="0" w:name="s"/>') + dele(B, rd('E'), 4)))
        b = M.accepter(R, [A])
        self.assertEqual((b['ins'], b['del']), (1, 1)); self.assertEqual(auteurs(R), {B})
        self.assertEqual(textes(R), ['aBC'])
        self.assertEqual(len(list(R.iter(f'{{{W}}}commentRangeStart'))), 1); self.assertEqual(len(list(R.iter(f'{{{W}}}bookmarkStart'))), 1)
        self.assertEqual([t.text for t in R.iter(f'{{{W}}}delText')], ['E'])          # suppression de l'autre auteur intacte

    def test_imbrications(self):
        R = doc(p(ins(B, r('x') + dele(A, rd('y'), 5), 3) + dele(B, ins(A, r('z'), 6), 4)))
        M.accepter(R, [A])
        i = R.find(f'.//{{{W}}}ins'); self.assertEqual(i.get(f'{{{W}}}author'), B); self.assertEqual(''.join(i.itertext()), 'x')
        d = R.find(f'.//{{{W}}}del'); self.assertEqual(d.get(f'{{{W}}}author'), B); self.assertEqual(''.join(d.itertext()), 'z')
        self.assertEqual(auteurs(R), {B})

    def test_mise_en_forme_suivie(self):
        chg = lambda a: f'<w:rPrChange w:id="8" w:author="{a}" w:date="2026-10-16T00:00:00Z"><w:rPr/></w:rPrChange>'
        R = doc(p(f'<w:r><w:rPr><w:sz w:val="22"/>{chg(A)}</w:rPr><w:t>a</w:t></w:r><w:r><w:rPr><w:sz w:val="22"/>{chg(B)}</w:rPr><w:t>b</w:t></w:r>',
                  f'<w:jc w:val="left"/><w:pPrChange w:id="9" w:author="{A}" w:date="2026-10-16T00:00:00Z"><w:pPr/></w:pPrChange>'))
        b = M.accepter(R, [A]); self.assertEqual((b['rPrChange'], b['pPrChange']), (1, 1))
        self.assertEqual([c.getparent().getparent().find(f'{{{W}}}t').text for c in R.iter(f'{{{W}}}rPrChange')], ['b'])
        self.assertEqual(len(list(R.iter(f'{{{W}}}sz'))), 2); self.assertIsNotNone(R.find(f'.//{{{W}}}jc'))


class Marques(unittest.TestCase):
    def test_fusion_dans_le_suivant(self):
        R = doc(p(r('Un '), marque('del', A) + '<w:pStyle w:val="Corps"/>'.join(['', ''])) + p(r('deux'), '<w:pStyle w:val="Titre2"/>') + p(r('trois')))
        b = M.accepter(R, [A]); self.assertEqual(b['marque_supprimee'], 1)
        self.assertEqual(textes(R), ['Un deux', 'trois'])
        st = R.find(f'.//{{{W}}}pStyle'); self.assertEqual(st.get(f'{{{W}}}val'), 'Titre2')          # propriétés du paragraphe qui reste

    def test_chaine_et_autre_auteur(self):
        R = doc(p(r('a'), marque('del', A)) + p(r('b'), marque('del', A)) + p(r('c'), marque('del', B)) + p(r('d')))
        M.accepter(R, [A]); self.assertEqual(textes(R), ['abc', 'd'])
        self.assertEqual(auteurs(R), {B})                                                         # marque de l'autre auteur gardée

    def test_avant_un_tableau_et_section(self):
        tbl = '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>cellule</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
        L = []; R = doc(p(rd('vide') if False else dele(A, rd('x')), marque('del', A)) + tbl + p(r('garde'), marque('del', A)) + tbl + p(r('s'), marque('del', A) + '<w:sectPr/>') + p(r('fin')))
        b = M.accepter(R, [A], L)
        self.assertEqual(b.get('paragraphe_vide_retire'), 1)
        self.assertEqual(sorted(x[0] for x in L), ['marque_non_fusionnable', 'marque_section'])
        self.assertIn('garde', textes(R)); self.assertIn('s', textes(R))

    def test_marque_inseree(self):
        R = doc(p(r('a'), marque('ins', A)) + p(r('b')))
        b = M.accepter(R, [A]); self.assertEqual(b['marque_inseree'], 1); self.assertEqual(textes(R), ['a', 'b']); self.assertEqual(auteurs(R), set())


class Rangees(unittest.TestCase):
    def tr(self, t, a=None, ref=False):
        trpr = f'<w:trPr><w:del w:id="3" w:author="{a}" w:date="2026-10-16T00:00:00Z"/></w:trPr>' if a else ''
        c = '<w:commentRangeStart w:id="5"/>' + r(t) + '<w:commentRangeEnd w:id="5"/><w:r><w:commentReference w:id="5"/></w:r>' if ref else r(t)
        return f'<w:tr>{trpr}<w:tc><w:p>{c}</w:p></w:tc></w:tr>'

    def test_rangee_et_tableau(self):
        R = doc(p(r('avant')) + f'<w:tbl>{self.tr("x", A)}{self.tr("y")}</w:tbl>' + f'<w:tbl>{self.tr("z", A, ref=True)}</w:tbl>' + p(r('apres')))
        b = M.accepter(R, [A]); self.assertEqual((b['rangee_supprimee'], b['tableau_retire']), (2, 1))
        self.assertEqual(textes(R), ['avant', 'y', 'apres'])
        self.assertEqual(len(list(R.iter(f'{{{W}}}commentReference'))), 1)                         # ancrage du commentaire gardé
        self.assertEqual(len(list(R.iter(f'{{{W}}}commentRangeStart'))), 1)

    def test_rangee_autre_auteur(self):
        R = doc(f'<w:tbl>{self.tr("x", B)}</w:tbl>' + p(r('fin')))
        M.accepter(R, [A]); self.assertEqual(len(list(R.iter(f'{{{W}}}tr'))), 1)


class Champs(unittest.TestCase):
    def test_champ_coupe_laisse(self):
        f = '<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText>PAGE</w:instrText></w:r>'
        R = doc(p(dele(A, f) + '<w:r><w:fldChar w:fldCharType="end"/></w:r>'))
        L = []; M.accepter(R, [A], L)
        self.assertEqual(L, [('champ_coupe', 'del')]); self.assertEqual(len(list(R.iter(f'{{{W}}}fldChar'))), 2)   # témoin : retirer casserait le champ


class Propriete(unittest.TestCase):
    def test_accepter_par_etapes_egal_tout_accepter(self):
        corps = (p(r('a') + ins(A, r('b')) + dele(B, rd('c'), 4), marque('del', A)) + p(ins(B, r('d') + dele(A, rd('e'), 7), 6), marque('del', B))
                 + p(r('f')) + f'<w:tbl>{Rangees().tr("g", A)}{Rangees().tr("h")}</w:tbl>' + p(r('i')))
        X = doc(corps); M.accepter(X, [A]); M.accepter(X, [B])
        Y = doc(corps); M.accepter(Y, [A, B])
        self.assertEqual(textes(X), textes(Y)); self.assertEqual(auteurs(X), set())
        self.assertEqual(etree.tostring(X), etree.tostring(Y))


class Paquet(unittest.TestCase):
    def fabriquer(self, d):
        ct = '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/></Types>'
        rels = ('<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>'
                '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image2.png"/></Relationships>')
        img = lambda rid: f'<w:r><w:drawing><a:blip xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" r:embed="{rid}"/></w:drawing></w:r>'
        corps = f'<w:document {NS}><w:body>' + p(dele(A, img('rId1')) + ins(A, img('rId2'))) + '<w:sectPr/></w:body></w:document>'
        f = os.path.join(d, 'essai_v1.docx')
        with zipfile.ZipFile(f, 'w') as z:
            z.writestr('[Content_Types].xml', ct); z.writestr('word/document.xml', corps); z.writestr('word/_rels/document.xml.rels', rels)
            z.writestr('word/media/image1.png', b'ancienne'); z.writestr('word/media/image2.png', b'nouvelle')
        return f

    def test_image_orpheline_et_ecrasement(self):
        d = dossier_essai('accepter_auteurs_v1'); f = self.fabriquer(d); s = os.path.join(d, 'essai_v2.docx')
        self.assertEqual(M.main([f, s, '--auteurs', A]), 0)
        z = zipfile.ZipFile(s)
        self.assertNotIn('word/media/image1.png', z.namelist()); self.assertIn('word/media/image2.png', z.namelist())
        self.assertNotIn(b'rId1', z.read('word/_rels/document.xml.rels')); self.assertIn(b'rId2', z.read('word/_rels/document.xml.rels'))
        self.assertEqual(M.main([f, s, '--auteurs', A]), 3)                                        # jamais d'écrasement
        self.assertEqual(M.main([]), 2)


if __name__ == '__main__':
    unittest.main()
