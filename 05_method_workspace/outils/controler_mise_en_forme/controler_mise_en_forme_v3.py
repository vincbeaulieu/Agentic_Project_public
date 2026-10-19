"""
OUTIL: controler_mise_en_forme
VERSION: 3
RESUME: Contrôle déterministe de la mise en forme d'un rapport Word révisé en suivi, avec la provenance de chaque écart (auteur de la révision qui l'a introduit, ou « base » pour le texte accepté). La v2 simule l'acceptation de toutes les révisions (« vue acceptée ») : un paragraphe dont la marque est supprimée en suivi se fond dans le suivant ; les écarts de paragraphe sont jugés sur le paragraphe qui restera. Écarts : MF1 passage sans taille explicite dont la taille effective (style, valeurs par défaut) diffère de la taille dominante de son paragraphe ; MF2 taille explicite différente ; MF3 résidu de Markdown (*…*, **…**, « * » en tête, #, `) ; MF4 ligne vide laissée par une suppression en suivi (texte supprimé, marque gardée) ; MF5 paragraphe vide hors des cas utiles (avant ou entre des tableaux, porteur d'un saut de page, d'une section ou d'un signet) ; MF6 police directe hors de la police du document et des polices permises ; MF7 fragment résiduel d'une suppression (quelques caractères survivent d'un paragraphe presque entièrement supprimé, par exemple un numéro de page d'un ancien sommaire) ; MF8 fusion à l'acceptation entre paragraphes de propriétés différentes (le résultat dépend du logiciel : Word garde celles du dernier paragraphe, LibreOffice celles du premier ; un titre peut devenir du corps de texte). La page de garde (tout ce qui précède la table des matières) et le sommaire ne sont jamais contrôlés pour correction. Commande « comparer » : écarts nouveaux d'une version à l'autre, par auteur, avec code 1 si l'auteur visé en a introduit (contrôle après chaque passe). Commande « accepte » : textes de la vue acceptée, pour confronter la simulation à une acceptation réelle. Commande « reference » (v3) : la mise en forme effective d'un document (par exemple le journal qui accompagne un rapport) est comparée à celle d'un document de référence (le rapport) : FR1 police ou taille dominante d'une catégorie (titres 1 à 3, corps, liste, cellule de tableau, légende) différente de la référence ; FR2 police absente de la référence ; FR3 titre dont police, taille, graisse, italique ou couleur effectives n'existent pas pour ce style dans la référence ; FR4 puces (format et glyphe du premier niveau) absentes de la référence ; FR5 champs du pied de page différents (« Page N sur M » : PAGE, NUMPAGES) ; la page de garde n'est pas comparée ; code 1 au moindre écart.
CATALOGUE CONSULTÉ : « comparer mise en forme docx » → controler_mise_en_forme (étendu, mode reference) ; audit_mise_en_forme_v2 et comparer_format_v1 (scripts du dossier 17, non promus) portés ici puis retirés.
USAGE: python3 outils/controler_mise_en_forme.py releve <docx> [--json <sortie.json>]  |  comparer <avant.docx> <apres.docx> [--auteur "Reevaluation - Claude"] [--json <sortie.json>]  |  accepte <docx> [--json <sortie.json>]  |  reference <reference.docx> <document.docx> [--json <sortie.json>]
ENTREES: docx (word/document.xml, word/styles.xml)
SORTIES: résumé à l'écran ; JSON facultatif {profil, ecarts:[{code, index, zone, auteur, texte, detail, membres}], compte} ; événement dans journal/ ; code 1 si « comparer » trouve des écarts nouveaux de l'auteur visé
CATEGORIE: revision_rapport
BANC: tests/test_controler_mise_en_forme_v3.py
REMPLACE: controler_mise_en_forme_v2 (ne comparait un document qu'à une autre version de lui-même : le format d'un journal livré avec un rapport — Calibri 9,5 pt, titres bleus au lieu de Times New Roman 11 pt — passait sans écart, erreur 6 du tableau de bord du 16 oct. 2026 ; commande « reference » ajoutée, qui reprend le relevé par catégorie des scripts audit_mise_en_forme_v2 et comparer_format_v1 ; le JSON demandé par --json n'écrase plus un fichier existant) ; v2 : controler_mise_en_forme_v1
"""
import sys, os, re, json, zipfile, collections
H = os.path.dirname(os.path.abspath(__file__)); O = H
while os.path.basename(O) != 'outils' and os.path.dirname(O) != O: O = os.path.dirname(O)
for p in (os.path.join(O, '_compat'), O):
    if p not in sys.path: sys.path.insert(0, p)
from lxml import etree                                       # noqa: E402
from cc_lib_v4 import evenement                              # noqa: E402

VERSION = 3; OUTIL = 'controler_mise_en_forme'
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
POLICES_PERMISES = {'Cambria Math'}
# Résidus de Markdown : emphase appariée (*mot*, **mot**, « * mot* »), titre « # », code « ` ». Une étoile d'appel de note (« * A : … », « B* ») n'en est pas un.
MD = re.compile(r'(?:^|[\s(])\*{1,2}\s?[^\s*][^*\n]{0,80}?\*{1,2}(?=\s*[,.;:)]|\s|$)|^\s*#{1,6}\s|`[^`]+`')
CODES = {'MF1': 'passage sans taille explicite, plus grand ou plus petit que son paragraphe', 'MF2': 'taille explicite différente de celle du paragraphe',
         'MF3': 'résidu de Markdown', 'MF4': 'ligne vide laissée par une suppression en suivi',
         'MF5': 'paragraphe vide inutile', 'MF6': 'police directe hors police du document',
         'MF7': 'fragment résiduel d\'une suppression', 'MF8': 'fusion à l\'acceptation entre paragraphes de propriétés différentes',
         'MF9': 'tableau vidé par des suppressions en suivi, rangées gardées', 'MF10': 'légende supprimée d\'un tableau gardé'}
# Fragment résiduel : au plus FRAG_MAX caractères visibles survivent, et la suppression en suivi couvre au moins FRAG_PART du texte d'origine.
FRAG_MAX = 8; FRAG_PART = 0.8
# Éléments de niveau bloc entre lesquels une fusion de paragraphes est possible ; les autres frères (signets, commentaires) sont transparents.
BLOCS = ('p', 'tbl', 'sdt', 'sectPr', 'customXml', 'altChunk')
HORS_SIGNATURE = ('rPr', 'pPrChange', 'sectPr')


def ln(e): return e.tag.split('}')[1] if isinstance(e.tag, str) else ''


# Anonymisation des sorties (règle E13 : aucun nom de personne dans mes documents) : les auteurs de révision et les extraits passent par
# l'outil anonymiser et ses rôles (Utilisateur, Collègue A…) ; sans rôles disponibles, tout auteur autre que Claude devient « Collègue ».
LIBELLES_NEUTRES = {'base', 'Utilisateur invité', 'Auteur', 'Author', 'Unknown', 'Inconnu'}
_ANON = {}


def _anonymiseur():
    if 'f' not in _ANON:
        try:
            from cc_lib_v4 import chemin, chemin_outil, derniere_version
            import importlib.util
            with open(derniere_version(chemin('regles'), 'roles', 'json'), encoding='utf-8') as g: roles = json.load(g)['roles']
            s = importlib.util.spec_from_file_location('anonymiser_courant', chemin_outil('anonymiser')); m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
            _ANON['f'] = lambda x: m.anonymiser(x, roles)
        except Exception:
            _ANON['f'] = None
    return _ANON['f']


def anonyme_auteur(a):
    if not a or a in LIBELLES_NEUTRES or a.endswith('- Claude') or re.fullmatch(r'(Collègue|Utilisateur)( [A-Z])?', a): return a
    f = _anonymiseur(); r = f(a) if f else a
    return r if r != a else 'Collègue'


def anonyme_texte(t):
    f = _anonymiseur(); return f(t) if (f and t) else t


def dans(e, *noms):
    return any(ln(a) in noms for a in e.iterancestors())


def auteur(e):
    """Auteur de l'insertion (ou du déplacement) qui contient e, sinon « base »."""
    for a in e.iterancestors():
        if ln(a) in ('ins', 'moveTo'): return a.get(W + 'author')
        if ln(a) == 'p': break
    return 'base'


class Styles:
    def __init__(self, z):
        s = etree.fromstring(z.read('word/styles.xml')); self.taille, self.base, self.police = {}, {}, {}
        dd = s.find(f'{W}docDefaults/{W}rPrDefault/{W}rPr')
        self.defaut_taille = (dd.find(W + 'sz').get(W + 'val') if dd is not None and dd.find(W + 'sz') is not None else '20')
        f = dd.find(W + 'rFonts') if dd is not None else None
        self.defaut_police = (f.get(W + 'ascii') or f.get(W + 'hAnsi')) if f is not None else None
        for st in s.iter(W + 'style'):
            i = st.get(W + 'styleId'); b = st.find(W + 'basedOn'); self.base[i] = b.get(W + 'val') if b is not None else None
            sz = st.find(f'{W}rPr/{W}sz'); self.taille[i] = sz.get(W + 'val') if sz is not None else None

    def taille_style(self, i, n=0):
        if i is None or n > 12: return self.defaut_taille
        return self.taille.get(i) or self.taille_style(self.base.get(i), n + 1)


def texte_visible(e):
    return ''.join(t.text or '' for t in e.iter(W + 't') if not dans(t, 'del', 'moveFrom'))


def texte_supprime(e):
    return ''.join(t.text or '' for t in e.iter(W + 'delText')) + ''.join(t.text or '' for t in e.iter(W + 't') if dans(t, 'moveFrom'))


def image_visible(p):
    return any(not dans(x, 'del', 'moveFrom') for x in p.iter(W + 'drawing', W + 'object', W + 'pict'))


def zone(p, st):
    if dans(p, 'tc'): return 'tableau'
    if st.startswith('TOC'): return 'sommaire'
    if st.startswith('Heading') or st in ('Title', 'Subtitle'): return 'titres'
    if st == 'ListParagraph': return 'liste'
    return 'corps'


def pstyle(p):
    s = p.find(f'{W}pPr/{W}pStyle'); return s.get(W + 'val') if s is not None else 'Normal'


def marque_supprimee(p):
    rp = p.find(f'{W}pPr/{W}rPr'); return rp is not None and (rp.find(W + 'del') is not None or rp.find(W + 'moveFrom') is not None)


def signature(p):
    """Propriétés de paragraphe qui comptent pour une fusion (style compris), sans la marque, la section ni les révisions."""
    ppr = p.find(W + 'pPr'); morceaux = []
    if ppr is not None:
        for c in ppr:
            if ln(c) in HORS_SIGNATURE or not isinstance(c.tag, str): continue
            if ln(c) == 'pStyle' and c.get(W + 'val') == 'Normal': continue
            a = sorted((k.split('}')[1], v) for k, v in c.attrib.items() if not k.split('}')[1].startswith('rsid'))
            morceaux.append(etree.tostring(c, encoding=str) if len(c) else f'{ln(c)}{a}')
    return '|'.join(morceaux)


def tableau_supprime(e):
    """Vrai pour un tableau dont toutes les rangées sont supprimées en suivi : il disparaît à l'acceptation."""
    rs = e.findall(W + 'tr')
    return ln(e) == 'tbl' and bool(rs) and all(r.find(W + 'trPr') is not None and r.find(W + 'trPr').find(W + 'del') is not None for r in rs)


def bloc_suivant(p):
    """Bloc suivant dans la vue acceptée (signets, commentaires et tableaux supprimés en suivi sont transparents)."""
    s = p.getnext()
    while s is not None and (ln(s) not in BLOCS or tableau_supprime(s)): s = s.getnext()
    return s


def bloc_precedent(p):
    s = p.getprevious()
    while s is not None and (ln(s) not in BLOCS or tableau_supprime(s)): s = s.getprevious()
    return s


def rangee_supprimee(p):
    """Vrai si p est dans une rangée de tableau supprimée en suivi (elle disparaît entière à l'acceptation)."""
    for a in p.iterancestors():
        if ln(a) == 'tr':
            tp = a.find(W + 'trPr')
            if tp is not None and tp.find(W + 'del') is not None: return True
    return False


def groupes(paras):
    """Vue acceptée : liste de groupes [indices], chacun devenant un seul paragraphe après acceptation de toutes les révisions.
    Le dernier indice est le « porteur » (marque gardée) ; une fusion ne franchit ni tableau ni fin de conteneur (groupe « bloqué »).
    Les paragraphes des rangées supprimées en suivi sont écartés."""
    pos = {id(p): i for i, p in enumerate(paras)}; G = []; vu = set()
    for i, p in enumerate(paras):
        if i in vu: continue
        if rangee_supprimee(p): vu.add(i); continue
        g = [i]; q = p
        while marque_supprimee(q):
            n = bloc_suivant(q)
            if n is None or ln(n) != 'p' or id(n) not in pos: break
            q = n; g.append(pos[id(q)])
        vu.update(g); G.append(g)
    return G


def runs_texte(p):
    """Passages visibles porteurs de texte (hors supprimés, hors champs, exposants et indices)."""
    for r in p.iter(W + 'r'):
        if dans(r, 'del', 'moveFrom') or r.getparent() is None: continue
        t = ''.join(x.text or '' for x in r.findall(W + 't'))
        if not t.strip(): continue
        rp = r.find(W + 'rPr')
        if rp is not None and rp.find(W + 'vertAlign') is not None: continue
        yield r, t


def taille_run(r, st, S):
    rp = r.find(W + 'rPr'); sz = rp.find(W + 'sz') if rp is not None else None
    if sz is not None: return sz.get(W + 'val'), True
    rs = rp.find(W + 'rStyle') if rp is not None else None
    return (S.taille_style(rs.get(W + 'val')) if rs is not None else S.taille_style(st)), False


def dominante(p, st, S):
    """Taille dominante (en caractères) des passages « base » à taille explicite du paragraphe ; à défaut, de tous ses passages explicites."""
    for filtre in (lambda r: auteur(r) == 'base', lambda r: True):
        c = collections.Counter()
        for r, t in runs_texte(p):
            v, expl = taille_run(r, st, S)
            if expl and filtre(r): c[v] += len(t)
        if c: return c.most_common(1)[0][0]
    return None


def debut_sommaire(paras):
    for i, p in enumerate(paras):
        if pstyle(p).startswith('TOC') or texte_visible(p).strip().lower() in ('table des matières', 'sommaire'): return i
    return 0


def profil_tailles(paras, lim, S):
    """Taille dominante des passages « base » à taille explicite, par zone (corps, liste) : référence d'un paragraphe sans taille explicite."""
    c = collections.defaultdict(collections.Counter)
    for p in paras[lim:]:
        st = pstyle(p); zn = zone(p, st)
        if zn not in ('corps', 'liste'): continue
        for r, t in runs_texte(p):
            v, expl = taille_run(r, st, S)
            if expl and auteur(r) == 'base': c[zn][v] += len(t)
    return {zn: c[zn].most_common(1)[0][0] for zn in c}


def auteur_suppression(ps):
    c = collections.Counter(a.get(W + 'author') for p in ps for a in p.iter(W + 'del', W + 'moveFrom') if ln(a.getparent()) != 'rPr')
    if not c: c = collections.Counter(a.get(W + 'author') for p in ps for a in p.iter(W + 'del'))
    return c.most_common(1)[0][0] if c else 'base'


def utile_vide(ps, porteur):
    """Un paragraphe vide est utile s'il porte une section, un saut de page ou un signet, s'il précède un tableau ou s'il est dans un tableau."""
    for p in ps:
        if (p.find(f'{W}pPr/{W}sectPr') is not None or any(b.get(W + 'type') == 'page' for b in p.iter(W + 'br'))
                or p.find(f'{W}pPr/{W}pageBreakBefore') is not None or p.findall('.//' + W + 'bookmarkStart')): return True
    av, ap = bloc_precedent(ps[0]), bloc_suivant(porteur)
    return dans(porteur, 'tc') or (ap is not None and ln(ap) == 'tbl') or (av is not None and ln(av) == 'tbl' and ap is not None and ln(ap) == 'tbl')


def releve(chemin, couverture=None):
    z = zipfile.ZipFile(chemin); return releve_arbre(etree.fromstring(z.read('word/document.xml')), z, os.path.basename(chemin), couverture)


def releve_arbre(doc, z, nom='document', couverture=None):
    S = Styles(z)
    body = doc.find(W + 'body'); paras = [p for p in body.iter(W + 'p')]
    lim = debut_sommaire(paras) if couverture is None else couverture
    PT = profil_tailles(paras, lim, S)
    E = []

    def ecart(code, i, zn, aut, p, detail='', membres=None):
        E.append(dict(code=code, index=i, zone=zn, auteur=aut, texte=(texte_visible(p) if not membres else ''.join(texte_visible(paras[k]) for k in membres))[:90],
                      detail=detail, membres=membres or [i]))
    # 1. Écarts de paragraphe, jugés sur la vue acceptée (groupes fusionnés).
    for g in groupes(paras):
        ps = [paras[k] for k in g]; porteur = ps[-1]; i = g[-1]
        sts = [pstyle(p) for p in ps]; zn = zone(porteur, sts[-1])
        if g[0] < lim or any(zone(p, s) == 'sommaire' for p, s in zip(ps, sts)): continue
        vis = ''.join(texte_visible(p) for p in ps); sup = ''.join(texte_supprime(p) for p in ps)
        img = any(image_visible(p) for p in ps)
        if len(g) > 1:
            dif = [k for k, p in zip(g[:-1], ps[:-1]) if signature(p) != signature(porteur)]
            if dif:
                d = paras[dif[0]]
                ecart('MF8', i, zn, auteur_suppression(ps[:-1]), porteur,
                      f'{len(g)} paragraphes fusionnés ; ¶{dif[0]} « {pstyle(d)} » dans ¶{i} « {sts[-1]} »', membres=g)
        if not vis.strip() and not img:
            if marque_supprimee(porteur): continue                                  # groupe bloqué (fin de conteneur, tableau) : rien ne reste
            dernier_cellule = dans(porteur, 'tc') and bloc_suivant(porteur) is None
            if sup.strip() and not dernier_cellule:
                ecart('MF4', i, zn, auteur_suppression(ps), porteur, sup[:60], membres=g)
            elif not sup.strip() and zn in ('corps', 'liste') and not utile_vide(ps, porteur):
                m = porteur.find(f'{W}pPr/{W}rPr/{W}ins'); ecart('MF5', i, zn, m.get(W + 'author') if m is not None else 'base', porteur, membres=g)
            continue
        net = re.sub(r'\s', '', vis)
        origine = all(auteur(x) == 'base' for p in ps for x in p.iter(W + 't') if not dans(x, 'del', 'moveFrom') and (x.text or '').strip())
        # Résidu : chaque paragraphe qui garde du texte en a perdu l'essentiel lui-même (un titre intact absorbant des lignes supprimées n'en est pas un).
        residu = all(len(re.sub(r'\s', '', texte_supprime(p))) >= FRAG_PART * (len(re.sub(r'\s', '', texte_visible(p))) + len(re.sub(r'\s', '', texte_supprime(p))))
                     for p in ps if texte_visible(p).strip())
        if sup.strip() and origine and residu and len(net) <= FRAG_MAX and not img:
            ecart('MF7', i, zn, auteur_suppression(ps), porteur, f'« {vis.strip()} » survit à la suppression de « {sup.strip()[:50]} »', membres=g)
    # 2. Tableaux : vidés par des suppressions en suivi (rangées gardées : une grille ou un encadré vide reste), ou privés de leur légende.
    pos = {id(p): i for i, p in enumerate(paras)}
    for tb in body.iter(W + 'tbl'):
        if tableau_supprime(tb) or rangee_supprimee(tb): continue
        ptb = next(tb.iter(W + 'p'), None)
        if ptb is None or pos[id(ptb)] < lim: continue
        i = pos[id(ptb)]; vis = re.sub(r'\s', '', ''.join(texte_visible(r) for r in tb.findall(W + 'tr') if not (r.find(W + 'trPr') is not None and r.find(W + 'trPr').find(W + 'del') is not None)))
        sup = re.sub(r'\s', '', texte_supprime(tb))
        if sup and len(vis) <= 0.1 * (len(vis) + len(sup)):
            ecart('MF9', i, 'tableau', auteur_suppression([tb]), ptb, f'{len(vis)} caractère(s) visibles sur {len(vis) + len(sup)} ; {len(tb.findall(W + "tr"))} rangée(s) gardée(s)')
            continue
        av = bloc_precedent(tb)
        if av is not None and ln(av) == 'p' and not texte_visible(av).strip() and re.match(r'\s*(Tableau|Table|Figure)\b', texte_supprime(av)):
            ecart('MF10', i, 'tableau', auteur_suppression([av]), ptb, f'légende supprimée : « {texte_supprime(av).strip()[:50]} »')
    # 3. Écarts de passage, paragraphe par paragraphe.
    for i, p in enumerate(paras):
        st = pstyle(p); zn = zone(p, st)
        if i < lim or zn == 'sommaire': continue
        vis = texte_visible(p)
        if not vis.strip() or rangee_supprimee(p): continue
        if zn in ('corps', 'liste', 'titres') and MD.search(vis):
            a = collections.Counter(auteur(t) for t in p.iter(W + 't') if not dans(t, 'del') and re.search(r'[*#`]', t.text or ''))
            ecart('MF3', i, zn, a.most_common(1)[0][0] if a else 'base', p, MD.search(vis).group(0).strip()[:40])
        if zn in ('corps', 'liste'):
            dom = dominante(p, st, S) or PT.get(zn)
            for r, t in runs_texte(p):
                v, expl = taille_run(r, st, S)
                if dom and v != dom: ecart('MF1' if not expl else 'MF2', i, zn, auteur(r), p, f'{int(v) / 2:g} pt au lieu de {int(dom) / 2:g} pt : « {t.strip()[:30]} »')
        for r, t in runs_texte(p):
            f = r.find(f'{W}rPr/{W}rFonts')
            if f is not None:
                nom = f.get(W + 'ascii') or f.get(W + 'hAnsi')
                if nom and nom not in POLICES_PERMISES and nom != S.defaut_police: ecart('MF6', i, zn, auteur(r), p, nom)
    for e in E: e.update(auteur=anonyme_auteur(e['auteur']), texte=anonyme_texte(e['texte']), detail=anonyme_texte(e['detail']))
    E.sort(key=lambda e: (e['index'], e['code']))
    profil = dict(taille_corps=PT.get('corps'), taille_liste=PT.get('liste'), police_document=S.defaut_police, taille_defaut=S.defaut_taille, debut_sommaire=lim)
    compte = collections.Counter((e['code'], e['auteur']) for e in E)
    return dict(fichier=nom, profil=profil, ecarts=E, compte={f'{c} / {a}': n for (c, a), n in sorted(compte.items())})


def textes_acceptes(chemin):
    """Texte de chaque paragraphe de la vue acceptée, dans l'ordre du document (tableaux compris)."""
    z = zipfile.ZipFile(chemin); doc = etree.fromstring(z.read('word/document.xml')); paras = list(doc.find(W + 'body').iter(W + 'p'))
    out = []
    for g in groupes(paras):
        if marque_supprimee(paras[g[-1]]) and not ''.join(texte_visible(paras[k]) for k in g).strip(): continue
        out.append(''.join(texte_visible(paras[k]) for k in g))
    return out


def cle(e): return (e['code'], e['auteur'], e['texte'], e['detail'].split(' ; ¶')[0] if e['code'] == 'MF8' else e['detail'])


def comparer(avant, apres, auteur_vise=None):
    A, B = releve(avant), releve(apres)
    vus = collections.Counter(cle(e) for e in A['ecarts']); nouveaux = []
    for e in B['ecarts']:
        k = cle(e)
        if vus[k]: vus[k] -= 1
        else: nouveaux.append(e)
    vises = [e for e in nouveaux if auteur_vise is None or e['auteur'] == auteur_vise]
    return dict(avant=A['fichier'], apres=B['fichier'], nouveaux=nouveaux, vises=vises, auteur=auteur_vise)


# ---------------------------------------------------------------- v3 : comparaison à un document de référence
W14 = '{http://schemas.microsoft.com/office/word/2010/wordml}'
TITRES = ('Title', 'Heading1', 'Heading2', 'Heading3')
CATS_REF = ('Heading1', 'Heading2', 'Heading3', 'corps', 'liste', 'cellule de tableau', 'légende')


class StylesEffectifs:
    """Mise en forme effective d'un passage : valeurs par défaut, style Normal, style du paragraphe, style de caractère, mise en
    forme directe (même résolution que le relevé audit_mise_en_forme_v2 du dossier 17, porté ici)."""
    def __init__(self, z):
        st = etree.fromstring(z.read('word/styles.xml'))
        self.S = {s.get(W + 'styleId'): s for s in st.findall(W + 'style')}
        d = st.find(f'{W}docDefaults/{W}rPrDefault/{W}rPr'); self.defaut = self.props(d)
        th = z.read('word/theme/theme1.xml').decode('utf-8', 'ignore') if 'word/theme/theme1.xml' in z.namelist() else ''
        ma = re.search(r'<a:majorFont><a:latin typeface="([^"]+)"', th); mi = re.search(r'<a:minorFont><a:latin typeface="([^"]+)"', th)
        self.theme = dict(major=ma.group(1) if ma else '(sans thème)', minor=mi.group(1) if mi else '(sans thème)')

    @staticmethod
    def props(rpr):
        out = {}
        if rpr is None: return out
        f = rpr.find(W + 'rFonts')
        if f is not None:
            if f.get(W + 'ascii'): out['police'] = f.get(W + 'ascii')
            elif f.get(W + 'asciiTheme'): out['police'] = 'thème:' + f.get(W + 'asciiTheme')
        for tag, k in (('sz', 'taille'), ('color', 'couleur')):
            e = rpr.find(W + tag)
            if e is not None and e.get(W + 'val'): out[k] = e.get(W + 'val')
        for tag, k in (('b', 'gras'), ('i', 'italique')):
            e = rpr.find(W + tag)
            if e is not None: out[k] = e.get(W + 'val') not in ('0', 'false')
        return out

    def chaine(self, sid):
        out, vus = {}, set()
        while sid and sid not in vus:
            vus.add(sid); s = self.S.get(sid)
            if s is None: break
            for k, v in self.props(s.find(W + 'rPr')).items(): out.setdefault(k, v)
            b = s.find(W + 'basedOn'); sid = b.get(W + 'val') if b is not None else None
        return out

    def effectif(self, p, r):
        e = dict(self.defaut); e.update(self.chaine('Normal')); e.update(self.chaine(pstyle(p) or 'Normal'))
        rs = r.find(f'{W}rPr/{W}rStyle')
        if rs is not None: e.update(self.chaine(rs.get(W + 'val')))
        e.update(self.props(r.find(W + 'rPr')))
        pol = e.get('police', '?')
        if pol.startswith('thème:'): pol = self.theme['major' if 'major' in pol.lower() else 'minor'] + ' (thème)'
        t = int(e.get('taille', '24')) / 2
        return dict(police=pol, taille=(str(int(t)) if t == int(t) else str(t)), gras=bool(e.get('gras', False)),
                    italique=bool(e.get('italique', False)), couleur=e.get('couleur', 'auto'))


def categorie_ref(p):
    s = pstyle(p); t = texte_visible(p).strip()
    if s.startswith('TOC'): return 'sommaire'
    if s in TITRES: return s
    if dans(p, 'tbl'): return 'cellule de tableau'
    if re.match(r'(Tableau|Figure)\s+[A-Z]?\d+\.', t): return 'légende'
    if s == 'ListParagraph' or p.find(f'{W}pPr/{W}numPr') is not None: return 'liste'
    return 'corps' if s in ('', 'Normal') else 'style:' + s


def puces(z):
    """{(format, glyphe)} du premier niveau de chaque liste employée par un paragraphe."""
    if 'word/numbering.xml' not in z.namelist(): return {}
    N = etree.fromstring(z.read('word/numbering.xml'))
    absn = {a.get(W + 'abstractNumId'): a for a in N.findall(W + 'abstractNum')}
    num = {n.get(W + 'numId'): n.find(W + 'abstractNumId').get(W + 'val') for n in N.findall(W + 'num') if n.find(W + 'abstractNumId') is not None}
    out = {}
    for nid, aid in num.items():
        a = absn.get(aid); lvl = a.find(W + 'lvl') if a is not None else None
        if lvl is None: continue
        f = lvl.find(W + 'numFmt'); t = lvl.find(W + 'lvlText')
        out[nid] = (f.get(W + 'val') if f is not None else '?', t.get(W + 'val') if t is not None else '')
    return out


def champs_pied(z):
    """Mots-clés des champs des pieds de page (PAGE, NUMPAGES…)."""
    out = set()
    for n in z.namelist():
        if re.match(r'word/footer\d*\.xml$', n):
            x = etree.fromstring(z.read(n))
            for it in x.iter(W + 'instrText'):
                m = re.match(r'\s*([A-Z]+)', it.text or '')
                if m: out.add(m.group(1))
            for f in x.iter(W + 'fldSimple'):
                m = re.match(r'\s*([A-Z]+)', f.get(W + 'instr') or '')
                if m: out.add(m.group(1))
    return out


def releve_format(chemin):
    """Relevé par catégorie : {categorie: Counter((police, taille) -> caractères)}, titres (effectif par style), puces employées, champs du pied."""
    z = zipfile.ZipFile(chemin); S = StylesEffectifs(z); doc = etree.fromstring(z.read('word/document.xml'))
    paras = list(doc.find(W + 'body').iter(W + 'p')); lim = debut_sommaire(paras)
    cat = collections.defaultdict(collections.Counter); ex = {}; titres = collections.defaultdict(set); P = puces(z); listes = set()
    for i, p in enumerate(paras):
        if i < lim: continue                                    # page de garde : jamais comparée
        c = categorie_ref(p)
        if c == 'sommaire': continue
        np_ = p.find(f'{W}pPr/{W}numPr/{W}numId')
        if np_ is not None and np_.get(W + 'val') in P: listes.add(P[np_.get(W + 'val')])
        premier = None
        for r in p.iter(W + 'r'):
            if dans(r, 'del', 'moveFrom'): continue
            tt = ''.join(x.text or '' for x in r.iter(W + 't'))
            if not tt.strip(): continue
            e = S.effectif(p, r); k = (e['police'], e['taille']); cat[c][k] += len(tt)
            ex.setdefault((c, k), dict(index=i, paraId=p.get(W14 + 'paraId'), texte=anonyme_texte(tt[:50])))
            if premier is None: premier = e
        if c in TITRES and premier is not None:
            titres[c].add((premier['police'], premier['taille'], premier['gras'], premier['italique'], premier['couleur']))
    return dict(fichier=os.path.basename(chemin), categories={c: dict(v) for c, v in cat.items()}, exemples=ex, titres=titres,
                puces=listes, champs_pied=champs_pied(z), debut_sommaire=lim)


def comparer_reference(reference, document):
    A, B = releve_format(reference), releve_format(document); E = []
    def dom(c): return max(c.items(), key=lambda kv: kv[1])[0] if c else None
    pol_ref = {k[0] for c in A['categories'].values() for k in c}
    for c in CATS_REF:
        if c not in B['categories']: continue
        a, b = dom(A['categories'].get(c, {})), dom(B['categories'][c])
        if a is not None and a != b:
            E.append(dict(code='FR1', categorie=c, detail=f'dominante {b[0]} {b[1]} pt au lieu de {a[0]} {a[1]} pt', exemple=B['exemples'].get((c, b))))
        for k, n in B['categories'][c].items():
            if k[0] not in pol_ref:
                E.append(dict(code='FR2', categorie=c, detail=f'police {k[0]} absente de la référence ({n} caractères)', exemple=B['exemples'].get((c, k))))
    for s in TITRES:
        for t in sorted(B['titres'].get(s, set()) - A['titres'].get(s, set())):
            if A['titres'].get(s):
                E.append(dict(code='FR3', categorie=s, detail=f'{dict(zip(("police", "taille", "gras", "italique", "couleur"), t))} ; référence {sorted(A["titres"][s])}', exemple=None))
    for pu in sorted(B['puces'] - A['puces']):
        if A['puces']: E.append(dict(code='FR4', categorie='liste', detail=f'puce {pu} ; référence {sorted(A["puces"])}', exemple=None))
    if A['champs_pied'] != B['champs_pied']:
        E.append(dict(code='FR5', categorie='pied de page', detail=f'champs {sorted(B["champs_pied"])} ; référence {sorted(A["champs_pied"])}', exemple=None))
    return dict(reference=A['fichier'], document=B['fichier'], ecarts=E, verdict='conforme' if not E else 'non conforme')


def opt(a, k, d=None): return a[a.index(k) + 1] if k in a and a.index(k) + 1 < len(a) else d


USAGE = __doc__.split('USAGE:')[1].split('ENTREES:')[0].strip()


def main(a=None):
    a = sys.argv[1:] if a is None else a
    if not a or a[0] not in ('releve', 'comparer', 'accepte', 'reference') or len(a) < 2 or (a[0] in ('comparer', 'reference') and len(a) < 3): print(USAGE); return 2
    js = opt(a, '--json')
    if a[0] == 'releve':
        R = releve(a[1]); print(f"{R['fichier']} : {len(R['ecarts'])} écart(s) ; profil {R['profil']}")
        for k, n in R['compte'].items(): print(f'  {k} : {n}')
        evenement(OUTIL, VERSION, 'releve', dict(ecarts=len(R['ecarts']), codes=sorted({e['code'] for e in R['ecarts']})))
        code = 0
    elif a[0] == 'accepte':
        R = textes_acceptes(a[1]); print(f'{len(R)} paragraphe(s) dans la vue acceptée')
        code = 0
    elif a[0] == 'reference':
        R = comparer_reference(a[1], a[2])
        print(f"{R['document']} face à {R['reference']} : {R['verdict']} ({len(R['ecarts'])} écart(s))")
        for e in R['ecarts'][:40]: print(f"  {e['code']} {e['categorie']} : {e['detail']}" + (f" (ex. ¶{e['exemple']['paraId']} « {e['exemple']['texte']} »)" if e.get('exemple') else ''))
        evenement(OUTIL, VERSION, 'reference', dict(ecarts=len(R['ecarts']), codes=sorted({e['code'] for e in R['ecarts']}), verdict=R['verdict']))
        code = 1 if R['ecarts'] else 0
    else:
        R = comparer(a[1], a[2], opt(a, '--auteur'))
        print(f"{len(R['nouveaux'])} écart(s) nouveau(x) de {R['avant']} à {R['apres']}" + (f" ; {len(R['vises'])} de « {R['auteur']} »" if R['auteur'] else ''))
        for e in R['vises'][:30]: print(f"  {e['code']} ¶{e['index']} {e['auteur']} : {e['detail'] or e['texte'][:60]}")
        evenement(OUTIL, VERSION, 'comparer', dict(nouveaux=len(R['nouveaux']), vises=len(R['vises']), verdict='conforme' if not R['vises'] else 'non conforme'))
        code = 1 if (R['auteur'] and R['vises']) else 0
    if js:
        with open(js, 'x', encoding='utf-8') as g: json.dump(R, g, ensure_ascii=False, indent=1)   # v3 : jamais d'écrasement
    return code


if __name__ == '__main__':
    sys.exit(main())
