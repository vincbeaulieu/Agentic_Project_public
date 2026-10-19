"""Tests de renumeroter_references_v3 (v1 et v2 jamais adoptées) (rapport IEEE fictif : citations dans le corps, l'une dans l'insertion d'un autre auteur ;
bibliographie de 4 entrées, l'une non citée, une autre portant une insertion d'un autre auteur et un commentaire) :
- vue « tout accepté » : citations dans l'ordre de première citation ([2] → [1], [1] → [2], [3] inchangée), liste triée, entrée non citée
  retirée, chaque citation renvoie à la même notice qu'avant ;
- refuser nos révisions (docx_couches v4) redonne l'origine ; accepter nos seules révisions garde celles de l'autre auteur ;
- le commentaire d'une entrée reste sur sa notice (déplacée ou non) ; aucun identifiant de révision en double ;
- contrôle du suivi du skill docx (appariement auteur, date, texte) : aucune révision d'un autre auteur tenue pour nouvelle hors de notre
  copie déplacée ; aucun identifiant de révision en double ;
- refus : liste à retirer discordante, plage « [1–3] », citation sans entrée (code 4) ; jamais d'écrasement (code 3) ; usage (code 2)."""
import os, re, zipfile, collections, unittest
from lxml import etree
from aide_tests_v2 import dossier_essai, importer_version
import test_moteur_revision_multi_v1 as T1

RN = importer_version('renumeroter_references', 3, 'renumeroter_references_v3_essai')
DC4 = importer_version('docx_couches', 4, 'docx_couches_v4_pour_renum')
AC2 = importer_version('accepter_auteurs', 2, 'accepter_auteurs_v2_pour_renum')
q, run, NS, W15, AUTRE = T1.q, T1.run, T1.NS, T1.W15, T1.AUTRE
AUTEUR = 'References - Claude'
TAB = '<w:r><w:tab/></w:r>'


def para(pid, x, style=None):
    st = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ''
    return f'<w:p w14:paraId="{pid}">{st}{x}</w:p>'


def ins(x, i): return f'<w:ins w:id="{i}" w:author="{AUTRE}" w:date="2026-10-01T00:00:00Z">{x}</w:ins>'


def entree(pid, n, texte, extra=''):
    return para(pid, run(f'[{n}]') + TAB + run(texte) + extra)


def docx(d, nom='rapport_v1.docx', corps_cit=None):
    corps_cit = corps_cit or (para('000000A1', run('Premier point [2] puis [1].'))
                              + para('000000A2', run('Suite ') + ins(run('ajout cité [3] '), 5) + run('et rappel [2].')))
    biblio = (para('000000B0', run('Références'), 'Heading1') + para('000000B9', run('Format IEEE.'))
              + entree('000000C1', 1, 'Auteur Un, Titre un.')
              + para('000000C2', '<w:commentRangeStart w:id="0"/>' + run('[2]') + TAB + run('Auteur Deux, Titre deux') + ins(run(', complété'), 6)
                     + run('.') + '<w:commentRangeEnd w:id="0"/><w:r><w:commentReference w:id="0"/></w:r>')
              + entree('000000C3', 3, 'Auteur Trois, Titre trois.') + entree('000000C4', 4, 'Auteur Quatre, Titre quatre.')
              + para('000000D1', run('Annexe A'), 'Heading1') + para('000000D2', run('Voir aussi [3].')))
    parts = {'word/document.xml': f'<w:document {NS}><w:body>{corps_cit}{biblio}</w:body></w:document>',
             'word/comments.xml': f'<w:comments {NS}><w:comment w:id="0" w:author="{AUTRE}" w:date="2026-10-01T00:00:00Z" w:initials="CA"><w:p w14:paraId="0000C001">{run("Vérifier.")}</w:p></w:comment></w:comments>',
             'word/commentsExtended.xml': f'<w15:commentsEx {W15}><w15:commentEx w15:paraId="0000C001" w15:done="0"/></w15:commentsEx>',
             'word/people.xml': f'<w15:people {W15}><w15:person w15:author="{AUTRE}"/></w15:people>', 'word/styles.xml': f'<w:styles {NS}/>'}
    f = os.path.join(d, nom)
    with zipfile.ZipFile(f, 'w') as z:
        for n, x in parts.items(): z.writestr(n, x)
    return f


def lire(f): return etree.fromstring(zipfile.ZipFile(f).read('word/document.xml'))


def vue(root):
    out = []
    for p in root.iter(q('p')):
        rp = p.find(q('pPr') + '/' + q('rPr'))
        if rp is not None and (rp.find(q('del')) is not None or rp.find(q('moveFrom')) is not None): continue
        out.append(''.join(('\t' if T1.ln(t) == 'tab' else (t.text or '')) for t in p.iter(q('t'), q('tab'))
                           if not any(T1.ln(a) in ('del', 'moveFrom') for a in t.iterancestors())))
    return out


def notices(lignes):
    """Pour chaque citation du texte (hors liste), le texte de la notice visée."""
    i = lignes.index('Références'); lst = {}
    for l in lignes[i + 1:]:
        m = re.match(r'\[(\d+)\]\t(.*)', l)
        if m: lst[int(m.group(1))] = m.group(2)
    corps = [l for l in lignes if not re.match(r'\[\d+\]\t', l)]
    return [lst[int(n)] for l in corps for n in re.findall(r'\[(\d+)\]', l)], [int(n) for n in lst]


class Renumerotation(unittest.TestCase):
    def faire(self, *extra, **k):
        d = dossier_essai('renumeroter_references_v3'); f = docx(d, **k); out = os.path.join(d, 'rapport_v2.docx')
        return f, out, RN.main([f, out, '--auteur', AUTEUR, *extra])

    def test_vue_acceptee(self):
        f, out, c = self.faire('--retirer', '4'); self.assertEqual(c, 0)
        A = lire(out); AC2.accepter(A, {a for (_, a) in AC2.auteurs_revisions(A)})
        L = vue(A)
        self.assertIn('Premier point [1] puis [2].', L); self.assertIn('Suite ajout cité [3] et rappel [1].', L); self.assertIn('Voir aussi [3].', L)
        av, _ = notices(vue_origine(f)); ap, ordre = notices(L)
        self.assertEqual(av, ap)                                                  # chaque citation vise la même notice
        self.assertEqual(ordre, [1, 2, 3]); self.assertNotIn('Auteur Quatre', ' '.join(L))

    def test_refus_et_revisions_des_autres(self):
        f, out, c = self.faire('--retirer', '4')
        R = lire(out); DC4.refuser(R, AUTEUR); self.assertEqual(DC4.couches(R), DC4.couches(lire(f)))
        A = lire(out); AC2.accepter(A, [AUTEUR])
        self.assertEqual(sum(v for (t, a), v in AC2.auteurs_revisions(A).items() if a == AUTRE), 2)

    def test_commentaire_et_identifiants(self):
        f, out, c = self.faire('--retirer', '4'); R = lire(out)
        e = list(R.iter(q('commentRangeStart'))); self.assertEqual(len(e), 1)
        p = next(e[0].iterancestors(q('p')))                                     # le commentaire reste sur la notice « Auteur Deux », hors source de déplacement
        self.assertIn('Auteur Deux', ''.join(t.text or '' for t in p.iter(q('t'), q('delText'))))
        self.assertIsNone(p.find(q('pPr') + '/' + q('rPr') + '/' + q('moveFrom')))
        ids = collections.Counter(x.get(q('id')) for t in ('ins', 'del', 'moveFrom', 'moveTo') for x in R.iter(q(t)) if x.get(q('id')))
        self.assertEqual([k for k, v in ids.items() if v > 1], [])

    def test_controle_du_suivi(self):
        import test_moteur_revision_multi_v4 as TM4
        f, out, c = self.faire('--retirer', '4'); self.assertEqual(c, 0)
        sauve = TM4.AUTEUR; TM4.AUTEUR = AUTEUR
        try: self.assertEqual(TM4.nouvelles(f, out), [])
        finally: TM4.AUTEUR = sauve

    def test_refus(self):
        self.assertEqual(self.faire('--retirer', '3')[2], 4)                     # liste discordante
        self.assertEqual(self.faire('--retirer', '4', corps_cit=para('000000A1', run('Plage [1–3].')))[2], 4)
        self.assertEqual(self.faire('--retirer', '4', corps_cit=para('000000A1', run('Absente [9].')))[2], 4)
        f, out, c = self.faire('--retirer', '4'); self.assertEqual(RN.main([f, out, '--auteur', AUTEUR, '--retirer', '4']), 3)
        self.assertEqual(RN.main([]), 2)


def vue_origine(f):
    R = lire(f); AC2.accepter(R, {a for (_, a) in AC2.auteurs_revisions(R)}); return vue(R)


if __name__ == '__main__':
    unittest.main()
