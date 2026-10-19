"""Tests de moteur_revision_multi_v1 (bibliothèque, classe DocR) sur de petits docx synthétiques écrits avec zipfile :
remplacement par diff de mots en w:del/w:ins sous l'auteur donné, vue « tout accepté » (text) conforme ; révision w:ins d'un
autre auteur (Collègue A) scindée mais jamais modifiée de l'intérieur ; insertion de paragraphe (insert_after, insert_before)
avec paraId nouveau, y compris après un tirage déjà pris ; suppression de paragraphe (marque et runs en w:del) et retrait pur
d'un paragraphe que nous avons inséré ; sauvegarde puis relecture (people.xml complété, parts non touchées identiques,
refuser nos révisions redonne le texte reçu) ; cas limites (texte identique : 0 opération et XML inchangé, plage vide,
paraId inconnu). Défaut signalé (expectedFailure) : un docx sans aucun commentaire ne s'ouvre pas."""
import os, re, zipfile, unittest
from unittest import mock
from lxml import etree
from aide_tests_v2 import dossier_essai, importer_version

M = importer_version('moteur_revision_multi', 1)
WN = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
W14 = 'http://schemas.microsoft.com/office/word/2010/wordml'
NS = f'xmlns:w="{WN}" xmlns:w14="{W14}"'
W15 = 'xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml"'
AUTEUR = 'Essai - Claude'; AUTRE = 'Collègue A'
P1, P2, P3 = '00ABCDEF', '0000000B', '0000000C'
T1 = 'Le taux est de 12 % sur trois lignes.'
T2 = 'Base. texte ajouté par un autre auteur.'
T3 = 'Paragraphe à supprimer.'


def q(t): return '{%s}%s' % (WN, t)


def ln(e): return etree.QName(e).localname if isinstance(e.tag, str) else None


def run(t): return f'<w:r><w:t xml:space="preserve">{t}</w:t></w:r>'


def corps():
    return (f'<w:p w14:paraId="{P1}">{run("Le taux est de ")}{run("12 % sur trois lignes.")}</w:p>'
            f'<w:p w14:paraId="{P2}">{run("Base. ")}<w:ins w:id="1" w:author="{AUTRE}" w:date="2026-10-01T00:00:00Z">'
            f'{run("texte ajouté par ")}{run("un autre auteur.")}</w:ins></w:p>'
            f'<w:p w14:paraId="{P3}">{run(T3)}</w:p>')


def ecrire_docx(f, commentaires=True):
    cm = (f'<w:comment w:id="0" w:author="{AUTRE}" w:date="2026-10-01T00:00:00Z" w:initials="CA">'
          f'<w:p w14:paraId="0000C001">{run("Remarque.")}</w:p></w:comment>') if commentaires else ''
    ex = '<w15:commentEx w15:paraId="0000C001" w15:done="0"/>' if commentaires else ''
    parts = {
        'word/document.xml': f'<w:document {NS}><w:body>{corps()}</w:body></w:document>',
        'word/comments.xml': f'<w:comments {NS}>{cm}</w:comments>',
        'word/commentsExtended.xml': f'<w15:commentsEx {W15}>{ex}</w15:commentsEx>',
        'word/commentsIds.xml': '<w16cid:commentsIds xmlns:w16cid="http://schemas.microsoft.com/office/word/2016/wordml/cid"></w16cid:commentsIds>',
        'word/commentsExtensible.xml': '<w16cex:commentsExtensible xmlns:w16cex="http://schemas.microsoft.com/office/word/2018/wordml/cex"></w16cex:commentsExtensible>',
        'word/people.xml': f'<w15:people {W15}><w15:person w15:author="{AUTRE}"/></w15:people>',
        'word/styles.xml': f'<w:styles {NS}/>'}
    with zipfile.ZipFile(f, 'w') as z:
        for n, x in parts.items(): z.writestr(n, x)
    return f


def nouveau(nom, **k):
    d = dossier_essai('moteur_revision_multi'); f = ecrire_docx(os.path.join(d, f'{nom}_v1.docx'), **k)
    return M.DocR(f, author=AUTEUR, init='EC'), d


def dans(e, tag, auteur=None):
    """Premier ancêtre w:<tag> de e dans son paragraphe (filtré par auteur si donné)."""
    for a in e.iterancestors():
        if ln(a) == 'p': return None
        if ln(a) == tag and (auteur is None or a.get(q('author')) == auteur): return a
    return None


def vue(p, refuser_auteur=None):
    """Texte indépendant du moteur : tout accepté, ou (refuser_auteur) nos révisions refusées et les autres acceptées."""
    out = []
    for x in p.iter(q('t'), q('delText')):
        if refuser_auteur is None:
            if ln(x) == 't' and dans(x, 'del') is None: out.append(x.text or '')
        elif ln(x) == 't' and dans(x, 'ins', refuser_auteur) is None and dans(x, 'del') is None: out.append(x.text or '')
        elif ln(x) == 'delText' and dans(x, 'del', refuser_auteur) is not None and dans(x, 'ins', refuser_auteur) is None:
            out.append(x.text or '')
    return ''.join(out)


def marque(p, tag):
    rp = p.find(f'{q("pPr")}/{q("rPr")}')
    return rp.find(q(tag)) if rp is not None else None


class DocR(unittest.TestCase):
    def test_remplacement_suivi_sous_l_auteur(self):
        d, _ = nouveau('remplacement'); nv = 'Le taux est de 15 % sur trois lignes.'
        self.assertEqual(d.text(P1), T1)
        self.assertEqual(d.appliquer_texte(P1, nv), 1)                     # un seul mot changé
        self.assertEqual(d.text(P1), nv)
        p = d.P(P1)
        dels, inss = p.findall(f'.//{q("del")}'), p.findall(f'.//{q("ins")}')
        self.assertEqual([x.get(q('author')) for x in dels + inss], [AUTEUR, AUTEUR])
        self.assertEqual(''.join(t.text for t in dels[0].iter(q('delText'))), '12')
        self.assertEqual(''.join(t.text for t in inss[0].iter(q('t'))), '15')
        self.assertTrue(all(x.get(q('id')) and x.get(q('date')) for x in dels + inss))
        self.assertEqual(vue(p), nv); self.assertEqual(vue(p, AUTEUR), T1)  # tout accepté / nos révisions refusées

    def test_autre_auteur_non_modifie_de_l_interieur(self):
        d, _ = nouveau('autre_auteur'); nv = 'Base. texte modifié par un autre auteur.'
        d.appliquer_texte(P2, nv); p = d.P(P2)
        self.assertEqual(d.text(P2), nv)
        notres = [x for x in p.iter(q('ins')) if x.get(q('author')) == AUTEUR]
        self.assertEqual(len(notres), 1)
        self.assertIsNone(dans(notres[0], 'ins'))                         # jamais à l'intérieur d'une révision d'autrui
        self.assertEqual(''.join(t.text for t in notres[0].iter(q('t'))), 'modifié')
        a = [x for x in p.iter(q('ins')) if x.get(q('author')) == AUTRE]
        self.assertGreaterEqual(len(a), 2)                                # conteneur scindé
        self.assertIn('1', [x.get(q('id')) for x in a])                   # l'original garde son id
        self.assertEqual(''.join(t.text for x in a for t in x.iter(q('t'), q('delText'))), 'texte ajouté par un autre auteur.')
        self.assertTrue(all(x.get(q('author')) == AUTEUR for x in p.iter(q('del'))))
        self.assertEqual(vue(p), nv); self.assertEqual(vue(p, AUTEUR), T2)

    def test_insertion_paragraphe_paraid_nouveau(self):
        d, _ = nouveau('insertion'); avant = set(d.used_para)
        self.assertIn('0000C001', avant)                                  # paraId des commentaires compris
        n1 = d.insert_after(P1, 'Nouveau paragraphe.'); n2 = d.insert_before(P3, 'Avant le dernier.')
        for n in (n1, n2):
            self.assertRegex(n, r'^[0-9A-F]{8}$'); self.assertNotIn(n, avant)
            np_ = d.P(n); self.assertEqual(marque(np_, 'ins').get(q('author')), AUTEUR)
        self.assertNotEqual(n1, n2)
        self.assertEqual(d.text(n1), 'Nouveau paragraphe.'); self.assertEqual(d.text(n2), 'Avant le dernier.')
        ordre = [p.get('{%s}paraId' % W14) for p in d.body.iter(q('p'))]
        self.assertEqual(ordre, [P1, n1, P2, n2, P3])
        with mock.patch.object(M.random, 'randint', side_effect=[int(P1, 16), int(n1, 16), 0x00ABCDF0]):
            n3 = d.insert_after(P2, 'Tirage déjà pris.')                  # deux tirages pris, le troisième retenu
        self.assertEqual(n3, '00ABCDF0')

    def test_suppression_paragraphe(self):
        d, _ = nouveau('suppression')
        self.assertEqual(d.delete_paragraph(P3), 'ok'); p = d.P(P3)
        self.assertEqual(d.text(P3), '')
        self.assertEqual(marque(p, 'del').get(q('author')), AUTEUR)
        self.assertEqual(''.join(t.text for t in p.iter(q('delText'))), T3)
        self.assertEqual(vue(p, AUTEUR), T3)
        n = d.insert_after(P1, 'Éphémère.')                              # notre propre paragraphe : retrait pur
        self.assertEqual(d.delete_paragraph(n), 'retire')
        self.assertRaises(KeyError, d.P, n)
        self.assertNotIn(n, [x.get('{%s}paraId' % W14) for x in d.body.iter(q('p'))])

    def test_sauvegarde_tout_accepte_et_refus(self):
        d, dos = nouveau('sauvegarde')
        d.appliquer_texte(P1, 'Le taux est de 15 % sur deux lignes.')
        d.appliquer_texte(P2, 'Base. texte modifié par un autre auteur.')
        n = d.insert_after(P2, 'Ajout final.'); d.delete_paragraph(P3)
        src = os.path.join(dos, 'sauvegarde_v1.docx'); out = os.path.join(dos, 'sauvegarde_v1.1c.docx'); d.save(out)
        self.assertTrue(os.path.exists(src))                              # le fichier reçu n'est pas écrasé
        with zipfile.ZipFile(src) as a, zipfile.ZipFile(out) as b:
            self.assertEqual(a.namelist(), b.namelist())
            self.assertEqual(a.read('word/styles.xml'), b.read('word/styles.xml'))
            self.assertIn(AUTEUR, b.read('word/people.xml').decode())
            body = etree.fromstring(b.read('word/document.xml')).find(q('body'))
        ps = {p.get('{%s}paraId' % W14): p for p in body.iter(q('p'))}
        acc = [vue(p) for k, p in ps.items() if marque(p, 'del') is None]
        self.assertEqual(acc, ['Le taux est de 15 % sur deux lignes.', 'Base. texte modifié par un autre auteur.', 'Ajout final.'])
        recu = [vue(p, AUTEUR) for k, p in ps.items() if marque(p, 'ins') is None]
        self.assertEqual(recu, [T1, T2, T3])                              # refuser nos révisions redonne le document reçu
        r = M.DocR(out, author=AUTEUR)
        self.assertEqual((r.text(P1), r.text(n), r.text(P3)), ('Le taux est de 15 % sur deux lignes.', 'Ajout final.', ''))

    def test_cas_limites(self):
        d, _ = nouveau('limites'); xml0 = etree.tostring(d.doc)
        self.assertEqual(d.appliquer_texte(P1, T1), 0)                   # rien à faire
        self.assertEqual(etree.tostring(d.doc), xml0)
        self.assertEqual(d.replace_span(P1, 5, 5, ''), 'rien')
        self.assertEqual(etree.tostring(d.doc), xml0)
        self.assertRaises(KeyError, d.text, 'FFFFFFFF')
        self.assertRaises(KeyError, d.appliquer_texte, 'FFFFFFFF', 'x')
        d.appliquer_texte(P1, T1 + ' Fin.')                              # insertion pure en fin de paragraphe
        p = d.P(P1)
        self.assertEqual(p.findall(f'.//{q("del")}'), [])
        self.assertEqual(d.text(P1), T1 + ' Fin.'); self.assertEqual(vue(p, AUTEUR), T1)

    @unittest.expectedFailure
    def test_defaut_docx_sans_commentaire(self):
        # Défaut : ENTREES annonce « docx (tous auteurs) », mais un docx sans aucun commentaire (comments.xml vide) ne s'ouvre
        # pas : Doc.__init__ calcule max() des identifiants de commentaires sur une liste vide (ValueError).
        d, _ = nouveau('sans_commentaire', commentaires=False)
        self.assertEqual(d.text(P1), T1)


if __name__ == '__main__':
    unittest.main()
