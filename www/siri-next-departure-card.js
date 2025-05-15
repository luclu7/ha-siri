class SiriNextDepartureCard extends HTMLElement {
  set hass(hass) {
    if (!this.content) {
      this.innerHTML = `
        <ha-card>
          <div class="card-header"></div>
          <div class="card-content">
            <div class="departure-list"></div>
          </div>
        </ha-card>
      `;
      this.content = this.querySelector("div.card-content");
      this.header = this.querySelector("div.card-header");
      this.departureList = this.querySelector("div.departure-list");

      const style = document.createElement("style");
      style.textContent = `
        .departure-list {
          width: 100%;
          border-spacing: 0;
        }
        .departure-item {
          display: flex;
          align-items: center;
          padding: 8px 0;
          border-bottom: 1px solid var(--divider-color, rgba(0,0,0,0.12));
        }
        .departure-item:last-child {
          border-bottom: none;
        }
        .departure-time {
          font-size: 1.2em;
          font-weight: bold;
          margin-right: 16px;
          min-width: 55px;
        }
        .departure-eta {
          font-size: 0.9em;
          color: var(--secondary-text-color);
          margin-left: auto;
          padding-left: 8px;
        }
        .departure-line {
          font-weight: bold;
          padding: 2px 8px;
          border-radius: 4px;
          margin-right: 8px;
          color: white;
          background-color: var(--primary-color);
          min-width: 30px;
          text-align: center;
        }
        .departure-destination {
          flex-grow: 1;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .icon-container {
          margin-right: 8px;
        }
        .no-departures {
          color: var(--secondary-text-color);
          font-style: italic;
          padding: 16px 0;
          text-align: center;
        }
      `;
      this.appendChild(style);
    }

    const config = this._config;
    const entityId = config.entity;
    const entity = hass.states[entityId];

    if (!entity) {
      this.header.textContent = `Entité non trouvée: ${entityId}`;
      this.departureList.innerHTML = "";
      return;
    }

    // Afficher le nom de l'arrêt dans l'en-tête
    const stopName =
      entity.attributes.stop_name || entity.attributes.friendly_name;
    this.header.textContent = stopName;

    // Récupérer les départs
    const departures = entity.attributes.departures || [];

    if (departures.length === 0) {
      this.departureList.innerHTML =
        '<div class="no-departures">Aucun départ prévu</div>';
      return;
    }

    // Vider la liste actuelle
    this.departureList.innerHTML = "";

    // Limiter le nombre de départs affichés si configuré
    const limit = config.max_departures || departures.length;
    const departuresLimited = departures.slice(0, limit);

    // Ajouter chaque départ à la liste
    departuresLimited.forEach((departure) => {
      const departureItem = document.createElement("div");
      departureItem.className = "departure-item";

      // Obtenir l'heure de départ et calculer le délai d'attente
      const departureTime = new Date(departure.expected_departure_time);
      const now = new Date();
      const waitMinutes = Math.round((departureTime - now) / 60000);
      const formattedTime = departureTime.toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      });

      // Déterminer l'icône en fonction du mode de transport
      let icon = "mdi:bus";
      // Utiliser d'abord le mode de transport du référentiel des lignes s'il est disponible
      const transportMode = (departure.line_transport_mode || departure.vehicle_mode || "").toLowerCase();
      if (transportMode.includes("tram")) {
        icon = "mdi:tram";
      } else if (
        transportMode.includes("rail") ||
        transportMode.includes("train")
      ) {
        icon = "mdi:train";
      } else if (
        transportMode.includes("metro") ||
        transportMode.includes("subway")
      ) {
        icon = "mdi:subway";
      } else if (
        transportMode.includes("ferry") ||
        transportMode.includes("boat")
      ) {
        icon = "mdi:ferry";
      }
      
      // Créer le contenu HTML pour l'élément de départ
      departureItem.innerHTML = `
        <div class="icon-container">
          <ha-icon icon="${icon}"></ha-icon>
        </div>
        <div class="departure-time">${formattedTime}</div>
        <div class="departure-line" style="${
          departure.line_color ? `background-color: ${departure.line_color};` : ''
        }${
          departure.line_text_color ? `color: ${departure.line_text_color};` : ''
        }">${
          departure.line_public_code || departure.published_line_name || departure.line_ref || "-"
        }</div>
        <div class="departure-destination">${
          departure.destination_name || "Inconnu"
        }</div>
        <div class="departure-eta">${
          waitMinutes > 0 ? `${waitMinutes} min` : "À l'arrêt"
        }</div>
      `;

      // Ajouter au DOM
      this.departureList.appendChild(departureItem);
    });
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error("Vous devez définir une entité");
    }
    this._config = config;
  }

  getCardSize() {
    const config = this._config;
    const limit = config.max_departures || 5; // par défaut 5 départs
    return 1 + Math.min(limit, 7); // en-tête + départs (max 7 pour le calcul de taille)
  }

  static getConfigElement() {
    return document.createElement("siri-next-departure-card-editor");
  }

  static getStubConfig() {
    return {
      entity: "",
      max_departures: 5,
    };
  }
}

// Définition de l'éditeur de configuration pour Lovelace UI
class SiriNextDepartureCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
    this.render();
  }

  get _entity() {
    return this._config.entity || "";
  }

  get _max_departures() {
    return this._config.max_departures || 5;
  }

  render() {
    if (!this._config) {
      return;
    }

    this.innerHTML = `
      <style>
        .form {
          display: flex;
          flex-direction: column;
        }
        .row {
          display: flex;
          flex-direction: row;
          margin: 5px 0;
          align-items: center;
        }
        .label {
          width: 130px;
          font-weight: 500;
        }
        ha-entity-picker {
          width: 100%;
        }
        ha-textfield {
          width: 100px;
        }
      </style>
      <div class="form">
        <div class="row">
          <label class="label">Entité:</label>
          <ha-entity-picker
            .hass=${this.hass}
            .value=${this._entity}
            .configValue=${"entity"}
            include-domains='sensor'
            @change=${this._valueChanged}
            allow-custom-entity
          ></ha-entity-picker>
        </div>
        <div class="row">
          <label class="label">Nombre max de départs:</label>
          <ha-textfield
            .value=${this._max_departures}
            .configValue=${"max_departures"}
            @input=${this._valueChanged}
            type="number"
            min="1"
            max="10"
          ></ha-textfield>
        </div>
      </div>
    `;
  }

  _valueChanged(ev) {
    if (!this._config || !this.hass) {
      return;
    }

    const target = ev.target;
    if (!target.configValue) {
      return;
    }

    // Mettre à jour la configuration avec la nouvelle valeur
    if (target.configValue === "max_departures") {
      this._config.max_departures = parseInt(target.value) || 5;
    } else {
      this._config[target.configValue] = target.value;
    }

    // Dispatcher un événement pour informer le panneau Lovelace du changement
    this.dispatchEvent(
      new CustomEvent("config-changed", { detail: { config: this._config } })
    );
  }
}

// Enregistrer la carte et l'éditeur
customElements.define("siri-next-departure-card", SiriNextDepartureCard);
customElements.define(
  "siri-next-departure-card-editor",
  SiriNextDepartureCardEditor
);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "siri-next-departure-card",
  name: "Carte des prochains départs SIRI",
  description:
    "Affiche les prochains départs des transports en commun à partir d'un capteur SIRI",
});
