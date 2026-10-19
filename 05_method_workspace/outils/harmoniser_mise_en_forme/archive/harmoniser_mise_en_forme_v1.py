"""
OUTIL: harmoniser_mise_en_forme
VERSION: 1
RESUME: Corrige en suivi des modifications, sous un auteur dédié, les écarts de mise en forme sans ambiguïté relevés par controler_mise_en_forme : H1 taille des passages du corps et des listes ramenée à la taille dominante de leur paragraphe (ou du corps du document), par une modification de mise en forme suivie (w:rPrChange : refuser redonne l'ancienne) ; H4 marque de paragraphe supprimée en suivi pour un paragraphe dont tout le texte est déjà supprimé en suivi (sinon une ligne vide reste après acceptation) ; H5 paragraphe vide retiré en suivi (marque supprimée), sauf entre deux tableaux, avant un tableau, ou porteur d'un saut de page, d'une section ou d'un signet. Ne touche ni la page de garde (tout ce qui précède la table des matières), ni le sommaire, ni les tableaux pour H1, ni le texte ; les résidus de Markdown (MF3) sont listés pour décision, jamais corrigés d'office. Contrôle intégré : relevé après correction, et aucun écart nouveau de l'auteur dédié.
USAGE: python3 outils/harmoniser_mise_en_forme.py <docx> <sortie.docx> [--auteur "Harmonisation - Claude"] [--regles H1,H4,H5] [--journal <journal.json>]
ENTREES: docx révisé en suivi (tous auteurs)
SORTIES: <sortie.docx> (jamais écrasé) ; journal JSON des corrections {regle, index, auteur_origine, texte, avant, apres} et des résidus à décider ; résumé ; événement dans journal/
CATEGORIE: revision_rapport
BANC: tests/test_harmoniser_mise_en_forme_v1.py
REMPLACE: -
"""
import sys, os, re, json, zipfile, datetime, collections
H = os.path.dirname(os.path.abspath(__file__)); O = H
while os.path.basename(O) != 'outils' and os.path.dirname(O) != O: O = os.path.dirname(O)
for p in (os.path.join(O, '_compat'), O):
    if p not in sys.path: sys.path.insert(0, p)
from lxml import etree                                       # noqa: E402
from cc_lib_v4 import evenement, chemin_outil                # noqa: E402

VERSION = 1; OUTIL = 'harmoniser_mise_en_forme'
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
# Ordre des propriétés d'un passage (CT_RPr) : sz et szCs se placent avant ces éléments.
APRES_SZ = ('highlight', 'u', 'effect', 'bdr', 'shd', 'fitText', 'vertAlign', 'rtl', 'cs', 'em', 'lang', 'eastAsianLayout', 'specVanish', 'oMath', 'rPrChange')
# Ordre de la marque de paragraphe (CT_ParaRPr) : ins, del, moveFrom, moveTo en tête.
APRES_RPR_PPR = ('sectPr', 'pPrChange')


def ln(e): return e.tag.split('}')[1] if isinstance(e.tag, str) else ''


def cmf():
    """Version courante de controler_mise_en_forme (ou son brouillon de candidat/ tant qu'il n'est pas adopté)."""
    try: f = chemin_outil('controler_mise_en_forme')
    except (SystemExit, ImportError):
        import glob
        f = sorted(glob.glob(os.path.join(O, 'controler_mise_en_forme', 'candidat', 'controler_mise_en_forme_v*.py')))[-1]
    import importlib.util
    s = importlib.util.spec_from_file_location('controler_mise_en_forme_courant', f); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


class Harmoniseur:
    def __init__(self, chemin, auteur):
        self.z = zipfile.ZipFile(chemin); self.doc = etree.fromstring(self.z.read('word/document.xml')); self.auteur = auteur
        tout = b''.join(self.z.read(n) for n in self.z.namelist() if n.endswith('.xml'))
        self.rev = max((int(x) for x in re.findall(rb'w:id="(-?\d+)"', tout)), default=0) + 1000
        self.date = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'); self.journal = []

    def suivi(self, tag):
        self.rev += 1; e = etree.Element(W + tag)
        e.set(W + 'id', str(self.rev)); e.set(W + 'author', self.auteur); e.set(W + 'date', self.date); return e

    def taille(self, r, val):
        """Fixe sz et szCs du passage r à val, en suivi (w:rPrChange avec les anciennes propriétés). Faux si une modification de mise en forme est déjà en suivi."""
        rp = r.find(W + 'rPr')
        if rp is None: rp = etree.Element(W + 'rPr'); r.insert(0, rp)
        if rp.find(W + 'rPrChange') is not None: return False
        ancien = etree.Element(W + 'rPr')
        for c in rp: ancien.append(etree.fromstring(etree.tostring(c)))
        for k in ('sz', 'szCs'):
            x = rp.find(W + k)
            if x is None:
                x = etree.Element(W + k); suivant = next((c for c in rp if ln(c) in APRES_SZ or (k == 'sz' and ln(c) == 'szCs')), None)
                (suivant.addprevious(x) if suivant is not None else rp.append(x))
            x.set(W + 'val', val)
        ch = self.suivi('rPrChange'); ch.append(ancien); rp.append(ch); return True

    def supprimer_marque(self, p):
        """Marque de paragraphe supprimée en suivi (le paragraphe disparaît à l'acceptation, le suivant garde sa mise en forme)."""
        ppr = p.find(W + 'pPr')
        if ppr is None: ppr = etree.Element(W + 'pPr'); p.insert(0, ppr)
        rp = ppr.find(W + 'rPr')
        if rp is None:
            rp = etree.Element(W + 'rPr'); suivant = next((c for c in ppr if ln(c) in APRES_RPR_PPR), None)
            (suivant.addprevious(rp) if suivant is not None else ppr.append(rp))
        if rp.find(W + 'del') is not None: return False
        d = self.suivi('del'); ins = rp.find(W + 'ins')
        (ins.addnext(d) if ins is not None else rp.insert(0, d)); return True

    def appliquer(self, regles, C):
        body = self.doc.find(W + 'body'); paras = list(body.iter(W + 'p'))
        R = C.releve_arbre(self.doc, self.z)
        par_index = collections.defaultdict(list)
        for e in R['ecarts']: par_index[e['index']].append(e)
        lim = R['profil']['debut_sommaire']; S = C.Styles(self.z); PT = C.profil_tailles(paras, lim, S); a_decider = []
        for i, E in sorted(par_index.items()):
            p = paras[i]; codes = {e['code'] for e in E}
            if 'MF3' in codes: a_decider += [dict(regle='MF3', index=i, auteur_origine=e['auteur'], texte=e['texte'], detail=e['detail']) for e in E if e['code'] == 'MF3']
            if 'H1' in regles and codes & {'MF1', 'MF2'}:
                st = C.pstyle(p); zn = C.zone(p, st); dom = C.dominante(p, st, S) or PT.get(zn)
                for r, t in list(C.runs_texte(p)):
                    v, expl = C.taille_run(r, st, S)
                    if dom and v != dom and self.taille(r, dom):
                        self.journal.append(dict(regle='H1', index=i, auteur_origine=C.auteur(r), texte=t.strip()[:60], avant=f'{int(v) / 2:g} pt', apres=f'{int(dom) / 2:g} pt'))
            if 'H4' in regles and 'MF4' in codes and self.supprimer_marque(p):
                self.journal.append(dict(regle='H4', index=i, auteur_origine=E[0]['auteur'], texte=E[0]['detail'][:60], avant='marque gardée', apres='marque supprimée'))
            if 'H5' in regles and 'MF5' in codes:
                suivant = p.getnext()
                if suivant is not None and ln(suivant) == 'tbl': continue          # paragraphe avant un tableau : gardé
                if self.supprimer_marque(p):
                    self.journal.append(dict(regle='H5', index=i, auteur_origine=E[0]['auteur'], texte='(paragraphe vide)', avant='présent', apres='retiré'))
        return a_decider

    def enregistrer(self, sortie):
        if os.path.exists(sortie): raise SystemExit(f'refus : {sortie} existe déjà (jamais d\'écrasement)')
        brut = etree.tostring(self.doc, xml_declaration=True, encoding='UTF-8', standalone=True)
        with zipfile.ZipFile(sortie, 'w', zipfile.ZIP_DEFLATED) as zo:
            for it in self.z.infolist():
                zo.writestr(it, brut if it.filename == 'word/document.xml' else self.z.read(it.filename))


def opt(a, k, d=None): return a[a.index(k) + 1] if k in a and a.index(k) + 1 < len(a) else d


USAGE = __doc__.split('USAGE:')[1].split('ENTREES:')[0].strip()


def main(a=None):
    a = sys.argv[1:] if a is None else a
    if len(a) < 2 or a[0].startswith('--'): print(USAGE); return 2
    src, out = a[0], a[1]; auteur = opt(a, '--auteur', 'Harmonisation - Claude'); regles = set((opt(a, '--regles', 'H1,H4,H5')).split(','))
    C = cmf(); h = Harmoniseur(src, auteur); a_decider = h.appliquer(regles, C); h.enregistrer(out)
    apres = C.releve(out); comp = C.comparer(src, out, auteur)
    cpt = collections.Counter(j['regle'] for j in h.journal)
    print(f"{sum(cpt.values())} correction(s) en suivi sous « {auteur} » : " + ', '.join(f'{k} {v}' for k, v in sorted(cpt.items())))
    print(f"écarts restants : {len(apres['ecarts'])} ({', '.join(f'{k} {v}' for k, v in apres['compte'].items())}) ; nouveaux écarts de « {auteur} » : {len(comp['vises'])}")
    if a_decider: print(f'{len(a_decider)} résidu(s) de Markdown à décider (non corrigés) : ' + ' ; '.join(f"¶{x['index']} « {x['texte'][:40]} »" for x in a_decider))
    j = opt(a, '--journal')
    if j:
        with open(j, 'w', encoding='utf-8') as g: json.dump(dict(source=os.path.basename(src), sortie=os.path.basename(out), auteur=auteur, corrections=h.journal, a_decider=a_decider,
                                                                 restants=apres['compte'], nouveaux_auteur=len(comp['vises'])), g, ensure_ascii=False, indent=1)
    evenement(OUTIL, VERSION, 'harmoniser', dict(corrections=len(h.journal), H1=cpt.get('H1', 0), H4=cpt.get('H4', 0), H5=cpt.get('H5', 0), a_decider=len(a_decider),
                                                verdict='conforme' if not comp['vises'] else 'non conforme'))
    return 0 if not comp['vises'] else 1


if __name__ == '__main__':
    sys.exit(main())
