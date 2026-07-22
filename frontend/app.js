const estoniaCenter = [58.5953, 25.0136];

const map = L.map("map", { zoomControl: false }).setView(estoniaCenter, 7);
const locationsLayer = L.layerGroup().addTo(map);

L.control.zoom({ position: "bottomleft" }).addTo(map);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution:
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}).addTo(map);

let draftMarker = null;
let toastTimer = null;

const locationForm = document.querySelector("#location-form");
const submitButton = locationForm.querySelector("button[type='submit']");
const nameInput = document.querySelector("#name");
const latitudeInput = document.querySelector("#latitude");
const longitudeInput = document.querySelector("#longitude");
const latitudeManualInput = document.querySelector("#latitude-manual");
const longitudeManualInput = document.querySelector("#longitude-manual");
const selectedLocation = document.querySelector("#selected-location");
const formStatus = document.querySelector("#form-status");
const locationCount = document.querySelector("#location-count");
const toast = document.querySelector("#toast");


function createTextElement(tagName, text, className = "") {
  const element = document.createElement(tagName);
  element.textContent = text;

  if (className) {
    element.className = className;
  }

  return element;
}


function showToast(message) {
  window.clearTimeout(toastTimer);
  toast.textContent = message;
  toast.classList.add("is-visible");
  toastTimer = window.setTimeout(() => {
    toast.classList.remove("is-visible");
  }, 3200);
}


function formatTime(timestamp) {
  return timestamp ? timestamp.slice(11, 16) : "—";
}


function updateSelectedCoordinates(latitude, longitude) {
  const formattedLatitude = latitude.toFixed(6);
  const formattedLongitude = longitude.toFixed(6);

  latitudeInput.value = formattedLatitude;
  longitudeInput.value = formattedLongitude;
  latitudeManualInput.value = formattedLatitude;
  longitudeManualInput.value = formattedLongitude;
  selectedLocation.classList.add("is-selected");
  selectedLocation.lastElementChild.textContent =
    `${formattedLatitude}, ${formattedLongitude} · markerit saab lohistada`;
}


function placeDraftMarker(latitude, longitude) {
  const coordinates = [latitude, longitude];

  if (draftMarker) {
    draftMarker.setLatLng(coordinates);
  } else {
    draftMarker = L.marker(coordinates, { draggable: true })
      .addTo(map)
      .bindTooltip("Lohista täpsele kaadrikohale", { direction: "top" })
      .openTooltip();

    draftMarker.on("dragend", () => {
      const position = draftMarker.getLatLng();
      updateSelectedCoordinates(position.lat, position.lng);
    });
  }

  updateSelectedCoordinates(latitude, longitude);
}


function createConditionCard(label, value) {
  const card = document.createElement("div");
  card.className = "condition-card";
  card.append(
    createTextElement("small", label),
    createTextElement("strong", value),
  );
  return card;
}


async function deleteLocation(location, button) {
  const confirmed = window.confirm(
    `Kas kustutada võttepaik „${location.name}“? Seda toimingut ei saa tagasi võtta.`,
  );

  if (!confirmed) {
    return;
  }

  button.disabled = true;
  button.textContent = "Kustutan...";

  try {
    const response = await fetch(`/locations/${location.id}`, {
      method: "DELETE",
    });

    if (!response.ok) {
      throw new Error("Võttepaiga kustutamine ebaõnnestus.");
    }

    map.closePopup();
    await loadLocations();
    showToast(`„${location.name}“ kustutati.`);
  } catch (error) {
    console.error(error);
    button.disabled = false;
    button.textContent = "Kustuta võttepaik";
    showToast("Võttepaiga kustutamine ebaõnnestus.");
  }
}


function createPopupContent(location) {
  const container = document.createElement("div");
  container.className = "location-popup";

  const conditions = document.createElement("div");
  conditions.textContent = "Laadin võtteolusid...";

  const deleteButton = createTextElement(
    "button",
    "Kustuta võttepaik",
    "danger-button",
  );
  deleteButton.type = "button";
  deleteButton.addEventListener("click", () => {
    deleteLocation(location, deleteButton);
  });

  container.append(
    createTextElement("p", "Võttepaik", "popup-label"),
    createTextElement("h2", location.name),
    createTextElement("p", location.description || "Produktsioonimärkmed puuduvad."),
    createTextElement(
      "p",
      `${location.latitude.toFixed(5)}, ${location.longitude.toFixed(5)}`,
    ),
    createTextElement(
      "p",
      location.no_fly_zone_status
        ? "Drooni kasutamisel vajab õhuruum lisakontrolli."
        : "Drooni kasutamisel kontrolli alati kehtivaid lennupiiranguid.",
    ),
    createTextElement("p", "Võtteolud", "popup-label"),
    conditions,
    deleteButton,
  );

  return { container, conditions };
}


async function loadFlightConditions(locationId) {
  const response = await fetch(
    `/locations/${locationId}/flight-conditions`,
  );

  if (!response.ok) {
    throw new Error("Võtteolude laadimine ebaõnnestus.");
  }

  return response.json();
}


function showFlightConditions(container, data) {
  const { wind, sun } = data;
  const windValue = wind ? `${wind.speed_mps} m/s` : "Pole seadistatud";
  const grid = document.createElement("div");
  grid.className = "conditions-grid";
  grid.append(
    createConditionCard("Tuul", windValue),
    createConditionCard("Päikeseloojang", formatTime(sun.sunset)),
    createConditionCard(
      "Golden hour",
      `${formatTime(sun.golden_hour_evening.begin)}–${formatTime(sun.golden_hour_evening.end)}`,
    ),
    createConditionCard(
      "Blue hour",
      `${formatTime(sun.blue_hour_evening.begin)}–${formatTime(sun.blue_hour_evening.end)}`,
    ),
  );
  container.replaceChildren(grid);
}


async function loadLocations() {
  try {
    const response = await fetch("/locations");

    if (!response.ok) {
      throw new Error("Võttepaikade laadimine ebaõnnestus.");
    }

    const locations = await response.json();
    locationsLayer.clearLayers();
    locationCount.textContent =
      `${locations.length} ${locations.length === 1 ? "võttepaik" : "võttepaika"}`;

    for (const location of locations) {
      const popup = createPopupContent(location);
      const marker = L.marker([location.latitude, location.longitude])
        .addTo(locationsLayer)
        .bindPopup(popup.container, { maxWidth: 320, minWidth: 270 });

      marker.on("popupopen", async () => {
        try {
          const data = await loadFlightConditions(location.id);
          showFlightConditions(popup.conditions, data);
        } catch (error) {
          popup.conditions.textContent = "Võtteolusid ei õnnestunud laadida.";
          console.error(error);
        }
      });
    }
  } catch (error) {
    console.error(error);
    locationCount.textContent = "Ühendus puudub";
    showToast("Võttepaikade laadimine ebaõnnestus.");
  }
}


locationForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  if (!latitudeInput.value || !longitudeInput.value) {
    formStatus.textContent = "Vali enne salvestamist asukoht kaardil.";
    return;
  }

  const formData = new FormData(locationForm);
  const location = {
    name: formData.get("name"),
    latitude: Number(formData.get("latitude")),
    longitude: Number(formData.get("longitude")),
    description: formData.get("description") || null,
    no_fly_zone_status: formData.get("no-fly-zone-status") === "on",
  };

  submitButton.disabled = true;
  formStatus.textContent = "Salvestan võttepaika...";

  try {
    const response = await fetch("/locations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(location),
    });

    if (!response.ok) {
      throw new Error("Võttepaiga salvestamine ebaõnnestus.");
    }

    locationForm.reset();
    draftMarker?.remove();
    draftMarker = null;
    selectedLocation.classList.remove("is-selected");
    selectedLocation.lastElementChild.textContent = "Vali järgmine asukoht kaardil.";
    formStatus.textContent = "";
    await loadLocations();
    map.flyTo([location.latitude, location.longitude], 14);
    showToast(`„${location.name}“ salvestati.`);
  } catch (error) {
    console.error(error);
    formStatus.textContent = "Võttepaiga salvestamine ebaõnnestus.";
  } finally {
    submitButton.disabled = false;
  }
});


map.on("click", (event) => {
  placeDraftMarker(event.latlng.lat, event.latlng.lng);
  formStatus.textContent = "";
  nameInput.focus();
});


function updateDraftFromManualCoordinates() {
  const latitudeValue = latitudeManualInput.value;
  const longitudeValue = longitudeManualInput.value;

  if (!latitudeValue || !longitudeValue) {
    return;
  }

  const latitude = Number(latitudeValue);
  const longitude = Number(longitudeValue);

  if (
    Number.isFinite(latitude) &&
    Number.isFinite(longitude) &&
    latitude >= -90 &&
    latitude <= 90 &&
    longitude >= -180 &&
    longitude <= 180
  ) {
    placeDraftMarker(latitude, longitude);
    map.panTo([latitude, longitude]);
  }
}


latitudeManualInput.addEventListener("change", updateDraftFromManualCoordinates);
longitudeManualInput.addEventListener("change", updateDraftFromManualCoordinates);


loadLocations();
