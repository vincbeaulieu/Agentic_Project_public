"""
OUTIL: harmoniser_mise_en_forme
VERSION: 2
RESUME: Corrige en suivi des modifications, sous un auteur dédié, les écarts de mise en forme sans ambiguïté relevés par controler_mise_en_forme (v2, vue acceptée) : H1 taille des passages du corps et des listes ramenée à la taille dominante de leur paragraphe (w:rPrChange : refuser redonne l'ancienne) ; H7 fragment résiduel d'une suppression (« 12 », « 3.2 », « xyz. ») supprimé en suivi, hors tableaux ; H4 ligne vide laissée par une suppression et H5 paragraphe vide inutile retirés en suivi (marque de paragraphe supprimée), sauf en fin de conteneur ou avant un tableau ; H8 fusion à l'acceptation rendue indépendante du logiciel : chaque paragraphe absorbé reçoit, en suivi (w:pPrChange), les propriétés du paragraphe qui reste (un titre reste un titre, que Word garde les propriétés du premier ou du dernier paragraphe fusionné). H4/H5 ne retirent un paragraphe que si l'alignement H8 qu'il entraîne est possible. Sur décision seulement (--regles …,H9) : H9 tableau vidé par des suppressions en suivi (rangées gardées) supprimé en suivi, rangée par rangée. Ne touche ni la page de garde, ni le sommaire ; un passage ou un paragraphe déjà modifié en suivi par un autre auteur est listé, jamais modifié ; les résidus de Markdown (MF3) et les fragments en tableau sont listés pour décision. Contrôle intégré : relevé après correction et aucun écart nouveau de l'auteur dédié.
USAGE: python3 outils/harmoniser_mise_en_forme.py <docx> <sortie.docx> [--auteur "Harmonisation - Claude"] [--regles H1,H4,H5,H7,H8[,H9]] [--journal <journal.json>]
ENTREES: docx révisé en suivi (tous auteurs)
SORTIES: <sortie.docx> (jamais écrasé) ; journal JSON des corrections {regle, index, auteur_origine, texte, avant, apres} et des cas à décider (auteurs anonymisés) ; résumé ; événement dans journal/
CATEGORIE: revision_rapport
BANC: tests/test_harmoniser_mise_en_forme_v2.py
REMPLACE: harmoniser_mise_en_forme_v1 (H5 retirait un paragraphe vide sans voir que des paragraphes précédents à marque supprimée s'y fondaient : « 3.2 » d'un ancien sommaire se collait au titre « 4 Titre de section » ; un paragraphe vide retiré avant un titre pouvait faire perdre au titre son style selon le logiciel ; trouvé par la confrontation à une acceptation réelle)
"""
import sys, os, re, json, zipfile, datetime, collections, copy
H = os.path.dirname(os.path.abspath(__file__)); O = H
while os.path.basename(O) != 'outils' and os.path.dirname(O) != O: O = os.path.dirname(O)
for p in (os.path.join(O, '_compat'), O):
    if p not in sys.path: sys.path.insert(0, p)
from lxml import etree                                       # noqa: E402
from cc_lib_v4 import evenement, chemin_outil                # noqa: E402

VERSION = 2; OUTIL = 'harmoniser_mise_en_forme'; VERSION_CONTROLE = 2
# H9 (tableau vidé : rangées supprimées en suivi) change le contenu : jamais par défaut, seulement sur décision (--regles …,H9).
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
# Ordre des propriétés d'un passage (CT_RPr) : sz et szCs se placent avant ces éléments.
APRES_SZ = ('highlight', 'u', 'effect', 'bdr', 'shd', 'fitText', 'vertAlign', 'rtl', 'cs', 'em', 'lang', 'eastAsianLayout', 'specVanish', 'oMath', 'rPrChange')
# Ordre de la marque de paragraphe (CT_ParaRPr) : ins, del, moveFrom, moveTo en tête.
APRES_RPR_PPR = ('sectPr', 'pPrChange')
HORS_BASE = ('rPr', 'sectPr', 'pPrChange')                  # tout le reste de w:pPr est CT_PPrBase (copié et enregistré dans w:pPrChange)
REGLES = 'H1,H4,H5,H7,H8'


def ln(e): return e.tag.split('}')[1] if isinstance(e.tag, str) else ''


def cmf():
    """controler_mise_en_forme v2 : version adoptée, sinon son brouillon de candidat/."""
    try: f = chemin_outil('controler_mise_en_forme', VERSION_CONTROLE)
    except (SystemExit, ImportError, TypeError):
        f = os.path.join(O, 'controler_mise_en_forme', 'candidat', f'controler_mise_en_forme_v{VERSION_CONTROLE}.py')
    import importlib.util
    s = importlib.util.spec_from_file_location('controler_mise_en_forme_courant', f); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


class Harmoniseur:
    def __init__(self, chemin, auteur):
        self.z = zipfile.ZipFile(chemin); self.doc = etree.fromstring(self.z.read('word/document.xml')); self.auteur = auteur
        tout = b''.join(self.z.read(n) for n in self.z.namelist() if n.endswith('.xml'))
        self.rev = max((int(x) for x in re.findall(rb'w:id="(-?\d+)"', tout)), default=0) + 1000
        self.date = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'); self.journal = []; self.a_decider = []

    def suivi(self, tag):
        self.rev += 1; e = etree.Element(W + tag)
        e.set(W + 'id', str(self.rev)); e.set(W + 'author', self.auteur); e.set(W + 'date', self.date); return e

    def taille(self, r, val):
        """Fixe sz et szCs du passage r à val, en suivi (w:rPrChange avec les anciennes propriétés). Faux si une modification de mise en forme est déjà en suivi."""
        rp = r.find(W + 'rPr')
        if rp is None: rp = etree.Element(W + 'rPr'); r.insert(0, rp)
        if rp.find(W + 'rPrChange') is not None: return False
        ancien = etree.Element(W + 'rPr')
        for c in rp: ancien.append(copy.deepcopy(c))
        for k in ('sz', 'szCs'):
            x = rp.find(W + k)
            if x is None:
                x = etree.Element(W + k); suivant = next((c for c in rp if ln(c) in APRES_SZ or (k == 'sz' and ln(c) == 'szCs')), None)
                (suivant.addprevious(x) if suivant is not None else rp.append(x))
            x.set(W + 'val', val)
        ch = self.suivi('rPrChange'); ch.append(ancien); rp.append(ch); return True

    def supprimer_marque(self, p):
        """Marque de paragraphe supprimée en suivi (le paragraphe se fond dans le suivant à l'acceptation)."""
        ppr = p.find(W + 'pPr')
        if ppr is None: ppr = etree.Element(W + 'pPr'); p.insert(0, ppr)
        rp = ppr.find(W + 'rPr')
        if rp is None:
            rp = etree.Element(W + 'rPr'); suivant = next((c for c in ppr if ln(c) in APRES_RPR_PPR), None)
            (suivant.addprevious(rp) if suivant is not None else ppr.append(rp))
        if rp.find(W + 'del') is not None or rp.find(W + 'moveFrom') is not None: return False
        d = self.suivi('del'); ins = rp.find(W + 'ins')
        (ins.addnext(d) if ins is not None else rp.insert(0, d)); return True

    @staticmethod
    def alignable(p):
        ppr = p.find(W + 'pPr')
        return ppr is None or (ppr.find(W + 'pPrChange') is None and ppr.find(W + 'sectPr') is None)

    def aligner(self, p, porteur, C):
        """Donne à p (paragraphe absorbé à l'acceptation) les propriétés de paragraphe du porteur, en suivi (w:pPrChange)."""
        if C.signature(p) == C.signature(porteur) or not self.alignable(p): return False
        ppr = p.find(W + 'pPr')
        if ppr is None: ppr = etree.Element(W + 'pPr'); p.insert(0, ppr)
        ancien = etree.Element(W + 'pPr')
        for c in list(ppr):
            if ln(c) not in HORS_BASE: ancien.append(copy.deepcopy(c)); ppr.remove(c)
        src = porteur.find(W + 'pPr')
        nouveaux = [copy.deepcopy(c) for c in (src if src is not None else []) if isinstance(c.tag, str) and ln(c) not in HORS_BASE]
        for k, c in enumerate(nouveaux): ppr.insert(k, c)
        ch = self.suivi('pPrChange'); ch.append(ancien); ppr.append(ch); return True

    def supprimer_texte(self, p, C):
        """Supprime en suivi les passages encore visibles de p (fragment résiduel d'une suppression)."""
        n = 0
        for r in list(p.iter(W + 'r')):
            if C.dans(r, 'del', 'moveFrom', 'ins', 'moveTo') or r.getparent() is None: continue
            if not any(ln(c) in ('t', 'tab', 'instrText') for c in r): continue
            for c in r:
                if ln(c) == 't': c.tag = W + 'delText'
                elif ln(c) == 'instrText': c.tag = W + 'delInstrText'
            d = self.suivi('del'); r.addprevious(d); d.append(r); n += 1
        return n

    def supprimer_rangees(self, tb, C):
        """Supprime en suivi toutes les rangées d'un tableau (w:trPr/w:del), le texte restant et les marques de paragraphe des cellules."""
        n = 0
        for tr in tb.findall(W + 'tr'):
            tp = tr.find(W + 'trPr')
            if tp is None:
                tp = etree.Element(W + 'trPr'); ex = tr.find(W + 'tblPrEx'); (ex.addnext(tp) if ex is not None else tr.insert(0, tp))
            if tp.find(W + 'del') is not None: continue
            d = self.suivi('del'); ch = tp.find(W + 'trPrChange'); (ch.addprevious(d) if ch is not None else tp.append(d))
            for p in tr.iter(W + 'p'): self.supprimer_texte(p, C); self.supprimer_marque(p)
            n += 1
        return n

    def noter(self, regle, index, origine, texte, avant, apres, C):
        self.journal.append(dict(regle=regle, index=index, auteur_origine=C.anonyme_auteur(origine), texte=C.anonyme_texte(texte)[:60], avant=avant, apres=apres))

    def decider(self, regle, index, texte, detail, C, origine=None):
        self.a_decider.append(dict(regle=regle, index=index, auteur_origine=C.anonyme_auteur(origine) if origine else None, texte=C.anonyme_texte(texte)[:60], detail=detail))

    def porteur_de(self, n, paras, pos, C):
        """Paragraphe qui restera du groupe commençant à n (suit les marques supprimées)."""
        q = n
        while C.marque_supprimee(q):
            s = C.bloc_suivant(q)
            if s is None or ln(s) != 'p' or id(s) not in pos: break
            q = s
        return q

    def appliquer(self, regles, C):
        body = self.doc.find(W + 'body'); paras = list(body.iter(W + 'p')); pos = {id(p): i for i, p in enumerate(paras)}
        S = C.Styles(self.z)
        # Phase 1 : passages (H1), fragments résiduels (H7) ; résidus de Markdown listés.
        R = C.releve_arbre(self.doc, self.z); lim = R['profil']['debut_sommaire']; PT = C.profil_tailles(paras, lim, S)
        par_index = collections.defaultdict(list)
        for e in R['ecarts']: par_index[e['index']].append(e)
        for i, E in sorted(par_index.items()):
            p = paras[i]; codes = {e['code'] for e in E}
            for e in E:
                if e['code'] == 'MF3': self.decider('MF3', i, e['texte'], e['detail'], C, e['auteur'])
            if 'H1' in regles and codes & {'MF1', 'MF2'}:
                st = C.pstyle(p); zn = C.zone(p, st); dom = C.dominante(p, st, S) or PT.get(zn)
                for r, t in list(C.runs_texte(p)):
                    v, expl = C.taille_run(r, st, S)
                    if not dom or v == dom: continue
                    if self.taille(r, dom): self.noter('H1', i, C.auteur(r), t.strip(), f'{int(v) / 2:g} pt', f'{int(dom) / 2:g} pt', C)
                    else: self.decider('H1', i, t.strip(), f'{int(v) / 2:g} pt au lieu de {int(dom) / 2:g} pt ; mise en forme déjà modifiée en suivi par un autre auteur', C, C.auteur(r))
            for e in E:
                if e['code'] == 'MF9' and 'H9' in regles:
                    tb = next(a for a in p.iterancestors() if ln(a) == 'tbl')
                    while any(ln(a) == 'tbl' for a in tb.iterancestors()): tb = next(a for a in tb.iterancestors() if ln(a) == 'tbl')
                    n = self.supprimer_rangees(tb, C)
                    if n: self.noter('H9', i, e['auteur'], e['texte'].strip() or '(tableau vide)', e['detail'], f'{n} rangée(s) supprimée(s) en suivi', C)
                elif e['code'] in ('MF9', 'MF10'): self.decider(e['code'], i, e['texte'], e['detail'], C, e['auteur'])
                if e['code'] != 'MF7': continue
                if 'H7' in regles and e['zone'] != 'tableau':
                    n = sum(self.supprimer_texte(paras[k], C) for k in e['membres'])
                    if n: self.noter('H7', i, e['auteur'], e['texte'].strip(), 'fragment visible', 'supprimé en suivi', C)
                else: self.decider('MF7', i, e['texte'], e['detail'], C, e['auteur'])
        # Phase 2 : lignes vides (H4) et paragraphes vides (H5), sur la vue acceptée recalculée.
        R2 = C.releve_arbre(self.doc, self.z)
        for e in R2['ecarts']:
            regle = {'MF4': 'H4', 'MF5': 'H5'}.get(e['code'])
            if not regle or regle not in regles: continue
            porteur = paras[e['index']]; n = C.bloc_suivant(porteur); brut = porteur.getnext()
            while brut is not None and ln(brut) not in C.BLOCS: brut = brut.getnext()
            if n is None or ln(n) != 'p' or id(n) not in pos or brut is not n: continue  # fin de conteneur, tableau (même supprimé) ou autre bloc : gardé
            cible = self.porteur_de(n, paras, pos, C)
            membres = [paras[k] for k in e['membres']]
            if 'H8' in regles and not all(self.alignable(m) or C.signature(m) == C.signature(cible) for m in membres):
                self.decider(e['code'], e['index'], e['texte'] or '(paragraphe vide)', 'retrait impossible sans changer la mise en forme du paragraphe suivant (paragraphe déjà modifié en suivi)', C, e['auteur'])
                continue
            if self.supprimer_marque(porteur):
                self.noter(regle, e['index'], e['auteur'], e['detail'] if e['code'] == 'MF4' else '(paragraphe vide)', 'présent', 'retiré', C)
        # Phase 3 : fusions (H8) : chaque paragraphe absorbé prend les propriétés du paragraphe qui reste.
        if 'H8' in regles:
            for g in C.groupes(paras):
                if len(g) < 2 or g[0] < lim: continue
                ps = [paras[k] for k in g]; porteur = ps[-1]
                if any(C.zone(p, C.pstyle(p)) == 'sommaire' for p in ps): continue
                dif = [p for p in ps[:-1] if C.signature(p) != C.signature(porteur)]
                if not dif: continue
                faits = [p for p in dif if self.aligner(p, porteur, C)]
                origine = C.auteur_suppression(ps[:-1])
                if faits: self.noter('H8', g[-1], origine, C.texte_visible(porteur).strip() or '(paragraphe vide)',
                                     f'{len(faits)} paragraphe(s) absorbé(s), dont « {C.pstyle(dif[0])} »', f'propriétés de « {C.pstyle(porteur)} »', C)
                if len(faits) < len(dif):
                    self.decider('MF8', g[-1], C.texte_visible(porteur).strip(), f'{len(dif) - len(faits)} paragraphe(s) absorbé(s) déjà modifié(s) en suivi par un autre auteur ou porteur(s) de section', C, origine)
        return self.a_decider

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
    src, out = a[0], a[1]; auteur = opt(a, '--auteur', 'Harmonisation - Claude'); regles = set((opt(a, '--regles', REGLES)).split(','))
    if os.path.exists(out): print(f'refus : {out} existe déjà (jamais d\'écrasement)'); return 3
    C = cmf(); h = Harmoniseur(src, auteur); a_decider = h.appliquer(regles, C); h.enregistrer(out)
    apres = C.releve(out); comp = C.comparer(src, out, auteur)
    cpt = collections.Counter(j['regle'] for j in h.journal)
    print(f"{sum(cpt.values())} correction(s) en suivi sous « {auteur} » : " + ', '.join(f'{k} {v}' for k, v in sorted(cpt.items())))
    print(f"écarts restants : {len(apres['ecarts'])} ({', '.join(f'{k} {v}' for k, v in apres['compte'].items())}) ; nouveaux écarts de « {auteur} » : {len(comp['vises'])}")
    for e in comp['vises'][:10]: print(f"  nouveau {e['code']} ¶{e['index']} : {e['detail'] or e['texte'][:60]}")
    if a_decider: print(f'{len(a_decider)} cas à décider (non corrigés) : ' + ' ; '.join(f"{x['regle']} ¶{x['index']} « {x['texte'][:30]} »" for x in a_decider[:12]))
    j = opt(a, '--journal')
    if j:
        with open(j, 'x', encoding='utf-8') as g: json.dump(dict(source=os.path.basename(src), sortie=os.path.basename(out), auteur=auteur, regles=sorted(regles), corrections=h.journal,
                                                                 a_decider=a_decider, restants=apres['compte'], nouveaux_auteur=len(comp['vises'])), g, ensure_ascii=False, indent=1)
    evenement(OUTIL, VERSION, 'harmoniser', dict(corrections=len(h.journal), **{k: cpt.get(k, 0) for k in ('H1', 'H4', 'H5', 'H7', 'H8', 'H9')}, a_decider=len(a_decider),
                                                verdict='conforme' if not comp['vises'] else 'non conforme'))
    return 0 if not comp['vises'] else 1


if __name__ == '__main__':
    sys.exit(main())
