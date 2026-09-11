"""
Résidence des élèves de maternelle.
Carte à bulles proportionnelles par quartier.

    pip install -r requirements.txt
    streamlit run app.py
"""

import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from core import filtering as flt
from core import loading as ld
from core import metrics as mx

st.set_page_config(
    page_title="Résidence des élèves",
    page_icon="🗺️",
    layout="wide",
)

# `use_container_width` est devenu `width="stretch"` en Streamlit 1.49.
_VERSION = tuple(int(n) for n in re.findall(r"\d+", st.__version__)[:2])
LARGE = {"width": "stretch"} if _VERSION >= (1, 49) else {"use_container_width": True}

GRADIENT = ["#D6E8FA", "#9FCBEF", "#5FA3E0", "#2E7DCC", "#185FA5", "#0C447C"]
BRAND = "#0C447C"
BARY = "#1f2d3d"

st.markdown(
    """
    <style>
      .block-container { padding-top: 1.6rem; padding-bottom: 2rem; max-width: 1400px; }
      [data-testid="stMetricValue"] { color: #0C447C; font-weight: 700; }
      [data-testid="stMetricLabel"] { color: #5b6b7b; }
      .app-header h1 {
        font-size: 1.9rem; font-weight: 800; color: #0C447C;
        margin: 0 0 .15rem 0; letter-spacing: -.5px;
      }
      hr.soft { border: none; border-top: 1px solid #eef2f6; margin: 1.4rem 0; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# CHARGEMENT
# ---------------------------------------------------------------------------
try:
    ref = ld.charger_referentiel()
    brut = ld.charger_eleves()
except Exception as exc:
    st.error(f"Chargement impossible : {exc}")
    st.stop()

if erreurs := ld.controler(brut, ref):
    for e in erreurs:
        st.error(e)
    st.stop()

# ---------------------------------------------------------------------------
# BARRE LATÉRALE
# ---------------------------------------------------------------------------
CLES = [f"f_{a}" for a in flt.AXES]


def reinitialiser():
    for k in CLES:
        st.session_state[k] = []


unite = st.sidebar.radio(
    "Unité", [flt.ELEVES, flt.FAMILLES], horizontal=True
)

st.sidebar.markdown("**Filtres**")
selections = {
    axe: st.sidebar.multiselect(
        meta["label"], flt.modalites(brut, axe), key=f"f_{axe}", placeholder="Tous"
    )
    for axe, meta in flt.AXES.items()
}

afficher_bary = st.sidebar.checkbox("Barycentre", value=True)
st.sidebar.button("Réinitialiser", on_click=reinitialiser, **LARGE)

# ---------------------------------------------------------------------------
# FILTRAGE GLOBAL
# ---------------------------------------------------------------------------
filtre = flt.appliquer(brut, selections)
loc, exclus, orphelins = flt.separer(filtre, ref)

axes_actifs = flt.filtre_actif(selections)
n_filtre = flt.compte(filtre, unite)
n_loc = flt.compte(loc, unite)
n_exclus = flt.compte(exclus, unite)
n_total = flt.compte(brut, unite)

rep = mx.repartition(loc, ref, unite)
actifs = rep[rep["effectif"] > 0]

# Échelle graphique calée sur la base NON filtrée : les bulles rétrécissent
# quand on filtre, au lieu de garder la même taille comme en v1.
loc_ref, _, _ = flt.separer(brut, ref)
rep_ref = mx.repartition(loc_ref, ref, unite)
_effs = rep_ref[rep_ref["effectif"] > 0]["effectif"]
max_ref = int(_effs.max()) if not _effs.empty else 1
min_ref = int(_effs.min()) if not _effs.empty else 0

ecole = (ld.ECOLE["lat"], ld.ECOLE["lng"])
bary = mx.barycentre(loc, ref, unite)
ecart_bary = mx.distance_km(bary, ecole) if bary else None

# ---------------------------------------------------------------------------
# EN-TÊTE
# ---------------------------------------------------------------------------
st.markdown(
    """
    <div class="app-header">
      <h1>Résidence des élèves de maternelle</h1>
    </div>
    """,
    unsafe_allow_html=True,
)

# Pas de `delta` : Streamlit y accole une flèche de tendance, qui n'a aucun sens
# pour un effectif rapporté à son total.
c1, c2, c3 = st.columns(3)
c1.metric(unite, f"{n_filtre} / {n_total}")
c2.metric("Localisé(e)s", f"{n_loc}")
c3.metric("Non localisé(e)s", f"{n_exclus}")

st.caption(("Filtres : " + ", ".join(axes_actifs)) if axes_actifs else "Base complète")

if not orphelins.empty:
    st.warning(f"{len(orphelins)} ligne(s) hors référentiel, non cartographiées.")

if n_filtre == 0:
    st.warning("Combinaison absente des données.")
    st.stop()

# ---------------------------------------------------------------------------
# CARTE
# ---------------------------------------------------------------------------
SCALE = 1.0


def color_for(value, vmin, vmax):
    if vmax == vmin:
        return GRADIENT[-1]
    t = (value - vmin) / (vmax - vmin)
    return GRADIENT[min(int(t * len(GRADIENT)), len(GRADIENT) - 1)]


def luminance(hex_color):
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255


def bubble_radius(value):
    # rayon en racine carrée -> l'AIRE est proportionnelle à l'effectif
    return (value / max_ref) ** 0.5 * 38 * SCALE + 4


def construire_carte(points: pd.DataFrame) -> folium.Map:
    m = folium.Map(
        location=ld.CENTRE_CARTE,
        zoom_start=ld.ZOOM_CARTE,
        tiles=ld.FOND_CARTE,
        attr=ld.FOND_ATTRIBUTION,
    )

    for _, row in points.iterrows():
        radius = bubble_radius(row["effectif"])
        fill_col = color_for(row["effectif"], min_ref, max_ref)
        large = ('<br><span style="color:#a06000;">Zone large, centroïde '
                 'approximatif</span>' if row["zone_large"] else "")
        popup = folium.Popup(
            f'<div style="font-family:system-ui,sans-serif;font-size:13px;">'
            f'<b style="color:{BRAND};">{row["quartier"]}</b><br>'
            f'<span style="font-size:18px;font-weight:700;">{int(row["effectif"])}</span>'
            f' {unite.lower()}'
            f'<br><span style="color:#5b6b7b;">{mx.fr(row["part"])} % du localisé</span>'
            f'{large}</div>',
            max_width=240,
        )
        folium.CircleMarker(
            location=[row["lat"], row["lng"]],
            radius=radius,
            color=BRAND,
            weight=1.2,
            fill=True,
            fill_color=fill_col,
            fill_opacity=0.78,
            popup=popup,
            tooltip=f"{row['quartier']} — {int(row['effectif'])} ({mx.fr(row['part'])} %)",
        ).add_to(m)

        if luminance(fill_col) < 0.55:
            txt, halo = "#ffffff", "rgba(4,36,63,.55)"
        else:
            txt, halo = "#04243f", "rgba(255,255,255,.85)"
        folium.map.Marker(
            [row["lat"], row["lng"]],
            icon=folium.DivIcon(
                html=(
                    f'<div style="font-size:11px;font-weight:700;color:{txt};'
                    f'text-align:center;transform:translate(-50%,-50%);'
                    f'white-space:nowrap;text-shadow:0 0 3px {halo},0 0 3px {halo};">'
                    f'{int(row["effectif"])}</div>'
                )
            ),
        ).add_to(m)

        offset = radius + 6
        folium.map.Marker(
            [row["lat"], row["lng"]],
            icon=folium.DivIcon(
                html=(
                    f'<div style="font-size:11px;font-weight:600;color:#1f2d3d;'
                    f'text-align:center;transform:translate(-50%,{offset:.0f}px);'
                    f'white-space:nowrap;'
                    f'text-shadow:0 0 3px #fff,0 0 3px #fff,0 0 3px #fff;">'
                    f'{row["quartier"]}</div>'
                )
            ),
        ).add_to(m)

    folium.Marker(
        location=list(ecole),
        tooltip=ld.ECOLE["nom"],
        icon=folium.Icon(color="red", icon="graduation-cap", prefix="fa"),
    ).add_to(m)

    if afficher_bary and bary:
        folium.PolyLine(
            [list(ecole), list(bary)],
            color=BARY, weight=2.4, opacity=0.85, dash_array="6,5",
            tooltip=f"{mx.fr(ecart_bary, 2)} km",
        ).add_to(m)
        # Disque plein cerclé de blanc : le point était auparavant blanc à
        # liseré sombre, donc invisible dès qu'il tombait sur une bulle foncée
        # — ce qui est le cas normal, le barycentre se logeant au milieu des
        # effectifs.
        # icon_size/icon_anchor à (0,0) : le conteneur Leaflet se réduit au point
        # géographique, et chaque élément se centre dessus par sa propre
        # transformation. Sans cela le conteneur fait 30 px par défaut et décale
        # l'étiquette par rapport à son disque.
        # L'étiquette passe au-dessus, sur pastille blanche : sous le disque elle
        # heurtait l'effectif de la bulle, le barycentre tombant par
        # construction au milieu des plus gros quartiers.
        folium.map.Marker(
            list(bary),
            icon=folium.DivIcon(
                icon_size=(0, 0),
                icon_anchor=(0, 0),
                html=(
                    f'<div style="position:absolute;transform:translate(-50%,-50%);'
                    f'width:17px;height:17px;border-radius:50%;background:{BARY};'
                    f'border:3px solid #fff;'
                    f'box-shadow:0 0 0 1.5px {BARY},0 1px 4px rgba(0,0,0,.45);">'
                    '</div>'
                    f'<div style="position:absolute;transform:translate(-50%,-34px);'
                    f'background:#fff;border:1px solid {BARY};border-radius:3px;'
                    f'padding:1px 5px;font-size:10px;font-weight:700;color:{BARY};'
                    'white-space:nowrap;line-height:1.35;">Barycentre</div>'
                ),
            ),
            tooltip=f"Barycentre — {mx.fr(ecart_bary, 2)} km",
            # Leaflet empile les marqueurs par latitude : le marqueur de l'école,
            # plus au sud, passait devant et tronquait l'étiquette. Le barycentre
            # est la couche d'analyse, il doit rester au-dessus.
            z_index_offset=1000,
        ).add_to(m)

    lats = list(points["lat"]) + [ecole[0]]
    lngs = list(points["lng"]) + [ecole[1]]
    if afficher_bary and bary:
        lats.append(bary[0])
        lngs.append(bary[1])
    if len(lats) >= 2:
        m.fit_bounds([[min(lats), min(lngs)], [max(lats), max(lngs)]], padding=(40, 40))

    size_vals = sorted(
        {v for v in (max_ref, max(int(round(max_ref / 2)), min_ref + 1), min_ref)
         if v > 0},
        reverse=True,
    )
    size_circles = "".join(
        f'<div style="display:flex;align-items:center;gap:5px;margin-top:3px;">'
        f'<span style="display:inline-flex;width:{min(2 * bubble_radius(v), 26):.0f}px;'
        f'height:{min(2 * bubble_radius(v), 26):.0f}px;min-width:6px;border-radius:50%;'
        f'background:rgba(46,125,204,.30);border:1px solid #2E7DCC;"></span>'
        f'<span style="color:#445;">{int(v)}</span></div>'
        for v in size_vals
    )
    legend_html = (
        '<div style="position:fixed; bottom:18px; left:18px; z-index:9999; '
        'background:rgba(255,255,255,.96); padding:6px 8px; border:1px solid #d9e2ec; '
        'border-radius:7px; font-size:10px; color:#333; font-family:system-ui,sans-serif; '
        'box-shadow:0 1px 5px rgba(12,68,124,.15);">'
        f'<div style="margin-bottom:3px; font-weight:700; color:{BRAND};">'
        f'{unite} / quartier</div>'
        '<div style="display:flex; align-items:center; gap:1px;">'
        + "".join(
            f'<span style="width:15px;height:8px;display:inline-block;background:{c};"></span>'
            for c in GRADIENT
        )
        + "</div>"
        '<div style="display:flex; justify-content:space-between; margin-top:1px;">'
        f'<span>{min_ref}</span><span>{max_ref}</span></div>'
        '<div style="margin-top:5px; border-top:1px solid #eef2f6; padding-top:4px;">'
        + size_circles
        + '</div>'
        '<div style="margin-top:4px; color:#8a97a4;">échelle fixe</div>'
        '</div>'
    )
    m.get_root().html.add_child(folium.Element(legend_html))
    return m


if actifs.empty:
    st.info("Aucun localisable dans cette sélection.")
else:
    signature = f"{unite}|{afficher_bary}|" + "|".join(
        f"{a}:{','.join(v)}" for a, v in selections.items()
    )
    st_folium(
        construire_carte(actifs), use_container_width=True, height=560,
        returned_objects=[],
        key=f"map_{hashlib.md5(signature.encode()).hexdigest()[:12]}",
    )

    # -----------------------------------------------------------------------
    # RÉPARTITION
    # -----------------------------------------------------------------------
    st.subheader("Répartition par quartier")

    # Part et cumul en texte : Streamlit affiche « None » sur une cellule
    # numérique vide, et ces deux colonnes suivent exactement l'ordre de
    # l'effectif — les trier n'apporterait rien. En texte, elles prennent au
    # passage la virgule décimale.
    table = rep[["quartier", "effectif", "part", "cumul"]].copy()
    table.columns = ["Quartier", unite, "Part", "Cumul"]
    for col in ("Part", "Cumul"):
        table[col] = table[col].map(lambda v: f"{mx.fr(v)} %")
    if n_exclus:
        table = pd.concat(
            [table, pd.DataFrame([["Non localisé(e)s", n_exclus, "", ""]],
                                 columns=table.columns)],
            ignore_index=True,
        )

    st.dataframe(table, hide_index=True, **LARGE)
    if note := flt.note_familles_mixtes(loc, unite, flt.AXES):
        st.caption(note)

# ---------------------------------------------------------------------------
# QUALITÉ
# ---------------------------------------------------------------------------
st.markdown('<hr class="soft">', unsafe_allow_html=True)
st.subheader("Détail des non localisés")

if n_exclus:
    exclus_u = flt.au_niveau_unite(exclus, unite)

    g, d = st.columns(2)
    with g:
        det = exclus_u["quartier"].value_counts().rename_axis("Motif").reset_index(
            name=unite
        )
        det["Part"] = (det[unite] / n_filtre * 100).map(lambda v: f"{mx.fr(v)} %")
        st.dataframe(det, hide_index=True, **LARGE)
    with d:
        ct = pd.crosstab(exclus_u["niveau"], exclus_u["arrivee_eleve"])
        ct = ct.reindex(
            index=[n for n in flt.AXES["niveau"]["ordre"] if n in ct.index],
            columns=sorted(ct.columns, reverse=True),  # millésimes, plus récent d'abord
        )
        ct.index.name = "Niveau"
        ct.columns.name = None
        st.dataframe(ct, **LARGE)
        st.caption("Exclus par niveau et année d'arrivée de l'élève.")
else:
    st.caption("Aucun exclu dans cette sélection.")

st.caption(f"Extraction le {ld.date_extraction()}")
