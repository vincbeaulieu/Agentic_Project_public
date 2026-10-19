"""Tests de harmoniser_mise_en_forme_v2 (docx synthétiques de test_controler_mise_en_forme_v2). Vérifié :
- H1 taille corrigée en suivi (w:rPrChange garde l'ancienne, en dernier dans w:rPr) ; passage déjà modifié en suivi par un autre auteur : listé, intact ;
- H4 / H5 marque supprimée en suivi (w:del dans la marque, après w:ins) ; vide avant un titre : retiré ET aligné sur le titre (w:pPrChange en
  dernier dans w:pPr) ; jamais avant un tableau (même supprimé), ni en fin de cellule, ni sur la page de garde ;
- H5 bloqué si un paragraphe absorbé est déjà modifié en suivi par un autre auteur (listé, marque gardée) ;
- H7 fragment résiduel supprimé en suivi puis la ligne vide retirée ; en tableau : listé ;
- H8 fusion préexistante alignée ; vue acceptée : le titre reste un titre ;
- H9 jamais par défaut (MF9 listé) ; sur décision : rangées supprimées en suivi ;
- contrôle intégré : aucun écart nouveau de l'auteur dédié ; deuxième passage sans correction (idempotence) ; journal sans nom ;
- jamais d'écrasement (code 3) ; ligne de commande sans argument : 2 ;
- confrontation à une acceptation réelle (LibreOffice, si présent) : le titre garde son style, plus aucune ligne vide ; témoin sans H8 :
  le titre perd son style (le test détecte le défaut) et le contrôle intégré rend le code 1."""
import os, sys, json, glob, shutil, zipfile, subprocess, unittest
from lxml import etree
from aide_tests_v2 import dossier_essai, chemin_version, importer_version
import test_controler_mise_en_forme_v2 as T

OUTIL = chemin_version('harmoniser_mise_en_forme', 2)
HM = importer_version('harmoniser_mise_en_forme', 2)
C = T.C
W = C.W
p, run, ins, dele, tbl, docx = T.p, T.run, T.ins, T.dele, T.tbl, T.docx
AUT = 'Harmonisation - Claude'
SOFFICE = shutil.which('soffice') or shutil.which('libreoffice')
ACCEPTER = '/mnt/skills/public/docx/scripts/accept_changes.py'


def ln(e): return C.ln(e)


def lire(f):
    with open(f, encoding='utf-8') as g: return json.load(g)


class Base(unittest.TestCase):
    def harmoniser(self, corps, regles=HM.REGLES, nom='h'):
        self.d = dossier_essai(f'harmoniser_mise_en_forme_v2_{nom}'); self.src = docx(self.d, 'doc_v1.docx', corps)
        self.out = os.path.join(self.d, 'doc_v2.docx'); self.journal = os.path.join(self.d, 'journal_v1.json')
        code = HM.main([self.src, self.out, '--regles', regles, '--journal', self.journal])
        self.J = lire(self.journal)
        self.doc = etree.fromstring(zipfile.ZipFile(self.out).read('word/document.xml'))
        self.P = list(self.doc.find(W + 'body').iter(W + 'p')); return code

    def para(self, texte):
        return next(q for q in self.P if texte in (C.texte_visible(q) + C.texte_supprime(q)))

    def regles(self): return sorted(j['regle'] for j in self.J['corrections'])


class Passages(Base):
    def test_h1_taille_en_suivi(self):
        self.assertEqual(self.harmoniser(p(run('Texte de base à onze points ') + ins('ajout sans taille'))), 0)
        self.assertEqual(self.regles(), ['H1'])
        r = next(r for r in self.para('ajout').iter(W + 'r') if 'ajout' in ''.join(t.text or '' for t in r.iter(W + 't')))
        rp = r.find(W + 'rPr'); self.assertEqual(rp.find(W + 'sz').get(W + 'val'), '22'); self.assertEqual(ln(rp[-1]), 'rPrChange')
        self.assertIsNone(rp[-1].find(f'{W}rPr/{W}sz'))                                         # refuser redonne l'ancienne (sans taille)

    def test_h1_deja_modifie_liste(self):
        autre = f'<w:rPrChange w:id="900" {T.a("Collègue A")}><w:rPr><w:b/></w:rPr></w:rPrChange>'
        corps = p(run('Texte de base à onze points ') + f'<w:r><w:rPr>{autre}</w:rPr><w:t>sans taille</w:t></w:r>')
        self.harmoniser(corps); self.assertEqual(self.regles(), []); self.assertEqual([x['regle'] for x in self.J['a_decider']], ['H1'])


class Lignes(Base):
    def test_h5_vide_entre_deux_paragraphes(self):
        self.harmoniser(p(run('Avant.')) + p() + p(run('Après.'))); self.assertEqual(self.regles(), ['H5'])
        vide = [q for q in self.P if not C.texte_visible(q).strip() and C.marque_supprimee(q)]
        self.assertEqual(len(vide), 1); rp = vide[0].find(f'{W}pPr/{W}rPr'); self.assertEqual(rp.find(W + 'del').get(W + 'author'), AUT)

    def test_h5_vide_avant_titre_aligne(self):
        self.harmoniser(p(run('Avant.')) + p() + p(run('1 Contexte', None), 'Heading1'))
        self.assertEqual(self.regles(), ['H5', 'H8'])
        vide = next(q for q in self.P if C.marque_supprimee(q)); ppr = vide.find(W + 'pPr')
        self.assertEqual(C.pstyle(vide), 'Heading1'); self.assertEqual(ln(ppr[-1]), 'pPrChange'); self.assertIsNone(ppr[-1].find(f'{W}pPr/{W}pStyle'))
        self.assertEqual(C.releve(self.out)['ecarts'], [])

    def test_jamais_avant_tableau_en_cellule_ni_garde(self):
        self.harmoniser(p() + tbl([p(run('x')) + p()]) + p(run('Suite.')) + p() + tbl([p(run('y'))], supprimees=True) + p(run('Fin.')))
        self.assertEqual(self.regles(), [])
        garde = self.P[1]; self.assertFalse(C.marque_supprimee(garde))

    def test_h4_ligne_vide(self):
        self.harmoniser(p(run('Avant.')) + p(dele('Phrase entièrement supprimée.')) + p(run('Après.'))); self.assertEqual(self.regles(), ['H4'])

    def test_h4_bloque_par_une_modification_d_un_autre_auteur(self):
        chg = f'<w:jc w:val="center"/><w:pPrChange w:id="901" {T.a("Collègue A")}><w:pPr/></w:pPrChange>'
        self.harmoniser(p(run('Avant.')) + p(dele('Phrase supprimée.'), ppr_extra=chg) + p(run('1 Titre', None), 'Heading1'))
        self.assertEqual(self.regles(), []); self.assertEqual([x['regle'] for x in self.J['a_decider']], ['MF4'])
        self.assertFalse(C.marque_supprimee(self.para('Phrase supprimée.')))


class Fragments(Base):
    def test_h7_puis_h4(self):
        self.harmoniser(p(run('Avant.')) + p(dele('5.7 Mise en œuvre') + run('24')) + p(run('Après.')))
        self.assertEqual(self.regles(), ['H4', 'H7'])
        q = self.para('24'); self.assertEqual(C.texte_visible(q), ''); self.assertTrue(C.marque_supprimee(q))
        self.assertNotIn('24', C.textes_acceptes(self.out))

    def test_h7_en_tableau_liste(self):
        self.harmoniser(tbl([p(run('Cause')) + p(dele('5.7 Mise en œuvre de la règle') + run('24'))]) + p(run('Suite.')))
        self.assertNotIn('H7', self.regles()); self.assertIn('MF7', [x['regle'] for x in self.J['a_decider']])


class Fusions(Base):
    def test_h8_titre_garde_son_style(self):
        self.harmoniser(p(run('Avant.')) + p(dele('Paragraphe supprimé.'), marque_sup='Collègue A') + p(run('1 Objet', None), 'Heading1'))
        self.assertEqual(self.regles(), ['H8'])
        absorbe = self.para('Paragraphe supprimé.'); self.assertEqual(C.pstyle(absorbe), 'Heading1')
        self.assertEqual(C.signature(absorbe), C.signature(self.para('1 Objet')))
        self.assertNotIn('Collègue A', json.dumps(self.J['a_decider']))

    def test_idempotence(self):
        corps = (p(run('Avant.')) + p() + p(run('1 Contexte', None), 'Heading1') + p(dele('5.7 Mise en œuvre') + run('24')) + p(run('Corps ') + ins('ajout'))
                 + p(dele('Paragraphe supprimé.'), marque_sup='Collègue A') + p(run('2 Méthode', None), 'Heading1'))
        self.harmoniser(corps); self.assertTrue(self.regles())
        sortie2 = os.path.join(self.d, 'doc_v3.docx'); j2 = os.path.join(self.d, 'journal_v2.json')
        self.assertEqual(HM.main([self.out, sortie2, '--journal', j2]), 0)
        self.assertEqual(lire(j2)['corrections'], [])


class Tableaux(Base):
    VIDE = tbl([p(run('Cause')), p(dele('Une longue explication supprimée en suivi dans la cellule.'))]) + p(run('Suite.'))

    def test_h9_jamais_par_defaut(self):
        self.harmoniser(self.VIDE); self.assertEqual(self.regles(), []); self.assertIn('MF9', [x['regle'] for x in self.J['a_decider']])

    def test_h9_sur_decision(self):
        self.harmoniser(self.VIDE, regles=HM.REGLES + ',H9'); self.assertEqual(self.regles(), ['H9'])
        trs = list(self.doc.iter(W + 'tr')); self.assertTrue(all(tr.find(f'{W}trPr/{W}del') is not None for tr in trs))
        self.assertNotIn('Cause', C.textes_acceptes(self.out))


class Fichiers(Base):
    def test_jamais_d_ecrasement(self):
        self.harmoniser(p(run('Avant.')) + p() + p(run('Après.')))
        self.assertEqual(HM.main([self.src, self.out]), 3)

    def test_sans_argument(self):
        r = subprocess.run([sys.executable, OUTIL], capture_output=True, text=True); self.assertEqual(r.returncode, 2)


@unittest.skipUnless(SOFFICE and os.path.exists(ACCEPTER), 'LibreOffice ou accept_changes.py absent')
class AcceptationReelle(Base):
    def test_titre_et_lignes_apres_acceptation(self):
        corps = (p(run('Avant.')) + p() + p(run('1 Contexte', None), 'Heading1') + p(run('Corps du chapitre.'))
                 + p(dele('Paragraphe supprimé.'), marque_sup='Collègue A') + p(run('2 Méthode', None), 'Heading1') + p(run('Fin.')))
        self.harmoniser(corps, nom='acceptation')
        acc = os.path.join(self.d, 'accepte_v1.docx')
        r = subprocess.run([sys.executable, ACCEPTER, self.out, acc], capture_output=True, text=True, timeout=300); self.assertEqual(r.returncode, 0, r.stderr)
        d = etree.fromstring(zipfile.ZipFile(acc).read('word/document.xml'))
        vus = [(C.pstyle(q), ''.join(t.text or '' for t in q.iter(W + 't'))) for q in d.find(W + 'body').iter(W + 'p')]
        corps_vus = vus[vus.index(next(v for v in vus if v[1] == 'Avant.')):]
        self.assertEqual([v[1] for v in corps_vus], ['Avant.', '1 Contexte', 'Corps du chapitre.', '2 Méthode', 'Fin.'])
        self.assertEqual(dict((t, s) for s, t in corps_vus)['1 Contexte'], 'Heading1'); self.assertEqual(dict((t, s) for s, t in corps_vus)['2 Méthode'], 'Heading1')

    def test_temoin_sans_h8(self):
        """Témoin : sans H8, l'acceptation réelle fait perdre son style au titre qui absorbe un paragraphe supprimé (le test ci-dessus détecte donc bien le défaut),
        et le contrôle intégré signale la fusion créée par H5 (code 1)."""
        corps = (p(run('Avant.')) + p() + p(run('1 Contexte', None), 'Heading1') + p(run('Corps du chapitre.'))
                 + p(dele('Paragraphe supprimé.'), marque_sup='Collègue A') + p(run('2 Méthode', None), 'Heading1') + p(run('Fin.')))
        self.assertEqual(self.harmoniser(corps, regles='H1,H4,H5,H7', nom='temoin'), 1)
        acc = os.path.join(self.d, 'accepte_v1.docx')
        subprocess.run([sys.executable, ACCEPTER, self.out, acc], capture_output=True, text=True, timeout=300)
        d = etree.fromstring(zipfile.ZipFile(acc).read('word/document.xml'))
        styles = {''.join(t.text or '' for t in q.iter(W + 't')): C.pstyle(q) for q in d.find(W + 'body').iter(W + 'p')}
        self.assertNotEqual(styles['2 Méthode'], 'Heading1')


if __name__ == '__main__':
    unittest.main()
