# SIRI Next Departures - Intégration Home Assistant

Cette intégration Home Assistant personnalisée permet de récupérer et d'afficher les prochains départs de transports en commun (bus, tram, etc.) à partir d'une API SIRI et d'un fichier NETEX décrivant les arrêts.

## Fonctionnalités

- Configuration via l'interface utilisateur de Home Assistant.
- Téléchargement et analyse d'un fichier NETEX pour obtenir la liste des arrêts.
- Interrogation d'un endpoint SIRI pour les prochains départs à un arrêt spécifique.
- Création d'entités capteur dans Home Assistant pour chaque arrêt surveillé.
- Chaque capteur affiche l'heure du prochain départ comme état et les départs suivants comme attributs.
- Carte Lovelace personnalisée pour afficher les prochains départs avec des icônes adaptées au mode de transport.

## Prérequis

- Une instance de Home Assistant fonctionnelle.
- Une URL accessible publiquement vers un fichier NETEX décrivant les arrêts de votre réseau de transport.
- Un endpoint SIRI (StopMonitoringService) pour récupérer les informations de passage en temps réel.
- Un ID de Dataset (ou clé d'API similaire) si requis par votre endpoint SIRI.

## Installation (Manuelle)

1.  **Copier les fichiers** :

    - Copiez l'intégralité du dossier `siri_next_departures` (qui contient `manifest.json`, `__init__.py`, `sensor.py`, `config_flow.py`, `const.py`, `utils.py`) dans le dossier `custom_components` de votre installation Home Assistant.
    - Si le dossier `custom_components` n'existe pas à la racine de votre configuration Home Assistant, créez-le.

    La structure devrait ressembler à ceci :

    ```
    <config_directory>/custom_components/siri_next_departures/__init__.py
    <config_directory>/custom_components/siri_next_departures/manifest.json
    <config_directory>/custom_components/siri_next_departures/sensor.py
    <config_directory>/custom_components/siri_next_departures/config_flow.py
    <config_directory>/custom_components/siri_next_departures/const.py
    <config_directory>/custom_components/siri_next_departures/utils.py
    ```

2.  **Installer la carte Lovelace personnalisée (optionnel)** :

    - Copiez le fichier `www/siri-next-departure-card.js` dans le dossier `www` de votre configuration Home Assistant.
    - Si le dossier `www` n'existe pas, créez-le.
    - Ajoutez la ressource à votre configuration Lovelace:
      - Via l'interface utilisateur: **Paramètres** > **Tableau de bord** > Cliquez sur le menu (**⋮**) > **Éditer le tableau de bord** > **Ressources** > **Ajouter une ressource**
        - URL: `/local/siri-next-departure-card.js`
        - Type: `JavaScript Module`
      - Ou ajoutez manuellement dans votre configuration YAML:
        ```yaml
        resources:
          - url: /local/siri-next-departure-card.js
            type: module
        ```

3.  **Dépendances Python** :
    L'intégration nécessite les bibliothèques Python suivantes : `httpx`, `xmltodict`, et `unidecode`. Celles-ci sont listées dans `manifest.json` et devraient être installées automatiquement par Home Assistant au démarrage après l'ajout de l'intégration. Si ce n'est pas le cas, vous pourriez avoir besoin de les installer manuellement dans l'environnement Python de Home Assistant.

4.  **Redémarrer Home Assistant** :
    Redémarrez votre instance Home Assistant pour qu'il puisse détecter et charger la nouvelle intégration.

## Configuration

1.  Allez dans **Paramètres** > **Appareils et services** dans Home Assistant.
2.  Cliquez sur le bouton **+ AJOUTER UNE INTÉGRATION**.
3.  Recherchez "SIRI Next Departures" et sélectionnez-la.
4.  Suivez les instructions à l'écran pour configurer l'intégration :

    - **URL du fichier NETEX** : L'URL complète pour télécharger le fichier XML NETEX contenant la description des arrêts.
    - **Endpoint de l'API SIRI** : L'URL de l'endpoint StopMonitoringService de votre API SIRI.
    - **Dataset ID** : L'ID de dataset ou la clé d'API nécessaire pour accéder à l'endpoint SIRI.

    L'intégration tentera de charger les arrêts à partir du fichier NETEX lors de la configuration initiale.

## Ajout de Capteurs d'Arrêts

Une fois l'intégration configurée

1.  Retournez à **Paramètres** > **Appareils et services**.
2.  Trouvez l'intégration "SIRI Next Departures" que vous venez d'ajouter.
3.  Cliquez sur le lien **CONFIGURER** (ou l'icône d'options).
4.  Vous verrez un menu. Choisissez **"Ajouter un capteur"**.
5.  Vous serez invité à fournir les informations suivantes :
    - **ID de l'arrêt (Stop ID)** : L'identifiant exact de l'arrêt tel que défini dans le fichier NETEX (par exemple, `ID_DU_QUAI`). Vous devez connaître cet ID.
    - **Nom de l'arrêt (Stop Name) (Optionnel)** : Un nom convivial pour ce capteur dans Home Assistant. Si laissé vide, le nom de l'arrêt provenant du fichier NETEX sera utilisé si possible, sinon l'ID de l'arrêt.
6.  Cliquez sur **Envoyer**.

Un nouveau capteur sera créé dans Home Assistant, affichant les prochains départs pour l'arrêt spécifié. Vous pouvez répéter cette opération pour ajouter autant de capteurs d'arrêts que nécessaire.

## État et Attributs du Capteur

- **État** : L'heure du prochain départ (par exemple, "10:15:00"). Affiche "No departures" si aucun départ n'est prévu ou si les données ne peuvent pas être récupérées.
- **Attributs** :
  - `stop_id`: L'ID de l'arrêt.
  - `stop_name`: Le nom de l'arrêt.
  - `last_update`: L'heure de la dernière mise à jour réussie des données.
  - `departures`: Une liste des prochains départs, chacun étant un dictionnaire contenant :
    - `line`: Numéro ou nom de la ligne.
    - `destination`: Destination du véhicule.
    - `expected_time`: Heure de départ prévue (peut inclure le retard).
    - `aimed_time`: Heure de départ théorique.
    - `vehicle_at_stop`: (Optionnel) Booléen indiquant si le véhicule est à l'arrêt.

## Utilisation de la Carte Lovelace Personnalisée

Une carte Lovelace personnalisée est disponible pour afficher les prochains départs de manière plus visuelle et intuitive.

### Ajout de la Carte au Tableau de Bord

1. Modifiez votre tableau de bord Lovelace
2. Cliquez sur **+ Ajouter une carte**
3. Recherchez **Carte des prochains départs SIRI**
4. Configurez la carte:
   - **Entité**: Sélectionnez un capteur SIRI Next Departures (ex: `sensor.next_departures_arret_mairie`)
   - **Nombre max de départs**: Définissez le nombre maximum de départs à afficher (par défaut: 5)

### Configuration YAML Manuelle

```yaml
type: 'custom:siri-next-departure-card'
entity: sensor.next_departures_arret_mairie
max_departures: 5
```

### Fonctionnalités de la Carte

- Affichage des prochains départs avec heure et temps d'attente
- Icônes adaptées au mode de transport (bus, tram, train, métro, ferry)
- Mise en page responsive et intuitive
- Personnalisation du nombre de départs affichés

Pour plus de détails sur la carte personnalisée, consultez le fichier `www/README.md`.
