"""Tests de moteur_revision_multi_v4. (a) Non-régression : suite v3 rejouée sur la version 4 (et, par elle, v2 et v1). (b) Correction :
déplacement suivi d'un paragraphe portant des révisions d'un autre auteur, vers l'aval (copie après la source) et vers l'amont (copie avant
la source) :
- dans la source, le texte de leur insertion reste en w:t (aucun « delText dans w:ins ») ;
- la copie ne porte que notre marque moveTo et leurs révisions de contenu scindées : aucune ne reproduit exactement une révision d'origine ;
- contrôle du suivi du skill docx (appariement auteur, date, texte) : seules nos révisions, et ce qui est dans notre copie, sont « nouvelles »
  (témoin v3 : vers l'amont, leur révision de la source est tenue pour nouvelle) ;
- refuser nos révisions redonne l'origine ; tout accepter donne l'ordre et les textes attendus."""
import os, sys, unittest
import xml.etree.ElementTree as ET
from aide_tests_v2 import dossier_essai, importer_version
import test_moteur_revision_multi_v3 as T3

M4 = importer_version('moteur_revision_multi', 4, 'moteur_revision_multi_v4_essai')
sys.path.insert(0, '/mnt/skills/public/docx/scripts/office')
from validators.redlining import RedliningValidator   # noqa: E402
q, AUTEUR, AUTRE = T3.q, T3.AUTEUR, T3.AUTRE
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


class SurV4:
    @classmethod
    def setUpClass(cls):
        cls._s4 = (T3.M3, T3.T1.M, T3.T2.M2); T3.M3 = T3.T1.M = T3.T2.M2 = M4

    @classmethod
    def tearDownClass(cls): T3.M3, T3.T1.M, T3.T2.M2 = cls._s4


class DocRV1SurV4(SurV4, T3.DocRV1SurV3): pass
class CorrigeV2SurV4(SurV4, T3.CorrigeV2SurV3): pass
class DeplacementV3SurV4(SurV4, T3.Deplacement):
    def test_temoin_v2(self): pass                                    # témoin de la v3 (moteur v2), sans objet ici


def deplacer(M, vers_amont):
    d = dossier_essai('moteur_revision_multi_v4'); f = T3.docx_deplacement(d)
    D = M.DocR(f, author=AUTEUR, init='EC')
    if vers_amont: D.move_block('000000B2', '000000B2', '000000B1', 'avant')
    else: D.move_block('000000B2', '000000B2', '000000B3', 'apres')
    out = os.path.join(d, 'deplacement_v2.docx'); D.save(out); return f, out


def nouvelles(f, out):
    V = RedliningValidator.__new__(RedliningValidator); V.namespaces = {'w': W}
    import zipfile
    a = ET.fromstring(zipfile.ZipFile(f).read('word/document.xml')); b = ET.fromstring(zipfile.ZipFile(out).read('word/document.xml'))
    for r in (a, b): V._flatten_text_elements(r)
    parents = {c: p for p in b.iter() for c in p}
    def dans_notre_copie(e):
        x = e
        while x in parents:
            x = parents[x]
            if x.tag == '{%s}moveTo' % W and x.get('{%s}author' % W) == AUTEUR: return True
        return False
    return [e for e in V._new_tracked_changes(a, b) if e.get('{%s}author' % W) != AUTEUR and not dans_notre_copie(e)]


class Reconnaissable(unittest.TestCase):
    def test_source_sans_deltext_dans_ins(self):
        for amont in (False, True):
            f, out = deplacer(M4, amont); R = T3.lire(out)
            for e in R.iter(q('ins')):
                if T3.T1.ln(e.getparent()) == 'rPr': continue
                self.assertEqual(list(e.iter(q('delText'))), [], 'delText dans une insertion')

    def test_copie_marque_et_morceaux(self):
        for amont in (False, True):
            f, out = deplacer(M4, amont); R = T3.lire(out)
            dst = [p for p in R.iter(q('p')) if p.find(q('pPr') + '/' + q('rPr') + '/' + q('moveTo')) is not None][0]
            self.assertEqual([T3.T1.ln(m) for m in dst.find(q('pPr') + '/' + q('rPr'))], ['moveTo'])
            textes = sorted(''.join(t.text or '' for t in e.iter(q('t'), q('delText'))) for e in dst.iter(q('ins'), q('del')) if e.get(q('author')) == AUTRE)
            self.assertEqual(len(textes), 4); self.assertNotIn('ajout ', textes); self.assertNotIn('retrait ', textes)

    def test_controle_du_suivi(self):
        for amont in (False, True):
            f, out = deplacer(M4, amont); self.assertEqual(nouvelles(f, out), [], f'amont={amont}')

    def test_temoin_v3_vers_amont(self):
        f, out = deplacer(T3.M3 if T3.M3 is not M4 else importer_version('moteur_revision_multi', 3, 'moteur_v3_temoin'), True)
        self.assertTrue(nouvelles(f, out))

    def test_refus_et_acceptation(self):
        for amont in (False, True):
            f, out = deplacer(M4, amont)
            R = T3.lire(out); T3.DC4.refuser(R, AUTEUR); self.assertEqual(T3.DC4.couches(R), T3.DC4.couches(T3.lire(f)))
            A = T3.lire(out); T3.AC2.accepter(A, [AUTEUR, AUTRE])
            attendu = ['[2]\tBeta ajout ', '[1]\tAlpha', '[3]\tGamma', 'Fin'] if amont else ['[1]\tAlpha', '[3]\tGamma', '[2]\tBeta ajout ', 'Fin']
            self.assertEqual(T3.textes(A), attendu)


if __name__ == '__main__':
    unittest.main()
