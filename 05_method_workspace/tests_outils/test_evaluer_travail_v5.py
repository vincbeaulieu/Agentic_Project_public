"""v5 de la suite (dossiers par le registre des chemins). Tests de evaluer_travail_v5 (N3) et de livrer_v3 : version des livrables = version attendue — convention générale
v(X+1).0.0 d'après la source, ou règle propre au document consignée dans TRAVAIL (decision_version approuvée par
l'utilisateur) ; noms à qualificatif « -revN » reconnus (ni N1 ni N4) ; livrer refuse une version_cible hors convention."""
import os, sys, json, shutil, subprocess, unittest, importlib.util
from aide_tests_v2 import dossier_essai, chemin_version, RACINE_CC, chemin

spec = importlib.util.spec_from_file_location('cas_evaluer', chemin('bancs', 'evaluer_travail', 'cas_v1.py'))
CAS = importlib.util.module_from_spec(spec); spec.loader.exec_module(CAS)
EVAL, LIVRER = chemin_version('evaluer_travail', 5), chemin_version('livrer', 3)
OUT = os.path.join(RACINE_CC, 'outils')


def lancer(*a):
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(OUT, '_compat'), OUT]))
    r = subprocess.run([sys.executable] + list(a), capture_output=True, text=True, env=env); return r.returncode, r.stdout + r.stderr


def constats(d):
    j = os.path.join(os.path.dirname(d), os.path.basename(d) + '_constats.json')
    c, s = lancer(EVAL, d, '--sans-xsd', '--sans-manifeste', '--json', j)
    with open(j, encoding='utf-8') as g: return {(k['regle'], k['chemin']) for k in json.load(g)['constats']}, s


def travail(d, **k):
    T = dict(sujet='essai', source='00_sources/doc_v1.txt', auteur_revisions='Reevaluation - Claude', version_cible='2.0.0', couverture=None, auteurs_relecteurs=[])
    T.update(k); CAS._ecrire(d, 'TRAVAIL_v2.json', json.dumps(T))


def rev(base, nom, decision):
    """Dossier dont la source est doc_v6.0.4-rev1.docx et les livrables v6.0.5-rev1."""
    d = os.path.join(base, nom)
    CAS._ecrire(d, 'LISEZMOI_v1.md', '# Essai\n'); CAS._ecrire(d, '00_sources/doc_v6.0.4-rev1.docx', 'source\n', ro=True)
    CAS._ecrire(d, '00_sources/sha256_sources_v1.txt', f'{CAS._sha("source" + chr(10))}  00_sources/doc_v6.0.4-rev1.docx\n', ro=True)
    CAS._ecrire(d, '95_journal/audit_v1.md', 'a\n'); CAS._ecrire(d, '01_etape/brouillon_v6.0.5-rev1.md', 'b\n')
    CAS._ecrire(d, '98_livrables/Rapport_v6.0.5-rev1.md', 'final\n', ro=True)
    CAS._ecrire(d, '98_livrables/empreintes_livrables_v6.0.5-rev1.txt', f'{CAS._sha("final" + chr(10))[:16]} Rapport_v6.0.5-rev1.md\n')
    CAS._ecrire(d, '99_livrables_modifiables/Rapport_v6.0.5-rev1.md', 'final\n')
    T = dict(sujet='essai', source='00_sources/doc_v6.0.4-rev1.docx', auteur_revisions='Reevaluation - Claude', version_cible='6.0.5-rev1', couverture=None, auteurs_relecteurs=[])
    if decision: T['decision_version'] = dict(valeur='6.0.5-rev1', approuvee_par='utilisateur', portee='document')
    CAS._ecrire(d, 'TRAVAIL_v1.json', json.dumps(T)); return d


class N3(unittest.TestCase):
    def test_conforme_convention_generale(self):
        K, s = constats(CAS._conforme(dossier_essai('eval4_conforme'))); self.assertEqual(K, set(), s)

    def test_version_cible_hors_convention(self):
        d = CAS._conforme(dossier_essai('eval4_hors')); travail(d, version_cible='9.0.0')
        K, s = constats(d); self.assertIn(('N3', 'TRAVAIL_v2.json'), K, s)
        self.assertIn(('N3', '98_livrables/Rapport_v2.0.0.md'), K)                 # livrable ≠ version_cible

    def test_regle_du_document(self):
        K, s = constats(rev(dossier_essai('eval4_rev'), '11_essai_rev', True)); self.assertEqual(K, set(), s)
        K, s = constats(rev(dossier_essai('eval4_rev_sans'), '11_essai_rev', False))
        self.assertEqual(K, {('N3', 'TRAVAIL_v1.json')}, s)                        # sans décision : convention v7.0.0


class Livrer(unittest.TestCase):
    def dossier(self, nom, decision):
        d = rev(dossier_essai(nom), '11_essai_livrer', decision)
        for s in ('98_livrables', '99_livrables_modifiables'):
            for f in os.listdir(os.path.join(d, s)): os.chmod(os.path.join(d, s, f), 0o644); os.remove(os.path.join(d, s, f))
        CAS._ecrire(d, '01_etape/resultat_v1.md', 'résultat\n'); return d

    def test_remise_avec_decision(self):
        d = self.dossier('livrer3_ok', True)
        c, s = lancer(LIVRER, d, os.path.join(d, '01_etape', 'resultat_v1.md') + ':Rapport', '--sans-evaluation'); self.assertEqual(c, 0, s)
        self.assertEqual(sorted(os.listdir(os.path.join(d, '98_livrables'))), ['Rapport_v6.0.5-rev1.md', 'empreintes_livrables_v6.0.5-rev1.txt'])
        c, s = lancer(LIVRER, d, os.path.join(d, '01_etape', 'resultat_v1.md') + ':Rapport', '--sans-evaluation'); self.assertNotEqual(c, 0)   # jamais d'écrasement

    def test_refus_hors_convention(self):
        d = self.dossier('livrer3_refus', False)
        c, s = lancer(LIVRER, d, os.path.join(d, '01_etape', 'resultat_v1.md') + ':Rapport', '--sans-evaluation')
        self.assertNotEqual(c, 0); self.assertIn('7.0.0', s); self.assertEqual(os.listdir(os.path.join(d, '98_livrables')), [])


if __name__ == '__main__':
    unittest.main()
