"""Tests de livrer_v7. (a) Non-régression : toute la suite de livrer_v6 (qui reprend celles des v4 et v5) est rejouée sur la v7.
(b) Correction de la v7 (18 oct. 2026) : une version de livrable en « -revN » (règle propre au rapport, décision de l'utilisateur :
source v6.0.12-rev1 → livrable v6.0.13-rev1) était refusée par la v6, dont le contrôle de relecture du nom ne comparait que la partie
numérique (« 6.0.13 » ≠ « 6.0.13-rev1 »). Le défaut est d'abord prouvé présent sur la v6 (LC-032)."""
import os, sys, json, subprocess, unittest
from aide_tests_v2 import chemin_version
import test_livrer_v6 as T6

LIVRER7 = chemin_version('livrer', 7); LIVRER6 = chemin_version('livrer', 6)
T6.LIVRER = LIVRER7                       # les classes de la v6 lancent désormais la v7

PorteDocxV7, FicheTravailV7, NomAvecPointV7, TexteV7 = T6.PorteDocx, T6.FicheTravail, T6.NomAvecPoint, T6.Texte
try:
    from test_livrer_v6 import *          # noqa: F401,F403  (autres classes éventuelles de la suite v6)
except Exception:
    pass


def dossier_rev(nom):
    d = T6.dossier(nom)
    T = json.load(open(os.path.join(d, 'TRAVAIL_v1.json'), encoding='utf-8'))
    T2 = dict(T, version_cible='6.0.13-rev1', decision_version=dict(valeur='6.0.13-rev1', approuvee_par='utilisateur', portee='essai : règle propre au rapport',
                                                                   citations=['« source v6.0.12-rev1 → livrables v6.0.13-rev1 »']))
    T6.CAS._ecrire(d, 'TRAVAIL_v2.json', json.dumps(T2))
    return d


class VersionRev(unittest.TestCase):
    def test_defaut_present_en_v6(self):
        d = dossier_rev('livrer7_rev_v6')
        r = subprocess.run([sys.executable, LIVRER6, d, os.path.join(d, '01_etape', 'resultat_v1.md') + ':Note', '--sans-evaluation'],
                           capture_output=True, text=True, timeout=600)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr); self.assertIn('ne se relit pas', r.stdout + r.stderr); self.assertEqual(T6.remis(d), [])

    def test_version_rev_remise(self):
        d = dossier_rev('livrer7_rev')
        c, s = T6.lancer(d, os.path.join(d, '01_etape', 'resultat_v1.md') + ':Note', '--sans-evaluation')
        self.assertEqual(c, 0, s); self.assertEqual(T6.remis(d), ['Note_v6.0.13-rev1.md', 'empreintes_livrables_v6.0.13-rev1.txt'])

    def test_nom_mal_relu_toujours_refuse(self):
        # variante « v2 » : « Note_v6.0.13-rev1_v2.md » se relirait en (Note_v6.0.13-rev1, 2) : refus attendu
        d = dossier_rev('livrer7_rev_invalide')
        c, s = T6.lancer(d, os.path.join(d, '01_etape', 'resultat_v1.md') + ':Note:v2', '--sans-evaluation')
        self.assertNotEqual(c, 0, s); self.assertEqual(T6.remis(d), [])


if __name__ == '__main__':
    unittest.main()
