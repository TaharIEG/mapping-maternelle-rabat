"""
Chargement des données et contrôles de cohérence.

Aucune donnée métier n'est codée ici : tout vient de data/.
Une nouvelle rentrée se charge en remplaçant le fichier d'extraction.
"""

import os
from pathlib import Path

import pandas as pd
import streamlit as st

DATA = Path(__file__).resolve().parent.parent / "data"
FICHIER_REFERENTIEL = DATA / "referentiel_quartiers.csv"

# L'extraction est trouvée par son extension, pas par son nom : Eduka sort
# tantôt du .xlsx, tantôt du .csv, et le nom du fichier change à chaque rentrée.
# .xlsx est préféré au .csv quand les deux sont présents (pas d'ambiguïté
# d'encodage ni de séparateur).
EXTENSIONS = (".xlsx", ".xlsm", ".csv")

# Date de l'extraction Eduka. Affichée sous les indicateurs et en pied de page.
# À remettre à jour à chaque nouvelle extraction — ou à repasser à None pour que
# l'application se rabatte sur la date de modification du fichier, en le
# signalant.
DATE_EXTRACTION = "11/09/2026"

# Libellés exacts du fichier Eduka -> noms internes.
# La colonne adresse est volontairement absente : remplie à 40,8 % et non
# normalisée, elle ne permet aucun géocodage fiable. Elle n'est ni lue ni
# affichée.
COLONNES = {
    "Code identifiant": "id_eleve",
    "Code famille": "id_famille",
    "Quartier analyse": "quartier",
    "Année d'arrivée de l'élève": "arrivee_eleve",
    "Niveau": "niveau",
    "Section": "section",
    "Année d'arrivée de la famille": "arrivee_famille",
    "Fraterie hors maternelle": "fratrie",  # orthographe du fichier source
}

# Colonnes dont une valeur vide fausserait un décompte : contrôlées au chargement.
OBLIGATOIRES = list(COLONNES.values())

# Modalités de « Quartier analyse » qui ne sont pas des quartiers.
EXCLUSIONS = ["Adresse non saisie", "Autres (etranger, autre ville)"]

ECOLE = {
    "nom": "LFSG",
    "lat": 33.96171998756709,
    "lng": -6.870393728834948,
}

CENTRE_CARTE = [33.97, -6.87]
ZOOM_CARTE = 12

# Fond de carte CARTO. Les tuiles exigent désormais une clé : sans elle, la
# carte se charge vide. La clé transite dans l'URL des tuiles, donc visible côté
# navigateur — c'est le fonctionnement prévu par CARTO pour ce type de clé.
# Style « positron » (light_all) : fond neutre clair, sur lequel le dégradé des
# bulles reste lisible. Pour « voyager », remplacer light_all par voyager.
#
# Le dépôt étant public, la clé ci-dessous l'est aussi. Ce type de clé n'est pas
# un secret au sens strict : elle voyage dans l'URL de chaque tuile et se lit
# donc dans le navigateur de n'importe quel visiteur. Elle reste surchargeable
# sans toucher au code, par la variable d'environnement `carto_cle` — que
# Streamlit Cloud alimente depuis les Secrets de l'application.
#
# La surcharge passe volontairement par l'environnement et non par `st.secrets` :
# en l'absence de fichier de secrets, lire `st.secrets` émet un élément
# Streamlit. Ce module étant importé avant `st.set_page_config()`, cet élément
# suffirait à faire échouer le démarrage de l'application.
CARTO_CLE = os.environ.get("carto_cle") or os.environ.get("CARTO_CLE") \
    or "cb1_3hdb_1_cdfc868c22cf32b27c78373e"

FOND_CARTE = (
    f"https://basemaps.cartocdn.com/rastertiles/light_all/"
    f"{{z}}/{{x}}/{{y}}.png?key={CARTO_CLE}"
)
FOND_ATTRIBUTION = "© OpenStreetMap · © CARTO"


# ---------------------------------------------------------------------------
# Localisation du fichier d'extraction
# ---------------------------------------------------------------------------
def trouver_fichier_eleves() -> Path:
    if not DATA.is_dir():
        raise FileNotFoundError(f"Le dossier {DATA} est introuvable.")

    candidats = [
        p for p in sorted(DATA.iterdir())
        if p.is_file()
        and p.suffix.lower() in EXTENSIONS
        and p.name != FICHIER_REFERENTIEL.name
        and not p.name.startswith("~$")  # fichier verrou laissé par Excel ouvert
    ]
    if not candidats:
        raise FileNotFoundError(
            f"Aucune extraction trouvée dans {DATA}. Déposez-y le fichier Eduka "
            f"({' ou '.join(EXTENSIONS)})."
        )

    tableurs = [p for p in candidats if p.suffix.lower() != ".csv"]
    retenus = tableurs or candidats
    if len(retenus) > 1:
        raise ValueError(
            "Plusieurs extractions présentes dans data/ : "
            + ", ".join(p.name for p in retenus)
            + ". N'en gardez qu'une, sinon le fichier lu serait arbitraire."
        )
    return retenus[0]


def _lire_csv(chemin: Path) -> pd.DataFrame:
    """
    Lecture tolérante : l'export Eduka sort en cp1252 séparé par « ; », mais
    un fichier réenregistré peut arriver en UTF-8 ou séparé par « , ».

    L'ordre des encodages n'est pas indifférent. En latin-1, l'octet 0x96 du
    tiret demi-cadratin de « Yacoub El Mansour – Akkari » se décode en
    caractère de contrôle : le libellé ne correspondrait plus au référentiel et
    le contrôle de cohérence refuserait de démarrer. cp1252 est donc essayé en
    premier, latin-1 n'est qu'un ultime recours.
    """
    erreur = None
    for encodage in ("utf-8-sig", "cp1252", "latin-1"):
        for sep in (";", ","):
            try:
                df = pd.read_csv(chemin, sep=sep, encoding=encodage, dtype=str)
            except UnicodeDecodeError as exc:
                erreur = exc
                break  # encodage inadapté : inutile d'essayer l'autre séparateur
            except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
                erreur = exc
                continue
            if df.shape[1] > 1:
                return df
    raise ValueError(
        f"Impossible de lire {chemin.name} : ni l'encodage ni le séparateur "
        f"n'ont pu être déterminés. ({erreur})"
    )


def _normaliser(df: pd.DataFrame) -> pd.DataFrame:
    """
    Renomme les colonnes et nettoie les chaînes.

    Le type `string` de pandas est utilisé plutôt que `str` : avec `astype(str)`
    une cellule vide devient la chaîne « nan », qui se mettrait à circuler comme
    une modalité de filtre à part entière et comme un libellé de quartier
    inconnu. Ici une cellule vide reste `pd.NA` et se fait détecter par les
    contrôles.
    """
    manquantes = [c for c in COLONNES if c not in df.columns]
    if manquantes:
        raise ValueError(
            "Colonnes absentes du fichier d'extraction : "
            + ", ".join(manquantes)
            + ". Les libellés doivent être repris exactement de l'export Eduka."
        )
    df = df[list(COLONNES)].rename(columns=COLONNES)
    for c in df.columns:
        df[c] = df[c].astype("string").str.strip().replace("", pd.NA)
    return df


@st.cache_data(show_spinner=False)
def _charger_referentiel(chemin: str, _empreinte: float) -> pd.DataFrame:
    ref = pd.read_csv(chemin, encoding="utf-8")
    attendues = {"quartier_canonique", "lat", "lng", "libelles_sources", "zone_large"}
    absentes = attendues - set(ref.columns)
    if absentes:
        raise ValueError(
            "Colonnes absentes du référentiel : " + ", ".join(sorted(absentes))
        )
    ref["zone_large"] = (
        ref["zone_large"].astype("string").str.strip().str.lower().eq("oui")
    )
    ref["quartier_canonique"] = ref["quartier_canonique"].astype("string").str.strip()
    ref["libelles_sources"] = ref["libelles_sources"].astype("string").str.strip()
    return ref


@st.cache_data(show_spinner=False)
def _charger_eleves(chemin: str, _empreinte: float) -> pd.DataFrame:
    p = Path(chemin)
    brut = _lire_csv(p) if p.suffix.lower() == ".csv" else pd.read_excel(p, dtype=str)
    return _normaliser(brut)


def charger_referentiel() -> pd.DataFrame:
    """L'empreinte (date de modification) fait tomber le cache quand le fichier change."""
    return _charger_referentiel(
        str(FICHIER_REFERENTIEL), FICHIER_REFERENTIEL.stat().st_mtime
    )


def charger_eleves() -> pd.DataFrame:
    fichier = trouver_fichier_eleves()
    return _charger_eleves(str(fichier), fichier.stat().st_mtime)


def date_extraction() -> str:
    """Date affichée. À défaut de DATE_EXTRACTION, la date du fichier, signalée."""
    if DATE_EXTRACTION:
        return DATE_EXTRACTION
    try:
        horodatage = pd.Timestamp.fromtimestamp(
            trouver_fichier_eleves().stat().st_mtime
        )
        return f"{horodatage:%d/%m/%Y} (date du fichier)"
    except (OSError, FileNotFoundError, ValueError):
        return "non renseignée"


# ---------------------------------------------------------------------------
# Correspondance libellé source -> quartier canonique
# ---------------------------------------------------------------------------
def correspondance(ref: pd.DataFrame) -> dict:
    """
    Libellé tel qu'il apparaît dans l'extraction -> quartier canonique.

    Une ligne du référentiel peut déclarer plusieurs libellés sources séparés
    par « | ». C'est ce qui permet de rattacher une variante d'orthographe
    (« Témara » accentué, par exemple) au même point sans dupliquer la bulle.
    """
    table = {}
    for _, r in ref.iterrows():
        for libelle in str(r["libelles_sources"]).split("|"):
            libelle = libelle.strip()
            if libelle:
                table[libelle] = r["quartier_canonique"]
    return table


def controler(df: pd.DataFrame, ref: pd.DataFrame) -> list[str]:
    """Contrôles bloquants. Retourne la liste des erreurs, vide si tout va bien."""
    erreurs = []

    doublons = int(df["id_eleve"].duplicated().sum())
    if doublons:
        exemples = sorted(df.loc[df["id_eleve"].duplicated(), "id_eleve"].unique())[:5]
        erreurs.append(
            f"{doublons} identifiant(s) élève en doublon : {', '.join(exemples)}"
            + (" …" if doublons > 5 else "")
            + ". Un élève compté deux fois fausserait tous les effectifs."
        )

    vides = {c: int(df[c].isna().sum()) for c in OBLIGATOIRES if df[c].isna().any()}
    if vides:
        erreurs.append(
            "Valeur(s) manquante(s) : "
            + ", ".join(f"{c} ({n})" for c, n in vides.items())
            + ". Complétez l'extraction : une cellule vide deviendrait une "
            "modalité de filtre fantôme."
        )

    doublons_ref = ref["quartier_canonique"].duplicated().sum()
    if doublons_ref:
        erreurs.append(
            f"{doublons_ref} quartier(s) en doublon dans le référentiel : les "
            "effectifs seraient répartis sur plusieurs bulles au même nom."
        )

    connus = set(correspondance(ref)) | set(EXCLUSIONS)
    inconnus = sorted(str(q) for q in df["quartier"].dropna().unique() if q not in connus)
    if inconnus:
        erreurs.append(
            "Libellé(s) de quartier absent(s) du référentiel : "
            + ", ".join(inconnus)
            + ". Ajoutez-les à data/referentiel_quartiers.csv, sinon les élèves "
            "concernés disparaîtraient de la carte sans avertissement."
        )

    return erreurs
