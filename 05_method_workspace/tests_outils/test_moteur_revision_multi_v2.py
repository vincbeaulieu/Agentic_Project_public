"""Tests de moteur_revision_multi_v2. (a) Non-régression : toute la suite v1 (remplacement suivi sous l'auteur, révision d'un
autre auteur scindée, insertion et suppression de paragraphes, sauvegarde et relecture, cas limites) est rejouée sur la
version 2. (b) Correction de la v2 : un docx sans aucun commentaire s'ouvre, se révise et s'enregistre, que comments.xml soit
vide, auto-fermant ou absent avec commentsExtended.xml, commentsIds.xml, commentsExtensible.xml et people.xml ; aucune part
n'est alors créée ; un docx sans aucun identifiant w:id s'ouvre aussi ; les parts manquantes ne sont créées (avec type de
contenu et relation du document) que si un commentaire ou une réponse est ajouté."""
import os, re, zipfile, unittest
from lxml import etree
from aide_tests_v2 import dossier_essai, importer_version
import test_moteur_revision_multi_v1 as T1

M2 = importer_version('moteur_revision_multi', 2, 'moteur_revision_multi_v2_essai')
q, vue, run, AUTEUR, P1, P2, P3, T1_, T3 = T1.q, T1.vue, T1.run, T1.AUTEUR, T1.P1, T1.P2, T1.P3, T1.T1, T1.T3
PARTS = ['word/comments.xml', 'word/commentsExtended.xml', 'word/commentsIds.xml', 'word/commentsExtensible.xml', 'word/people.xml']
CT = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
      '<Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" '
      'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')


class SurV2:
    """Rejoue une classe de la suite v1 avec la version 2, puis restaure."""
    @classmethod
    def setUpClass(cls):
        cls._sauve = T1.M; T1.M = M2

    @classmethod
    def tearDownClass(cls):
        T1.M = cls._sauve


class DocRV1SurV2(SurV2, T1.DocR):
    def test_defaut_docx_sans_commentaire(self): pass   # remplacé par Corrige.test_defaut_docx_sans_commentaire


def variante(nom, retirer=(), remplacer=None, emballage=False, src=None):
    """Docx d'essai de la suite v1 (sans commentaire) ou src, parts retirées ou remplacées ; emballage : types et relations."""
    d = dossier_essai('moteur_revision_multi_v2')
    if src is None: src = T1.ecrire_docx(os.path.join(d, f'{nom}_base.docx'), commentaires=False)
    f = os.path.join(d, f'{nom}_v1.docx')
    with zipfile.ZipFile(src) as a, zipfile.ZipFile(f, 'w') as b:
        for n in a.namelist():
            if n not in retirer: b.writestr(n, (remplacer or {}).get(n, a.read(n)))
        if emballage: b.writestr('[Content_Types].xml', CT); b.writestr('word/_rels/document.xml.rels', RELS)
    return f, d


def lire(f):
    with zipfile.ZipFile(f) as z: return {n: z.read(n) for n in z.namelist()}


class Corrige(unittest.TestCase):
    def reviser(self, d):
        d.appliquer_texte(P1, 'Le taux est de 15 % sur trois lignes.'); n = d.insert_after(P1, 'Ajout.'); d.delete_paragraph(P3)
        return n

    def relire(self, out, n):
        r = M2.DocR(out, author=AUTEUR)
        self.assertEqual((r.text(P1), r.text(n), r.text(P3)), ('Le taux est de 15 % sur trois lignes.', 'Ajout.', ''))
        self.assertEqual(vue(r.P(P1), AUTEUR), T1_); self.assertEqual(vue(r.P(P3), AUTEUR), T3)
        return r

    def test_defaut_docx_sans_commentaire(self):
        f, dos = variante('vide')                                         # comments.xml présent mais sans commentaire
        d = M2.DocR(f, author=AUTEUR, init='EC')
        self.assertEqual(d.text(P1), T1_); self.assertEqual(d.comments, {}); self.assertEqual(d.next_cid, 0)
        n = self.reviser(d); out = os.path.join(dos, 'vide_v1.1c.docx'); d.save(out)
        a, b = lire(f), lire(out)
        self.assertEqual(list(a), list(b))
        self.assertEqual([a[x] for x in PARTS[:4]], [b[x] for x in PARTS[:4]])   # parts de commentaires inchangées
        self.assertIn(AUTEUR, b['word/people.xml'].decode())
        self.relire(out, n)

    def test_parts_absentes_sans_creation(self):
        f, dos = variante('absentes', retirer=PARTS, emballage=True)
        d = M2.DocR(f, author=AUTEUR, init='EC'); self.assertEqual(d.text(P2), T1.T2)
        n = self.reviser(d); out = os.path.join(dos, 'absentes_v1.1c.docx'); d.save(out)
        a, b = lire(f), lire(out)
        self.assertEqual(list(a), list(b))                                # aucune part créée
        for x in ('[Content_Types].xml', 'word/_rels/document.xml.rels', 'word/styles.xml'): self.assertEqual(a[x], b[x])
        self.relire(out, n)

    def test_sans_aucun_identifiant(self):
        doc = f'<w:document {T1.NS}><w:body><w:p w14:paraId="{P1}">{run(T1_)}</w:p><w:p w14:paraId="{P3}">{run(T3)}</w:p></w:body></w:document>'
        f, dos = variante('sans_id', retirer=PARTS, remplacer={'word/document.xml': doc})
        d = M2.DocR(f, author=AUTEUR, init='EC')
        n = self.reviser(d); out = os.path.join(dos, 'sans_id_v1.1c.docx'); d.save(out)
        ids = [x.get(q('id')) for x in d.body.iter(q('ins'), q('del'))]
        self.assertTrue(ids and all(re.fullmatch(r'\d+', i) for i in ids)); self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(list(lire(f)), list(lire(out)))
        self.relire(out, n)

    def test_commentaire_cree_les_parts(self):
        f, dos = variante('creation', retirer=PARTS, emballage=True)
        d = M2.DocR(f, author=AUTEUR, init='EC'); cid = d.new_comment(P1, ['Note.'])
        out = os.path.join(dos, 'creation_v1.1c.docx'); d.save(out); b = lire(out)
        self.assertEqual(sorted(set(b) - set(lire(f))), sorted(PARTS))
        for x in b:
            if x.endswith('.xml') or x.endswith('.rels'): etree.fromstring(b[x])          # tout reste bien formé
        ct, rels = b['[Content_Types].xml'].decode(), b['word/_rels/document.xml.rels'].decode()
        for x in PARTS:
            self.assertEqual(ct.count(f'PartName="/{x}"'), 1); self.assertEqual(rels.count(f'Target="{x[5:]}"'), 1)
        rid = re.findall(r'Id="(rId\d+)"', rels); self.assertEqual(len(rid), 6); self.assertEqual(len(set(rid)), 6)
        self.assertIn(AUTEUR, b['word/people.xml'].decode())
        r = M2.DocR(out, author=AUTEUR, init='EC')
        self.assertEqual((r.comment_text(str(cid)), r.anchor_pid(str(cid))), ('Note.', P1))
        rep = r.reply(str(cid), ['Réponse.']); out2 = os.path.join(dos, 'creation_v1.3c.docx'); r.save(out2)
        self.assertEqual(sorted(lire(out2)), sorted(b))                   # rien de plus : les parts existent déjà
        r2 = M2.DocR(out2, author=AUTEUR)
        self.assertEqual(r2.root_of(str(rep)), str(cid)); self.assertEqual(r2.thread_ids(str(cid)), [str(cid), str(rep)])

    def test_reponse_parts_partielles(self):
        f0, dos = variante('partielles_base', retirer=PARTS)
        d = M2.DocR(f0, author=AUTEUR, init='EC'); cid = d.new_comment(P1, ['Note.'])
        base = os.path.join(dos, 'partielles_base_v1.1c.docx'); d.save(base)
        f, dos = variante('partielles', retirer=PARTS[1:], src=base)       # seul comments.xml reste
        r = M2.DocR(f, author=AUTEUR, init='EC')
        out = os.path.join(dos, 'partielles_v1.1c.docx'); r.save(out)
        self.assertEqual(list(lire(f)), list(lire(out)))                  # sans ajout, rien n'est créé
        rep = r.reply(str(cid), ['Réponse.']); out2 = os.path.join(dos, 'partielles_v1.3c.docx'); r.save(out2)
        self.assertEqual(sorted(set(lire(out2)) - set(lire(f))), sorted(PARTS[1:]))
        r2 = M2.DocR(out2, author=AUTEUR)
        self.assertEqual(r2.root_of(str(rep)), str(cid)); self.assertEqual(r2.comment_text(str(rep)), 'Réponse.')

    def test_comments_auto_fermant(self):
        vide = f'<w:comments {T1.NS}/>'.encode()
        f, dos = variante('auto', retirer=PARTS[1:], remplacer={'word/comments.xml': vide})
        d = M2.DocR(f, author=AUTEUR, init='EC'); n = self.reviser(d)
        out = os.path.join(dos, 'auto_v1.1c.docx'); d.save(out)
        self.assertEqual(lire(out)['word/comments.xml'], vide); self.relire(out, n)
        cid = d.new_comment(P2, ['Note.']); out2 = os.path.join(dos, 'auto_v1.3c.docx'); d.save(out2)
        self.assertEqual(M2.DocR(out2, author=AUTEUR).comment_text(str(cid)), 'Note.')


if __name__ == '__main__':
    unittest.main()
