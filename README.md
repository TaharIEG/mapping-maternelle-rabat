# Résidence des élèves de maternelle

Application Streamlit de cartographie des élèves de maternelle par quartier.
Carte à bulles proportionnelles, filtres globaux, barycentre des lieux de
résidence.

## Données publiées : pseudonymisées

**Le fichier de ce dépôt n'est pas l'extraction d'origine.** Il en a été dérivé
pour pouvoir être publié :

- la colonne adresse a été **supprimée du fichier** — elle n'était de toute
  façon jamais lue par le code ;
- `Code identifiant` et `Code famille` ont été remplacés par des compteurs
  opaques (`E001`, `F001`…), numérotés au hasard. Dans l'extraction d'origine,
  le code famille **est** le nom de famille.

Les regroupements sont préservés à l'identique : un même foyer garde un même
code. Tous les agrégats — effectifs, parts, barycentres — sont rigoureusement
inchangés.

L'extraction d'origine n'a pas sa place dans ce dépôt.

## Lancement

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Structure

```
app.py                              interface, aucun chiffre métier
core/loading.py                     chargement et contrôles
core/filtering.py                   filtres et bascule élèves/familles
core/metrics.py                     agrégats, barycentre, distances
data/data_maternelle_rabat.xlsx     1 ligne = 1 élève (pseudonymisé)
data/referentiel_quartiers.csv      coordonnées des quartiers
```

## Déploiement — Streamlit Community Cloud

Pointez l'application sur ce dépôt, branche `main`, fichier `app.py`. Les
dépendances de `requirements.txt` sont installées automatiquement.

Le fond de carte CARTO exige une clé. Elle figure dans `core/loading.py` et se
surcharge depuis **Settings → Secrets** :

```toml
carto_cle = "votre_cle"
```

Sans clé valide, la carte se charge **vide, sans message d'erreur** — c'est le
premier réflexe si les bulles flottent sur du blanc.

## Mettre à jour les données

Déposez la nouvelle extraction dans `data/` et retirez l'ancienne. Le fichier
est reconnu à son extension, pas à son nom : `.xlsx`, `.xlsm` ou `.csv`
conviennent, et les libellés de colonnes doivent être repris exactement de
l'export Eduka. Aucun code n'est à modifier.

Deux extractions présentes en même temps font échouer le démarrage plutôt que
d'en choisir une au hasard.

Renseignez `DATE_EXTRACTION` dans `core/loading.py`. Tant qu'il vaut `None`,
l'application affiche la date de modification du fichier en le signalant.

**Pseudonymisez toute nouvelle extraction avant de la committer.**

### Encodage

Le `.xlsx` est le format le plus sûr : il porte son encodage. Un `.csv` exporté
par Eduka sort en **cp1252** séparé par `;` — le chargeur essaie successivement
UTF-8, cp1252 puis latin-1. L'ordre compte : en latin-1, le tiret demi-cadratin
de `Yacoub El Mansour – Akkari` se décode en caractère de contrôle, le libellé
ne correspond plus au référentiel et l'application refuse de démarrer.

### Quartier inconnu

Si l'extraction contient un libellé absent du référentiel, l'application refuse
de démarrer et le nomme. Ajoutez la ligne correspondante dans
`data/referentiel_quartiers.csv` (libellé canonique, latitude, longitude,
libellé source, `oui`/`non` pour une zone à emprise large). Ce garde-fou évite
qu'une nouvelle rentrée fasse disparaître des élèves de la carte sans
avertissement.

Une même ligne peut déclarer plusieurs libellés sources séparés par `|` : c'est
ainsi qu'une variante d'orthographe (`Témara` accentué, par exemple) se rattache
au même point sans dupliquer la bulle.

## Base de calcul

206 élèves, 195 familles. Deux modalités de `Quartier analyse` ne sont pas des
quartiers et sont exclues de la carte : « Adresse non saisie » (25) et « Autres
(etranger, autre ville) » (10). Base géographique : **171 élèves, 165
familles**. Les exclus restent comptabilisés et détaillés en bas de page.

## Points à connaître

**Aucun seuil de fiabilité.** Toutes les valeurs s'affichent, y compris sur
petits effectifs. L'effectif est systématiquement joint au pourcentage.

**Échelle graphique fixe.** La taille des bulles est calée sur la base non
filtrée, pour que les bulles rétrécissent visiblement quand on filtre.

**Barycentre.** Moyenne des coordonnées des quartiers pondérée par l'effectif. Il
porte sur les centroïdes de quartier, pas sur les adresses. Témara et Salé sont
signalés comme zones larges : leurs centroïdes sont approximatifs et pèsent 36 %
de la base.

**Section et niveau.** La section Anglaise n'existe pas en TPS ni en PS. Le
croisement PS + Anglaise renvoie donc un écran vide explicite.

**Mode familles.** Une famille est retenue si au moins un de ses enfants
correspond au filtre. Quatre familles ont des enfants dans les deux sections et
apparaissent donc des deux côtés : une note sous les tableaux le rappelle, la
somme des modalités dépasse le total. Quand plusieurs enfants d'une famille ont
des années d'arrivée différentes, c'est la plus ancienne qui est retenue.

**Confidentialité.** L'application n'affiche aucune ligne individuelle et ne
propose aucun export au niveau élève. Seuls des agrégats par quartier sont
produits.
