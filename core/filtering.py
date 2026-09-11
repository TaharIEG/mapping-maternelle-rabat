"""
Filtrage et unité de compte.

Le filtre est global : un seul jeu de données filtré est produit ici, et tous
les composants de l'interface en dérivent — carte, tableaux, indicateurs,
décompte des exclusions, section Qualité.
"""

import pandas as pd

from core.loading import EXCLUSIONS, correspondance

# Axes proposés en barre latérale. `ordre` fige l'ordre d'affichage quand la
# modalité a un ordre naturel ; None = tri alphabétique.
#
# `decroissant` renverse ce tri. Il sert aux millésimes, dont la liste change à
# chaque rentrée et ne peut donc pas être figée : « 23/24 » se trie
# lexicographiquement comme chronologiquement, le renversement met la rentrée la
# plus récente en tête.
AXES = {
    "niveau": {"label": "Niveau", "ordre": ["TPS", "PS", "MS", "GS"]},
    "section": {"label": "Section", "ordre": ["Générale", "Anglaise"]},
    "fratrie": {"label": "Avec Fratrie hors maternelle", "ordre": ["Oui", "Non"]},
    "arrivee_eleve": {"label": "Année d'arrivée de l'élève", "ordre": None,
                      "decroissant": True},
    "arrivee_famille": {"label": "Année d'arrivée de la famille", "ordre": None,
                        "decroissant": True},
}

# Axes portés par l'élève : deux enfants d'une même famille peuvent en différer.
AXES_ELEVE = ("niveau", "section", "arrivee_eleve")

ELEVES = "Élèves"
FAMILLES = "Familles"


def modalites(df: pd.DataFrame, axe: str) -> list[str]:
    meta = AXES[axe]
    ordre = meta["ordre"]
    presentes = {str(m) for m in df[axe].dropna().unique()}
    if ordre:
        return [m for m in ordre if m in presentes] + sorted(presentes - set(ordre))
    return sorted(presentes, reverse=meta.get("decroissant", False))


def appliquer(df: pd.DataFrame, selections: dict) -> pd.DataFrame:
    """Un axe sans aucune modalité cochée équivaut à tout sélectionner."""
    out = df
    for axe, choix in selections.items():
        if choix:
            out = out[out[axe].isin(choix)]
    return out


def filtre_actif(selections: dict) -> list[str]:
    """Libellés des axes réellement contraints, pour la mention du bandeau."""
    return [AXES[a]["label"] for a, choix in selections.items() if choix]


def separer(df: pd.DataFrame, ref: pd.DataFrame):
    """
    Sépare les élèves localisables des exclusions.

    Le troisième groupe — ni localisable, ni motif d'exclusion connu — ne peut
    exister qu'en cas de référentiel incomplet, que `controler()` bloque au
    démarrage. Il est renvoyé quand même : sans cela une ligne s'évaporerait de
    l'écran sans jamais être comptée nulle part.
    """
    connus = set(correspondance(ref))
    localises = df[df["quartier"].isin(connus)].copy()
    exclus = df[df["quartier"].isin(EXCLUSIONS)].copy()
    orphelins = df[
        ~df["quartier"].isin(connus) & ~df["quartier"].isin(EXCLUSIONS)
    ].copy()
    return localises, exclus, orphelins


def compte(df: pd.DataFrame, unite: str) -> int:
    """Effectif dans l'unité demandée."""
    if df.empty:
        return 0
    return int(df["id_famille"].nunique()) if unite == FAMILLES else int(len(df))


def au_niveau_unite(df: pd.DataFrame, unite: str) -> pd.DataFrame:
    """
    En mode Familles, ramène une ligne par famille.

    Le filtrage ayant déjà été appliqué au niveau élève, la déduplication
    réalise exactement la règle retenue : une famille est retenue si au moins un
    de ses enfants correspond au filtre.

    La ligne conservée est celle de l'enfant à l'année d'arrivée la plus
    ancienne, conformément au plan §6.1 — et non la première venue dans l'ordre
    du fichier. Quartier, année d'arrivée de la famille et fratrie étant
    cohérents entre frères et sœurs, ce choix n'affecte que `arrivee_eleve`,
    `niveau` et `section`, pour lesquels la règle est explicite.

    Le tri lexicographique sur les millésimes « 23/24 » est chronologique tant
    que le siècle ne change pas.
    """
    if unite != FAMILLES or df.empty:
        return df
    return (
        df.sort_values("arrivee_eleve", kind="stable")
        .drop_duplicates(subset="id_famille", keep="first")
    )


def familles_mixtes(df: pd.DataFrame, axe: str) -> int:
    """
    Familles dont les enfants relèvent de plusieurs modalités d'un axe élève.

    Ces familles sont comptées dans chaque modalité : en mode Familles, la somme
    des modalités dépasse donc le total.
    """
    if df.empty or axe not in AXES_ELEVE:
        return 0
    return int((df.groupby("id_famille")[axe].nunique() > 1).sum())


def note_familles_mixtes(df: pd.DataFrame, unite: str, axes) -> str | None:
    """Note affichée sous les tableaux concernés (plan §6.1). None si sans objet."""
    if unite != FAMILLES:
        return None
    concernes = [
        (AXES[a]["label"], n)
        for a in axes
        if a in AXES_ELEVE and (n := familles_mixtes(df, a))
    ]
    if not concernes:
        return None
    detail = ", ".join(f"{lab.lower()} ({n})" for lab, n in concernes)
    return f"Familles à modalités multiples comptées deux fois : {detail}."
