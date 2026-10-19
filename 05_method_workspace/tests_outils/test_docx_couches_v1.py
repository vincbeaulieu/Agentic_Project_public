"""Tests de docx_couches_v1 (bibliothèque ; petits docx synthétiques écrits avec zipfile : une insertion de « Collègue A »,
une suppression de « Collègue B », un paragraphe inséré par A, un commentaire et sa réponse) : revisions_par_auteur (compte
par type et auteur) ; refuser (insertion de A retirée, paragraphe inséré retiré, repères de commentaire conservés ; suppression
de B rendue au texte ; ligne de tableau insérée retirée) ; couches (segments, chaîne des révisions, marque de paragraphe,
rsid et style de référence de commentaire ignorés) ; comparer_refus (conforme, paragraphe en écart, nombre de paragraphes) ;
commentaires (parent, racine, docx sans commentaires) ; ligne de commande (code 0 / 1 ; sans argument : défaut signalé)."""
import os, sys, zipfile, subprocess, unittest
from lxml import etree
from aide_tests_v2 import dossier_essai, chemin_version, importer_version, OUTILS

OUTIL = chemin_version('docx_couches', 1)
DC = importer_version('docx_couches', 1)
q = DC.q
NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
      'xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml"')
D = '2026-01-01T00:00:00Z'
A = f'w:author="Collègue A" w:date="{D}"'
B = f'w:author="Collègue B" w:date="{D}"'
P1 = ('<w:p w14:paraId="0000000A"><w:r><w:t xml:space="preserve">Le </w:t></w:r>'
      f'<w:ins w:id="1" {A}><w:commentRangeStart w:id="0"/><w:r><w:t xml:space="preserve">petit </w:t></w:r></w:ins>'
      f'<w:r><w:t xml:space="preserve">chat </w:t></w:r><w:del w:id="2" {B}><w:r><w:delText xml:space="preserve">noir </w:delText></w:r></w:del>'
      '<w:r><w:t>dort.</w:t></w:r><w:commentRangeEnd w:id="0"/><w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr><w:commentReference w:id="0"/></w:r></w:p>')
P2 = '<w:p w14:paraId="0000000B"><w:r><w:rPr w:rsidR="00AA0001"><w:b/></w:rPr><w:t>Fi</w:t></w:r><w:r><w:rPr><w:b/></w:rPr><w:t>n.</w:t></w:r></w:p>'
P3 = f'<w:p w14:paraId="0000000C"><w:pPr><w:rPr><w:ins w:id="3" {A}/></w:rPr></w:pPr><w:ins w:id="4" {A}><w:r><w:t>Ajout.</w:t></w:r></w:ins></w:p>'
# Attendu après refus de A : P1 sans « petit », P2, plus de P3.
P1_REF = (f'<w:p w14:paraId="0000000A"><w:r><w:t xml:space="preserve">Le chat </w:t></w:r><w:del w:id="2" {B}><w:r><w:delText xml:space="preserve">noir </w:delText></w:r></w:del>'
          '<w:r><w:t>dort.</w:t></w:r></w:p>')


def corps(xml): return etree.fromstring(f'<w:document {NS}><w:body>{xml}</w:body></w:document>')


def ecrire_docx(f, xml, commentaires=True):
    with zipfile.ZipFile(f, 'w') as z:
        z.writestr('word/document.xml', f'<w:document {NS}><w:body>{xml}</w:body></w:document>')
        if commentaires:
            z.writestr('word/comments.xml', f'<w:comments {NS}><w:comment w:id="0" {A} w:initials="CA"><w:p w14:paraId="0000C001"><w:r><w:t>Question ?</w:t></w:r></w:p></w:comment>'
                                            f'<w:comment w:id="1" {B} w:initials="CB"><w:p w14:paraId="0000C002"><w:r><w:t>Première ligne</w:t></w:r></w:p>'
                                            '<w:p w14:paraId="0000C003"><w:r><w:t>Réponse.</w:t></w:r></w:p></w:comment></w:comments>')
            z.writestr('word/commentsExtended.xml', f'<w15:commentsEx {NS}><w15:commentEx w15:paraId="0000C001" w15:done="0"/>'
                                                    '<w15:commentEx w15:paraId="0000C003" w15:paraIdParent="0000C001" w15:done="0"/></w15:commentsEx>')
    return f


def texte(root, balise='t'): return [''.join(t.text or '' for t in p.iter(q(balise))) for p in root.iter(q('p'))]


class Revisions(unittest.TestCase):
    def test_revisions_par_auteur(self):
        f = ecrire_docx(os.path.join(dossier_essai('docx_couches_revisions'), 'doc_v1.docx'), P1 + P2 + P3)
        self.assertEqual(dict(DC.revisions_par_auteur(f)), {('ins', 'Collègue A'): 3, ('del', 'Collègue B'): 1})

    def test_refuser_insertions_de_A(self):
        root = corps(P1 + P2 + P3)
        self.assertEqual(DC.refuser(root, 'Collègue A'), {'par_ins': 1, 'ins': 1})
        self.assertEqual(texte(root), ['Le chat dort.', 'Fin.'])
        self.assertEqual(texte(root, 'delText'), ['noir ', ''])                                   # suppression de B intacte
        self.assertEqual([e.get(q('author')) for e in root.iter(q('ins'), q('del'))], ['Collègue B'])
        self.assertEqual(len(list(root.iter(q('commentRangeStart')))), 1)                        # repère sorti de l'insertion

    def test_refuser_suppression_de_B_et_ligne(self):
        root = corps(P1 + P2 + P3)
        self.assertEqual(DC.refuser(root, 'Collègue B'), {'del': 1})
        self.assertEqual(texte(root)[0], 'Le petit chat noir dort.'); self.assertEqual(list(root.iter(q('delText'))), [])
        self.assertEqual(len([e for e in root.iter(q('ins')) if e.get(q('author')) == 'Collègue A']), 3)
        tab = corps(f'<w:tbl><w:tr><w:tc><w:p><w:r><w:t>L1</w:t></w:r></w:p></w:tc></w:tr><w:tr><w:trPr><w:ins w:id="7" {A}/></w:trPr>'
                    f'<w:tc><w:p><w:r><w:t>L2</w:t></w:r></w:p></w:tc></w:tr><w:tr><w:trPr><w:del w:id="8" {A}/></w:trPr><w:tc><w:p><w:r><w:t>L3</w:t></w:r></w:p></w:tc></w:tr></w:tbl>')
        self.assertEqual(DC.refuser(tab, 'Collègue A'), {'ligne_ins': 1, 'ligne_del': 1})
        self.assertEqual(texte(tab), ['L1', 'L3']); self.assertEqual(list(tab.iter(q('del'))), [])


class Couches(unittest.TestCase):
    def test_segments_chaine_et_marque(self):
        c = {x[0]: x for x in DC.couches(corps(P1 + P2 + P3))}
        self.assertEqual(list(c), ['0000000A', '0000000B', '0000000C'])
        segs = c['0000000A'][3]
        self.assertEqual([v for k, v in segs], ['Le ', 'petit ', 'chat ', 'noir ', 'dort.'])
        self.assertEqual([k[0] for k, v in segs], ['t', 't', 't', 'text', 't'])                   # delText -> « text » (la chaîne le distingue déjà)
        self.assertEqual([k[2] for k, v in segs], [(), (('ins', 'Collègue A', D),), (), (('del', 'Collègue B', D),), ()])
        self.assertEqual(len(c['0000000B'][3]), 1); self.assertEqual(c['0000000B'][3][0][1], 'Fin.')   # rsid ignoré : un seul segment
        self.assertEqual((c['0000000C'][1], c['0000000A'][1], c['0000000A'][2]), ((('ins', 'Collègue A', D),), (), ''))
        sans_style = DC.couches(corps('<w:p w14:paraId="0000000D"><w:r><w:rPr></w:rPr><w:t>x</w:t></w:r></w:p>'))[0][3][0][0][1]
        avec_style = DC.couches(corps('<w:p w14:paraId="0000000D"><w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr><w:t>x</w:t></w:r></w:p>'))[0][3][0][0][1]
        self.assertEqual(sans_style, avec_style)

    def test_comparer_refus(self):
        d = dossier_essai('docx_couches_comparer')
        f = ecrire_docx(os.path.join(d, 'doc_v1.docx'), P1 + P2 + P3)
        n, ec = DC.comparer_refus(f, 'Collègue A', ecrire_docx(os.path.join(d, 'reference_v1.docx'), P1_REF + P2))
        self.assertEqual((n, ec), ({'par_ins': 1, 'ins': 1}, []))
        _, ec = DC.comparer_refus(f, 'Collègue A', ecrire_docx(os.path.join(d, 'reference_v2.docx'), P1_REF.replace('chat', 'chien') + P2))
        self.assertEqual(ec, ['0000000A'])
        _, ec = DC.comparer_refus(f, 'Collègue A', ecrire_docx(os.path.join(d, 'reference_v3.docx'), P1_REF + P2 + P3))
        self.assertEqual(ec, ['nombre de paragraphes 2 / 3'])


class Commentaires(unittest.TestCase):
    def test_parent_racine_et_absence(self):
        d = dossier_essai('docx_couches_commentaires')
        c = DC.commentaires(ecrire_docx(os.path.join(d, 'doc_v1.docx'), P1))
        self.assertEqual(c['0'], dict(auteur='Collègue A', date=D, texte='Question ?', parent=None, racine='0'))
        self.assertEqual(c['1'], dict(auteur='Collègue B', date=D, texte='Première ligne\nRéponse.', parent='0', racine='0'))
        self.assertEqual(DC.commentaires(ecrire_docx(os.path.join(d, 'doc_v2.docx'), P2, commentaires=False)), {})


class LigneDeCommande(unittest.TestCase):
    def test_codes_de_sortie(self):
        d = dossier_essai('docx_couches_cli'); env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(OUTILS, '_compat'), OUTILS]))
        f = ecrire_docx(os.path.join(d, 'doc_v1.docx'), P1 + P2 + P3)
        r = subprocess.run([sys.executable, OUTIL, f, 'Collègue A', ecrire_docx(os.path.join(d, 'reference_v1.docx'), P1_REF + P2)], capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr); self.assertIn('refus conforme', r.stdout)
        r = subprocess.run([sys.executable, OUTIL, f, 'Collègue B', ecrire_docx(os.path.join(d, 'reference_v2.docx'), P1_REF + P2)], capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(r.returncode, 1, r.stderr); self.assertIn('ÉCART', r.stdout)
        self.assertNotEqual(subprocess.run([sys.executable, OUTIL], capture_output=True, text=True, env=env, timeout=120).returncode, 0)

    @unittest.expectedFailure
    def test_sans_argument_message_usage(self):
        # Défaut : sans argument, l'outil s'arrête sur une trace « ValueError: not enough values to unpack » (code 1)
        # au lieu d'afficher son USAGE avec un code 2.
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(OUTILS, '_compat'), OUTILS]))
        r = subprocess.run([sys.executable, OUTIL], capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(r.returncode, 2); self.assertIn('USAGE', (r.stdout + r.stderr).upper()); self.assertNotIn('Traceback', r.stderr)


if __name__ == '__main__':
    unittest.main()
