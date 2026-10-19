"""Tests de controler_mise_en_forme_v3 : toute la suite v2, plus la commande « reference » (classes Reference et ReferenceReelle). Suite v2 (petits docx synthétiques complets, écrits avec zipfile). Vérifié :
- page de garde (avant la table des matières) et sommaire jamais relevés ;
- MF1 passage inséré sans taille (12 pt par défaut dans un corps à 11 pt), attribué à son auteur ; MF2 taille explicite ;
- MF3 « * Conservés* » relevé, appel de note « * A : » et « B* » non relevés ;
- vue acceptée : une marque supprimée fond le paragraphe dans le suivant ; fusion arrêtée par un tableau ; rangées et tableaux supprimés en
  suivi écartés ; textes_acceptes ;
- MF4 ligne vide laissée par une suppression ; MF5 paragraphe vide inutile (pas avant un tableau, ni avec signet, ni en cellule) ;
- MF7 fragment résiduel (« 12 » d'un ancien sommaire) ; une insertion qui remplace un passage supprimé et un titre intact qui absorbe des
  lignes supprimées n'en sont pas ;
- MF8 fusion entre propriétés différentes (corps supprimé absorbé par un titre) ; aucune si les propriétés sont égales ;
- MF9 tableau vidé (rangées gardées) ; MF10 légende supprimée d'un tableau gardé ;
- auteurs anonymisés (nom inconnu -> « Collègue » ; libellés neutres et auteurs Claude gardés) ;
- comparer (code 1 si l'auteur visé introduit un écart) ; ligne de commande (sans argument : 2 ; releve : JSON écrit)."""
import os, sys, json, zipfile, subprocess, unittest
from aide_tests_v2 import dossier_essai, chemin_version, importer_version

OUTIL = chemin_version('controler_mise_en_forme', 3)
C = importer_version('controler_mise_en_forme', 3)
NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
D = '2026-01-01T00:00:00Z'
STYLES = (f'<w:styles {NS}><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:sz w:val="24"/></w:rPr></w:rPrDefault></w:docDefaults>'
          '<w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
          '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>'
          '<w:style w:type="paragraph" w:styleId="TOC1"><w:name w:val="toc 1"/><w:basedOn w:val="Normal"/></w:style>'
          '<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/></w:style></w:styles>')
TYPES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
         '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
         '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
         '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>')
RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
DOCRELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
           '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')


def a(nom): return f'w:author="{nom}" w:date="{D}"'


_id = [100]


def nid():
    _id[0] += 1; return _id[0]


def run(t, sz='22'): return f'<w:r><w:rPr>{f"<w:sz w:val=\"{sz}\"/><w:szCs w:val=\"{sz}\"/>" if sz else ""}</w:rPr><w:t xml:space="preserve">{t}</w:t></w:r>'
def ins(t, qui='Correction - Claude', sz=None): return f'<w:ins w:id="{nid()}" {a(qui)}>{run(t, sz)}</w:ins>'
def dele(t, qui='Correction - Claude'): return f'<w:del w:id="{nid()}" {a(qui)}><w:r><w:rPr><w:sz w:val="22"/></w:rPr><w:delText xml:space="preserve">{t}</w:delText></w:r></w:del>'


def p(contenu='', style=None, marque_sup=None, ppr_extra=''):
    rpr = f'<w:rPr><w:del w:id="{nid()}" {a(marque_sup)}/></w:rPr>' if marque_sup else ''
    st = f'<w:pStyle w:val="{style}"/>' if style else ''
    return f'<w:p><w:pPr>{st}{ppr_extra}{rpr}</w:pPr>{contenu}</w:p>'


def tbl(rangees, supprimees=False, qui='Correction - Claude'):
    tr = ''.join(f'<w:tr>{f"<w:trPr><w:del w:id=\"{nid()}\" {a(qui)}/></w:trPr>" if supprimees else ""}<w:tc><w:tcPr><w:tcW w:w="2000" w:type="dxa"/></w:tcPr>{c}</w:tc></w:tr>' for c in rangees)
    return f'<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/></w:tblPr><w:tblGrid><w:gridCol w:w="2000"/></w:tblGrid>{tr}</w:tbl>'


GARDE = p(run('Rapport de démonstration', '40')) + p() + p(run('Table des matières'), 'TOC1') + p(run('1 Contexte\t3'), 'TOC1')
CORPS = p(run('Un paragraphe de corps à onze points, assez long pour fixer la taille dominante du document.'))
SECT = '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" w:header="567" w:footer="567" w:gutter="0"/></w:sectPr>'


def docx(dossier, nom, corps):
    f = os.path.join(dossier, nom)
    with zipfile.ZipFile(f, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', TYPES); z.writestr('_rels/.rels', RELS); z.writestr('word/_rels/document.xml.rels', DOCRELS)
        z.writestr('word/document.xml', f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {NS}><w:body>{GARDE}{CORPS}{corps}{SECT}</w:body></w:document>')
        z.writestr('word/styles.xml', STYLES)
    return f


def codes(R, code=None): return [e for e in R['ecarts'] if code is None or e['code'] == code]


class Base(unittest.TestCase):
    def releve(self, corps, nom='doc_v1.docx'):
        self.d = dossier_essai('controler_mise_en_forme_v3'); self.f = docx(self.d, nom, corps); return C.releve(self.f)


class Passages(Base):
    def test_garde_et_sommaire_ignores(self):
        R = self.releve(''); self.assertEqual(R['profil']['debut_sommaire'], 2); self.assertEqual(codes(R), [])

    def test_mf1_insertion_sans_taille(self):
        R = self.releve(p(run('Texte de base à onze points ') + ins('ajout sans taille')))
        e = codes(R, 'MF1'); self.assertEqual(len(e), 1); self.assertEqual(e[0]['auteur'], 'Correction - Claude'); self.assertIn('12 pt au lieu de 11 pt', e[0]['detail'])

    def test_mf2_taille_explicite(self):
        R = self.releve(p(run('Texte de base assez long à onze points ') + run('petit', '18')))
        self.assertEqual([e['code'] for e in codes(R)], ['MF2'])

    def test_mf3_markdown_et_appels_de_note(self):
        R = self.releve(p(run('* Conservés* : X1 et X2.')) + p(run('* A : note A.')) + p(run('Cellule B* incluse.')))
        e = codes(R, 'MF3'); self.assertEqual(len(e), 1); self.assertIn('Conservés', e[0]['texte'])


class VueAcceptee(Base):
    def test_groupes_et_textes(self):
        corps = (p(dele('Ancien paragraphe.'), marque_sup='Correction - Claude') + p(run('Suite gardée.'))
                 + p(run('Avant tableau.'), marque_sup='Correction - Claude') + tbl([p(run('cellule'))]) + p(run('Après.'))
                 + tbl([p(run('rangée supprimée'))], supprimees=True) + p(run('Fin.')))
        self.releve(corps); T = C.textes_acceptes(self.f)
        self.assertIn('Suite gardée.', T); self.assertNotIn('Ancien paragraphe.', T)
        self.assertIn('Avant tableau.', T)                                    # fusion arrêtée par le tableau
        self.assertNotIn('rangée supprimée', T); self.assertIn('cellule', T)

    def test_mf4_ligne_vide(self):
        R = self.releve(p(dele('Phrase entièrement supprimée.')) + p(run('Suite.')))
        e = codes(R, 'MF4'); self.assertEqual(len(e), 1); self.assertEqual(e[0]['auteur'], 'Correction - Claude')

    def test_mf5_vide_utile_ou_non(self):
        R = self.releve(p(run('Avant.')) + p() + p(run('Après.')) + p() + tbl([p(run('x'))]) + p('<w:bookmarkStart w:id="1" w:name="_Ref1"/><w:bookmarkEnd w:id="1"/>')
                        + tbl([p(run('y')) + p()]))
        self.assertEqual(len(codes(R, 'MF5')), 1)

    def test_mf7_fragment_residuel(self):
        R = self.releve(p(dele('5.7 Mise en œuvre') + run('12')) + p(run('Suite.')))
        e = codes(R, 'MF7'); self.assertEqual(len(e), 1); self.assertIn('« 12 »', e[0]['detail'])

    def test_mf7_pas_un_remplacement_ni_un_titre_intact(self):
        R = self.releve(p(dele('Niveau bas (cellule B)') + ins('B*', sz='22'))
                        + p(dele('Ligne entièrement supprimée qui précède un titre.'), marque_sup='Correction - Claude') + p(run('PARTIE I', None), 'Heading1'))
        self.assertEqual(codes(R, 'MF7'), [])

    def test_mf8_titre_absorbant_du_corps(self):
        R = self.releve(p(dele('Paragraphe supprimé.'), marque_sup='Correction - Claude') + p(run('1 Contexte', None), 'Heading1'))
        e = codes(R, 'MF8'); self.assertEqual(len(e), 1); self.assertIn('Heading1', e[0]['detail']); self.assertEqual(len(e[0]['membres']), 2)

    def test_mf8_absent_si_proprietes_egales(self):
        R = self.releve(p(dele('Paragraphe supprimé.'), marque_sup='Correction - Claude') + p(run('Corps.')))
        self.assertEqual(codes(R, 'MF8'), [])


class Tableaux(Base):
    def test_mf9_tableau_vide(self):
        R = self.releve(tbl([p(run('Cause')), p(dele('Une longue explication supprimée en suivi dans la cellule.'))]) + p(run('Suite.')))
        self.assertEqual(len(codes(R, 'MF9')), 1)

    def test_mf9_absent_si_rangees_supprimees(self):
        R = self.releve(tbl([p(dele('Contenu supprimé.'))], supprimees=True) + p(run('Suite.')))
        self.assertEqual(codes(R, 'MF9'), [])

    def test_mf10_legende_supprimee(self):
        R = self.releve(p(dele('Tableau 3. Repères de lecture.')) + tbl([p(run('Plage')), p(run('Interprétation'))]) + p(run('Suite.')))
        self.assertEqual(len(codes(R, 'MF10')), 1)


class Anonymisation(unittest.TestCase):
    def test_auteurs(self):
        self.assertEqual(C.anonyme_auteur('Correction - Claude'), 'Correction - Claude')
        self.assertEqual(C.anonyme_auteur('Utilisateur invité'), 'Utilisateur invité')
        self.assertEqual(C.anonyme_auteur('Collègue A'), 'Collègue A')
        self.assertEqual(C.anonyme_auteur('Jean Exemplaire'), 'Collègue')

    def test_releve_sans_nom(self):
        d = dossier_essai('controler_mise_en_forme_v3_anonyme')
        f = docx(d, 'doc_v1.docx', p(dele('Phrase supprimée par une personne.', qui='Jean Exemplaire')) + p(run('Suite.')))
        self.assertNotIn('Exemplaire', json.dumps(C.releve(f), ensure_ascii=False))


class Comparer(unittest.TestCase):
    def test_auteur_vise(self):
        d = dossier_essai('controler_mise_en_forme_v3_comparer')
        f1 = docx(d, 'avant_v1.docx', p(run('Texte de base.'))); f2 = docx(d, 'apres_v1.docx', p(run('Texte de base.') + ins('ajout', qui='Passe - Claude')))
        R = C.comparer(f1, f2, 'Passe - Claude'); self.assertEqual([e['code'] for e in R['vises']], ['MF1'])
        self.assertEqual(C.comparer(f1, f2, 'Autre - Claude')['vises'], [])


class LigneDeCommande(unittest.TestCase):
    def test_sans_argument(self):
        r = subprocess.run([sys.executable, OUTIL], capture_output=True, text=True); self.assertEqual(r.returncode, 2); self.assertIn('releve', r.stdout)

    def test_releve_json(self):
        d = dossier_essai('controler_mise_en_forme_v3_cli'); f = docx(d, 'doc_v1.docx', p(dele('Supprimé.')) + p(run('Suite.'))); j = os.path.join(d, 'releve_v1.json')
        r = subprocess.run([sys.executable, OUTIL, 'releve', f, '--json', j], capture_output=True, text=True)
        with open(j, encoding='utf-8') as g: R = json.load(g)
        self.assertEqual(r.returncode, 0, r.stderr); self.assertEqual([e['code'] for e in R['ecarts']], ['MF4'])



# ---------------------------------------------------------------- v3 : commande « reference »
def styles(police='Times New Roman', sz='22', h1_couleur=None, h1_sz='30'):
    c = f'<w:color w:val="{h1_couleur}"/>' if h1_couleur else ''
    return (f'<w:styles {NS}><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="{police}" w:hAnsi="{police}"/><w:sz w:val="{sz}"/></w:rPr></w:rPrDefault></w:docDefaults>'
            '<w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
            f'<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:rPr><w:b/>{c}<w:sz w:val="{h1_sz}"/></w:rPr></w:style>'
            '<w:style w:type="paragraph" w:styleId="TOC1"><w:name w:val="toc 1"/><w:basedOn w:val="Normal"/></w:style>'
            '<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/></w:style></w:styles>')


def numerotation(fmt='bullet', glyphe='•'):
    return (f'<w:numbering {NS}><w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0"><w:numFmt w:val="{fmt}"/><w:lvlText w:val="{glyphe}"/></w:lvl></w:abstractNum>'
            '<w:num w:numId="2"><w:abstractNumId w:val="0"/></w:num></w:numbering>')


def pied(champs=('PAGE', 'NUMPAGES')):
    f = ''.join(f'<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> {c} </w:instrText></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r>' for c in champs)
    return f'<w:ftr {NS}><w:p>{run("Page ")}{f}</w:p></w:ftr>'


def docx_ref(dossier, nom, corps, st=None, num=None, ftr=None, garde=None):
    f = os.path.join(dossier, nom)
    types = TYPES.replace('</Types>', ''.join(o for o in (
        '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>' if num else '',
        '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>' if ftr else '')) + '</Types>')
    rels = DOCRELS.replace('</Relationships>', ''.join(r for r in (
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>' if num else '',
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>' if ftr else '')) + '</Relationships>')
    with zipfile.ZipFile(f, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', types); z.writestr('_rels/.rels', RELS); z.writestr('word/_rels/document.xml.rels', rels)
        z.writestr('word/document.xml', f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {NS}><w:body>{garde if garde is not None else GARDE}{corps}{SECT}</w:body></w:document>')
        z.writestr('word/styles.xml', st or styles())
        if num: z.writestr('word/numbering.xml', num)
        if ftr: z.writestr('word/footer1.xml', ftr)
    return f


LISTE = '<w:p><w:pPr><w:pStyle w:val="ListParagraph"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="2"/></w:numPr></w:pPr><w:r><w:t>Un point de liste.</w:t></w:r></w:p>'
CORPS_REF = (p('<w:r><w:t>Contexte</w:t></w:r>', 'Heading1') + p('<w:r><w:t>Un paragraphe de corps sans taille directe, au format du rapport.</w:t></w:r>') + LISTE)


class Reference(unittest.TestCase):
    def setUp(self):
        self.d = dossier_essai('controler_mise_en_forme_v3_reference')
        self.ref = docx_ref(self.d, 'rapport_v1.docx', CORPS_REF, num=numerotation(), ftr=pied())

    def test_document_identique_conforme(self):
        doc = docx_ref(self.d, 'journal_v1.docx', CORPS_REF, num=numerotation(), ftr=pied())
        R = C.comparer_reference(self.ref, doc)
        self.assertEqual((R['verdict'], R['ecarts']), ('conforme', []))

    def test_calibri_et_titres_bleus_refuses(self):
        doc = docx_ref(self.d, 'journal_v1.docx', CORPS_REF, st=styles('Calibri', '19', h1_couleur='1F3864', h1_sz='26'), num=numerotation(), ftr=pied())
        with zipfile.ZipFile(doc) as z: st = z.read('word/styles.xml').decode()
        self.assertIn('w:ascii="Calibri"', st); self.assertIn('1F3864', st)                     # le défaut est bien injecté
        R = C.comparer_reference(self.ref, doc); cs = {e['code'] for e in R['ecarts']}
        self.assertEqual(R['verdict'], 'non conforme'); self.assertTrue({'FR1', 'FR2', 'FR3'} <= cs, R['ecarts'])
        corps = [e for e in R['ecarts'] if e['code'] == 'FR1' and e['categorie'] == 'corps']
        self.assertEqual(corps[0]['detail'], 'dominante Calibri 9.5 pt au lieu de Times New Roman 11 pt')

    def test_puces_et_pied_de_page(self):
        doc = docx_ref(self.d, 'journal_v1.docx', CORPS_REF, num=numerotation('decimal', '%1.'), ftr=pied(('PAGE',)))
        cs = sorted(e['code'] for e in C.comparer_reference(self.ref, doc)['ecarts'])
        self.assertEqual(cs, ['FR4', 'FR5'])

    def test_page_de_garde_jamais_comparee(self):
        garde = p('<w:r><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:sz w:val="56"/></w:rPr><w:t>Titre de couverture</w:t></w:r>') + p(run('Table des matières'), 'TOC1')
        doc = docx_ref(self.d, 'journal_v1.docx', CORPS_REF, num=numerotation(), ftr=pied(), garde=garde)
        self.assertEqual(C.comparer_reference(self.ref, doc)['ecarts'], [])

    def test_ligne_de_commande(self):
        doc = docx_ref(self.d, 'journal_v1.docx', CORPS_REF, st=styles('Calibri', '19'), num=numerotation(), ftr=pied())
        r = subprocess.run([sys.executable, OUTIL, 'reference', self.ref], capture_output=True, text=True); self.assertEqual(r.returncode, 2)
        j = os.path.join(self.d, 'reference_v1.json')
        r = subprocess.run([sys.executable, OUTIL, 'reference', self.ref, doc, '--json', j], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stderr); self.assertIn('non conforme', r.stdout)
        r2 = subprocess.run([sys.executable, OUTIL, 'reference', self.ref, doc, '--json', j], capture_output=True, text=True)
        self.assertNotEqual(r2.returncode, 0); self.assertIn('FileExistsError', r2.stderr)       # v3 : jamais d'écrasement du JSON


from aide_tests_v2 import RACINE_CC
RAPPORT = os.path.join(os.path.dirname(RACINE_CC), '16_version_finale', '98_livrables')   # dossier de travail voisin de l'espace (cloud et PC)


@unittest.skipUnless(os.path.isdir(RAPPORT), 'livrables réels absents de cet espace')
class ReferenceReelle(unittest.TestCase):
    """Le cas du 16 oct. 2026 : le journal livré avec le rapport v6.0.10 était en Calibri 9,5 pt (erreur 6 du tableau de bord)."""
    R = os.path.join(RAPPORT, 'Rapport_Etude_v6.0.10-rev1.docx'); J = os.path.join(RAPPORT, 'Journal_version_finale_v6.0.10-rev1.docx')

    def test_rapport_face_a_lui_meme(self):
        self.assertEqual(C.comparer_reference(self.R, self.R)['verdict'], 'conforme')

    def test_journal_livre_non_conforme(self):
        R = C.comparer_reference(self.R, self.J)
        self.assertEqual(R['verdict'], 'non conforme')
        self.assertTrue(any(e['code'] == 'FR1' and e['categorie'] == 'corps' and 'Calibri' in e['detail'] for e in R['ecarts']), R['ecarts'])

if __name__ == '__main__':
    unittest.main()
