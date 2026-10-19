"""Tests de moteur_revision_multi_v3. (a) Non-régression : suite v2 rejouée sur la version 3 (et, par elle, la suite v1). (b) Correction :
déplacement suivi d'un paragraphe qui porte des révisions d'un autre auteur (insertion, suppression, marque de paragraphe insérée) et un
commentaire :
- leurs révisions sont imbriquées dans l'enveloppe moveFrom / moveTo (témoin v2 : elles restaient dehors) ;
- leur marque de paragraphe insérée est gardée à côté de la nôtre, dans l'ordre du schéma (témoin v2 : effacée) ;
- les révisions de la copie ont des identifiants neufs : aucun w:id de révision en double (témoin v2 : doublons) ;
- le commentaire suit le paragraphe (marqueurs complets dans la copie, aucun à la source) ;
- refuser nos révisions (docx_couches v4) redonne le document d'origine ;
- accepter nos révisions seules (accepter_auteurs v2) : le paragraphe à sa nouvelle place, les révisions de l'autre auteur toujours en
  suivi ; accepter tout : ordre et textes attendus."""
import os, zipfile, collections, unittest
from lxml import etree
from aide_tests_v2 import dossier_essai, importer_version
import test_moteur_revision_multi_v1 as T1
import test_moteur_revision_multi_v2 as T2

M3 = importer_version('moteur_revision_multi', 3, 'moteur_revision_multi_v3_essai')
M2 = importer_version('moteur_revision_multi', 2, 'moteur_revision_multi_v2_temoin')
DC4 = importer_version('docx_couches', 4, 'docx_couches_v4_pour_moteur3')
AC2 = importer_version('accepter_auteurs', 2, 'accepter_auteurs_v2_pour_moteur3')
q, run, NS, W15, AUTEUR, AUTRE = T1.q, T1.run, T1.NS, T1.W15, T1.AUTEUR, T1.AUTRE
REV = ('ins', 'del', 'moveFrom', 'moveTo', 'rPrChange', 'pPrChange')


class SurV3:
    @classmethod
    def setUpClass(cls):
        cls._s3 = (T1.M, T2.M2); T1.M = M3; T2.M2 = M3

    @classmethod
    def tearDownClass(cls): T1.M, T2.M2 = cls._s3


class DocRV1SurV3(SurV3, T2.DocRV1SurV2): pass
class CorrigeV2SurV3(SurV3, T2.Corrige): pass


def tr(tag, x, i, a=AUTRE): return f'<w:{tag} w:id="{i}" w:author="{a}" w:date="2026-10-01T00:00:00Z">{x}</w:{tag}>'


def docx_deplacement(d, nom='deplacement_v1.docx'):
    p2 = (f'<w:p w14:paraId="000000B2"><w:pPr><w:rPr>{tr("ins", "", 9)}</w:rPr></w:pPr>'
          f'<w:commentRangeStart w:id="0"/>{run("[2]	Beta ")}{tr("ins", run("ajout "), 10)}'
          f'{tr("del", "<w:r><w:delText xml:space=\"preserve\">retrait </w:delText></w:r>", 11)}<w:commentRangeEnd w:id="0"/>'
          f'<w:r><w:commentReference w:id="0"/></w:r></w:p>')
    corps = (f'<w:p w14:paraId="000000B1">{run("[1]	Alpha")}</w:p>' + p2 + f'<w:p w14:paraId="000000B3">{run("[3]	Gamma")}</w:p>'
             f'<w:p w14:paraId="000000B4">{run("Fin")}</w:p>')
    parts = {'word/document.xml': f'<w:document {NS}><w:body>{corps}</w:body></w:document>',
             'word/comments.xml': f'<w:comments {NS}><w:comment w:id="0" w:author="{AUTRE}" w:date="2026-10-01T00:00:00Z" w:initials="CA"><w:p w14:paraId="0000C001">{run("Remarque.")}</w:p></w:comment></w:comments>',
             'word/commentsExtended.xml': f'<w15:commentsEx {W15}><w15:commentEx w15:paraId="0000C001" w15:done="0"/></w15:commentsEx>',
             'word/people.xml': f'<w15:people {W15}><w15:person w15:author="{AUTRE}"/></w15:people>', 'word/styles.xml': f'<w:styles {NS}/>'}
    f = os.path.join(d, nom)
    with zipfile.ZipFile(f, 'w') as z:
        for n, x in parts.items(): z.writestr(n, x)
    return f


def lire(f): return etree.fromstring(zipfile.ZipFile(f).read('word/document.xml'))


def textes(root):
    """Vue « tout accepté » : texte hors suppressions et hors source de déplacement, paragraphes à marque supprimée ou déplacée retirés."""
    out = []
    for p in root.iter(q('p')):
        rp = p.find(q('pPr') + '/' + q('rPr'))
        if rp is not None and (rp.find(q('del')) is not None or rp.find(q('moveFrom')) is not None): continue
        out.append(''.join(('\t' if T1.ln(t) == 'tab' else (t.text or '')) for t in p.iter(q('t'), q('tab'))
                           if not any(T1.ln(a) in ('del', 'moveFrom') for a in t.iterancestors())))
    return out


class Deplacement(unittest.TestCase):
    def deplacer(self, M):
        d = dossier_essai('moteur_revision_multi_v3_deplacement'); f = docx_deplacement(d)
        D = M.DocR(f, author=AUTEUR, init='EC'); D.move_block('000000B2', '000000B2', '000000B3', 'apres')
        out = os.path.join(d, 'deplacement_v2.docx'); D.save(out); return f, out

    def test_revisions_imbriquees_et_marque_gardee(self):
        f, out = self.deplacer(M3); R = lire(out)
        for e in R.iter(q('ins'), q('del')):
            if e.get(q('author')) == AUTRE and T1.ln(e.getparent()) != 'rPr':
                self.assertTrue(any(T1.ln(a) in ('moveFrom', 'moveTo') for a in e.iterancestors()), 'révision de l\'autre auteur hors du déplacement')
        src = [p for p in R.iter(q('p')) if p.find(q('pPr') + '/' + q('rPr') + '/' + q('moveFrom')) is not None][0]
        self.assertEqual([T1.ln(m) for m in src.find(q('pPr') + '/' + q('rPr'))], ['ins', 'moveFrom'])
        self.assertEqual(src.find(q('pPr') + '/' + q('rPr') + '/' + q('ins')).get(q('author')), AUTRE)

    def test_temoin_v2(self):
        f, out = self.deplacer(M2); R = lire(out)
        dehors = [e for e in R.iter(q('ins'), q('del')) if e.get(q('author')) == AUTRE and T1.ln(e.getparent()) != 'rPr'
                  and not any(T1.ln(a) in ('moveFrom', 'moveTo') for a in e.iterancestors())]
        self.assertTrue(dehors)                                                   # la v2 laissait leurs révisions hors de l'enveloppe

    def test_identifiants_uniques(self):
        f, out = self.deplacer(M3); R = lire(out)
        ids = collections.Counter(e.get(q('id')) for t in REV for e in R.iter(q(t)) if e.get(q('id')) is not None)
        self.assertEqual([k for k, v in ids.items() if v > 1], [])

    def test_commentaire_suit(self):
        f, out = self.deplacer(M3); R = lire(out)
        for t in ('commentRangeStart', 'commentRangeEnd', 'commentReference'):
            e = list(R.iter(q(t))); self.assertEqual(len(e), 1, t)
            p = next(e[0].iterancestors(q('p'))); self.assertIsNotNone(p.find(q('pPr') + '/' + q('rPr') + '/' + q('moveTo')), t)

    def test_refus_et_acceptation(self):
        f, out = self.deplacer(M3)
        R = lire(out); DC4.refuser(R, AUTEUR)
        self.assertEqual(DC4.couches(R), DC4.couches(lire(f)))                   # refuser nos révisions redonne l'origine
        A = lire(out); AC2.accepter(A, [AUTEUR])
        self.assertEqual({a for (t, a) in AC2.auteurs_revisions(A)}, {AUTRE})     # leurs révisions toujours en suivi
        self.assertEqual(textes(A), ['[1]\tAlpha', '[3]\tGamma', '[2]\tBeta ajout ', 'Fin'])
        T = lire(out); AC2.accepter(T, [AUTEUR, AUTRE]); self.assertEqual(textes(T), ['[1]\tAlpha', '[3]\tGamma', '[2]\tBeta ajout ', 'Fin'])
        self.assertEqual(dict(AC2.auteurs_revisions(T)), {})


if __name__ == '__main__':
    unittest.main()
