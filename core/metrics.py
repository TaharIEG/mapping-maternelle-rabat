"""
Agrégats, barycentre, distances.

Aucun seuil de fiabilité n'est appliqué : toutes les valeurs calculées sont
affichées telles quelles. L'effectif est en revanche systématiquement joint au
pourcentage, dans les tableaux comme dans les infobulles.
"""

import math

import pandas as pd

from core.filtering import au_niveau_unite
from core.loading import correspondance


def repartition(df_loc: pd.DataFrame, ref: pd.DataFrame, unite: str) -> pd.DataFrame:
    """
    Effectif, part et cumul décroissant par quartier.

    Tous les quartiers du référentiel sont conservés, y compris à effectif nul
    après filtrage, pour que l'absence soit lisible dans le tableau.
    """
    d = au_niveau_unite(df_loc, unite)
    table = correspondance(ref)

    if d.empty:
        eff = pd.Series(dtype="int64")
    else:
        eff = d["quartier"].map(table).value_counts()

    out = ref.rename(columns={"quartier_canonique": "quartier"}).copy()
    out["effectif"] = out["quartier"].map(eff).fillna(0).astype(int)
    total = int(out["effectif"].sum())
    out["part"] = (out["effectif"] / total * 100) if total else 0.0
    out = out.sort_values(
        ["effectif", "quartier"], ascending=[False, True]
    ).reset_index(drop=True)
    out["cumul"] = out["part"].cumsum()
    return out[["quartier", "lat", "lng", "zone_large", "effectif", "part", "cumul"]]


def barycentre(df_loc: pd.DataFrame, ref: pd.DataFrame, unite: str):
    """
    Moyenne des coordonnées, pondérée par l'effectif de chaque quartier.

    Le calcul porte sur les centroïdes de quartier, pas sur les adresses : le
    barycentre situe le centre de gravité des zones de résidence, pas des
    domiciles. Témara et Salé, signalés comme zones larges, pèsent 36 % de la
    base sur deux points approximatifs.
    """
    rep = repartition(df_loc, ref, unite)
    rep = rep[rep["effectif"] > 0]
    if rep.empty:
        return None
    poids = rep["effectif"].sum()
    lat = (rep["lat"] * rep["effectif"]).sum() / poids
    lng = (rep["lng"] * rep["effectif"]).sum() / poids
    return lat, lng


def fr(x, dec: int = 1, signe: bool = False) -> str:
    """
    Nombre à la française : virgule décimale.

    Les tableaux, eux, restent en notation pointée : `st.column_config` n'expose
    pas de format localisé, et convertir en texte pour la virgule ferait perdre
    le tri numérique des colonnes.
    """
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    return f"{x:+.{dec}f}".replace(".", ",") if signe else f"{x:.{dec}f}".replace(".", ",")


def distance_km(a, b) -> float:
    """Distance approchée, suffisante à l'échelle de l'agglomération."""
    if a is None or b is None:
        return float("nan")
    dy = (a[0] - b[0]) * 111.32
    dx = (a[1] - b[1]) * 111.32 * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot(dx, dy)
