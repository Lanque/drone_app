const estoniaCenter = [59.437, 24.7536];

const map = L.map("map", { zoomControl: false }).setView(estoniaCenter, 8);
const locationsLayer = L.layerGroup().addTo(map);
const markersById = new Map();

L.control.zoom({ position: "bottomleft" }).addTo(map);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution:
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}).addTo(map);

let draftMarker = null;
let toastTimer = null;
let isSelectingLocation = false;
let editingLocationId = null;
let viewerPhotos = [];
let viewerPhotoIndex = 0;
let authMode = "login";
let authenticatedUser = null;

const authScreen = document.querySelector("#auth-screen");
const authForm = document.querySelector("#auth-form");
const authTitle = document.querySelector("#auth-title");
const authIntro = document.querySelector("#auth-intro");
const authNameField = document.querySelector("#auth-name-field");
const authDisplayNameInput = document.querySelector("#auth-display-name");
const authEmailInput = document.querySelector("#auth-email");
const authPasswordInput = document.querySelector("#auth-password");
const authTermsField = document.querySelector("#auth-terms-field");
const authAcceptedTermsInput = document.querySelector("#auth-accepted-terms");
const authSubmitButton = document.querySelector("#auth-submit");
const authStatus = document.querySelector("#auth-status");
const toggleAuthModeButton = document.querySelector("#toggle-auth-mode");
const closeAuthPanelButton = document.querySelector("#close-auth-panel");
const googleLoginButton = document.querySelector("#google-login-button");
const guestActions = document.querySelector("#guest-actions");
const userActions = document.querySelector("#user-actions");
const openLoginButton = document.querySelector("#open-login");
const openRegisterButton = document.querySelector("#open-register");
const currentUserName = document.querySelector("#current-user-name");
const accountButton = document.querySelector("#account-button");
const logoutButton = document.querySelector("#logout-button");
const workspace = document.querySelector("#workspace");
const mapPanel = document.querySelector(".map-panel");
const sidePanel = document.querySelector("#side-panel");
const showLocationsButton = document.querySelector("#show-locations");
const startAddModeButton = document.querySelector("#start-add-mode");
const closePanelButton = document.querySelector("#close-panel");
const cancelMapSelectionButton = document.querySelector("#cancel-map-selection");
const openManualCoordsButton = document.querySelector("#open-manual-coords");
const selectionHint = document.querySelector("#selection-hint");
const panelTitle = document.querySelector("#panel-title");
const locationsView = document.querySelector("#locations-view");
const locationsList = document.querySelector("#locations-list");
const formView = document.querySelector("#form-view");
const locationForm = document.querySelector("#location-form");
const submitButton = locationForm.querySelector("button[type='submit']");
const nameInput = document.querySelector("#name");
const latitudeInput = document.querySelector("#latitude");
const longitudeInput = document.querySelector("#longitude");
const latitudeManualInput = document.querySelector("#latitude-manual");
const longitudeManualInput = document.querySelector("#longitude-manual");
const selectedLocation = document.querySelector("#selected-location");
const reselectOnMapButton = document.querySelector("#reselect-on-map");
const formStatus = document.querySelector("#form-status");
const noFlyZoneInput = document.querySelector("#no-fly-zone-status");
const locationCount = document.querySelector("#location-count");
const toast = document.querySelector("#toast");
const photoViewer = document.querySelector("#photo-viewer");
const photoViewerImage = document.querySelector("#photo-viewer-image");
const photoViewerCaption = document.querySelector("#photo-viewer-caption");
const closePhotoViewerButton = document.querySelector("#close-photo-viewer");
const previousPhotoButton = document.querySelector("#previous-photo");
const nextPhotoButton = document.querySelector("#next-photo");
const accountDialog = document.querySelector("#account-dialog");
const closeAccountDialogButton = document.querySelector("#close-account-dialog");
const accountEmail = document.querySelector("#account-email");
const deleteAccountButton = document.querySelector("#delete-account-button");
const accountStatus = document.querySelector("#account-status");


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


function setAuthMode(mode) {
  authMode = mode;
  const isRegistration = mode === "register";

  authTitle.textContent = isRegistration ? "Loo konto" : "Logi sisse";
  authIntro.textContent = isRegistration
    ? "Loo konto, et hoida enda võttepaigad teistest eraldi."
    : "Sinu võttepaigad, fotod ja võtteolud ühes kohas.";
  authNameField.hidden = !isRegistration;
  authDisplayNameInput.required = isRegistration;
  authTermsField.hidden = !isRegistration;
  authAcceptedTermsInput.required = isRegistration;

  if (!isRegistration) {
    authAcceptedTermsInput.checked = false;
  }

  authPasswordInput.autocomplete = isRegistration
    ? "new-password"
    : "current-password";
  authSubmitButton.textContent = isRegistration
    ? "Loo konto"
    : "Logi sisse";
  toggleAuthModeButton.textContent = isRegistration
    ? "Mul on juba konto"
    : "Loo uus konto";
  authStatus.textContent = "";
}


async function getApiError(response, fallbackMessage) {
  try {
    const errorData = await response.json();
    return errorData.detail || fallbackMessage;
  } catch {
    return fallbackMessage;
  }
}


async function login(email, password) {
  const response = await fetch("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ email, password }),
  });

  if (!response.ok) {
    throw new Error(
      await getApiError(response, "Sisselogimine ebaõnnestus."),
    );
  }

  return response.json();
}


async function showAuthenticatedApp(user) {
  authenticatedUser = user;
  currentUserName.textContent = user.display_name;
  accountEmail.textContent = user.email;
  guestActions.hidden = true;
  userActions.hidden = false;
  authScreen.hidden = true;

  window.requestAnimationFrame(() => {
    map.invalidateSize();
  });

  await loadLocations();
}


function openAuthenticationPanel(mode = "login") {
  setAuthMode(mode);
  authScreen.hidden = false;
  window.requestAnimationFrame(() => {
    if (mode === "register") {
      authDisplayNameInput.focus();
    } else {
      authEmailInput.focus();
    }
  });
}


function showLoggedOutApp() {
  authenticatedUser = null;
  guestActions.hidden = false;
  userActions.hidden = true;
  authScreen.hidden = true;
  currentUserName.textContent = "";
  locationCount.textContent = "Logi sisse, et näha asukohti";
  locationsLayer.clearLayers();
  markersById.clear();
  closePanel();
  setAuthMode("login");
  authPasswordInput.value = "";

  if (accountDialog.open) {
    accountDialog.close();
  }
}


async function initializeAuthentication() {
  const queryParameters = new URLSearchParams(window.location.search);
  const authError = queryParameters.get("auth_error");

  if (authError) {
    window.history.replaceState({}, "", "/");
  }

  try {
    const response = await fetch("/auth/me", {
      credentials: "same-origin",
    });

    if (!response.ok) {
      showLoggedOutApp();

      if (authError) {
        openAuthenticationPanel("login");
        authStatus.textContent =
          "Google'iga sisselogimine ebaõnnestus. Proovi uuesti.";
      }

      return;
    }

    await showAuthenticatedApp(await response.json());
  } catch (error) {
    console.error(error);
    showLoggedOutApp();
    showToast("Serveriga ei õnnestunud ühendust saada.");
  }
}


function updatePhotoViewer() {
  const photo = viewerPhotos[viewerPhotoIndex];

  if (!photo) {
    return;
  }

  photoViewerImage.src = photo.url;
  photoViewerImage.alt = photo.caption || photo.original_name;
  photoViewerCaption.textContent = photo.caption || photo.original_name;
  previousPhotoButton.disabled = viewerPhotoIndex === 0;
  nextPhotoButton.disabled = viewerPhotoIndex === viewerPhotos.length - 1;
}


function openPhotoViewer(photos, photoIndex) {
  viewerPhotos = photos;
  viewerPhotoIndex = photoIndex;
  updatePhotoViewer();
  photoViewer.showModal();
}


function closePhotoViewer() {
  photoViewer.close();
  photoViewerImage.removeAttribute("src");
  viewerPhotos = [];
}


function formatTime(timestamp) {
  return timestamp ? timestamp.slice(11, 16) : "—";
}


function openPanel(view) {
  workspace.classList.add("is-panel-open");
  const isFormView = view === "form";
  sidePanel.classList.toggle("side-panel--form", isFormView);
  locationsView.hidden = isFormView;
  formView.hidden = !isFormView;
  panelTitle.textContent = isFormView
    ? editingLocationId === null ? "Uus võttepaik" : "Muuda võttepaika"
    : "Asukohad";
}


function closePanel() {
  workspace.classList.remove("is-panel-open");
}


function resetDraft() {
  draftMarker?.remove();
  draftMarker = null;
  editingLocationId = null;
  locationForm.reset();
  submitButton.textContent = "Salvesta";
  selectedLocation.classList.remove("is-selected");
  selectedLocation.textContent = "Vali asukoht kaardil.";
  if (reselectOnMapButton) {
    reselectOnMapButton.hidden = true;
  }
  formStatus.textContent = "";
}


function setSelectionMode(enabled, autoOpenForm = false) {
  isSelectingLocation = enabled;
  mapPanel.classList.toggle("is-selecting", enabled);
  selectionHint.hidden = !enabled;

  if (enabled && autoOpenForm) {
    openPanel("form");
  } else if (!enabled && reselectOnMapButton) {
    reselectOnMapButton.hidden = true;
  }
}


function cancelSelection() {
  resetDraft();
  setSelectionMode(false);
  closePanel();
}


function updateSelectedCoordinates(latitude, longitude) {
  const formattedLatitude = latitude.toFixed(6);
  const formattedLongitude = longitude.toFixed(6);

  latitudeInput.value = formattedLatitude;
  longitudeInput.value = formattedLongitude;
  latitudeManualInput.value = formattedLatitude;
  longitudeManualInput.value = formattedLongitude;
  selectedLocation.classList.add("is-selected");
  selectedLocation.textContent =
    `Valitud: ${formattedLatitude}, ${formattedLongitude}`;
}


function placeDraftMarker(latitude, longitude) {
  const coordinates = [latitude, longitude];

  if (draftMarker) {
    draftMarker.setLatLng(coordinates);
  } else {
    draftMarker = L.marker(coordinates, { draggable: true })
      .addTo(map)
      .bindTooltip("Lohista marker täpsele kaadrikohale", { direction: "top" })
      .openTooltip();

    draftMarker.on("dragend", () => {
      const position = draftMarker.getLatLng();
      updateSelectedCoordinates(position.lat, position.lng);
    });
  }

  updateSelectedCoordinates(latitude, longitude);
  if (window.innerWidth > 820) {
    nameInput.focus();
  }
}


function createConditionCard(label, value) {
  const card = document.createElement("div");
  card.className = "condition-card";
  card.append(createTextElement("small", label), createTextElement("strong", value));
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
    const response = await fetch(`/locations/${location.id}`, { method: "DELETE" });

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

function getStreetViewUrl(location) {
  const parameters = new URLSearchParams({
    api: "1",
    map_action: "pano",
    viewpoint: `${location.latitude},${location.longitude}`,
    heading: "0",
    pitch: "0",
    fov: "90",
  });

  return `https://www.google.com/maps/@?${parameters}`;
}

function startEditing(location) {
  resetDraft();
  editingLocationId = location.id;
  setSelectionMode(false);

  nameInput.value = location.name;
  document.querySelector("#description").value = location.description || "";
  noFlyZoneInput.checked = location.no_fly_zone_status;
  placeDraftMarker(location.latitude, location.longitude);

  selectedLocation.textContent =
    "Muudad olemasolevat võttepaika. Vajadusel lohista marker uude kohta.";
  submitButton.textContent = "Salvesta muudatused";
  openPanel("form");
}


function createPopupContent(location, onLayoutChange) {
  const container = document.createElement("div");
  container.className = "location-popup";

  const conditions = document.createElement("div");
  conditions.textContent = "Laadin võtteolusid...";

  const photoGallery = document.createElement("div");
  photoGallery.textContent = "Laadin pilte...";
  const photoUploadForm = createPhotoUploadForm(
    location,
    photoGallery,
    onLayoutChange,
  );
  const showPhotoUploadButton = createTextElement("button", "Lisa pilt", "show-photo-upload-button");
  photoUploadForm.hidden = true;
  showPhotoUploadButton.type = "button";
  showPhotoUploadButton.addEventListener("click", () => {
    const willShowForm = photoUploadForm.hidden;
    photoUploadForm.hidden = !willShowForm;
    showPhotoUploadButton.textContent = willShowForm ? "Peida lisamine" : "Lisa pilt";
    onLayoutChange();
  });

  const deleteButton = createTextElement("button", "Kustuta võttepaik", "danger-button");
  deleteButton.type = "button";
  deleteButton.addEventListener("click", () => deleteLocation(location, deleteButton));

  const editButton = createTextElement("button", "Muuda võttepaika", "edit-button");
  editButton.type = "button";
  editButton.addEventListener("click", () => {
    map.closePopup();
    startEditing(location);
  });

  const streetViewLink = document.createElement("a");
  streetViewLink.href = getStreetViewUrl(location);
  streetViewLink.target = "_blank";
  streetViewLink.rel = "noopener noreferrer";
  streetViewLink.textContent = "Ava Street View";
  streetViewLink.className = "street-view-link";

  container.append(
    createTextElement("p", "Võttepaik", "popup-label"),
    createTextElement("h2", location.name),
    createTextElement("p", location.description || "Produktsioonimärkmed puuduvad."),
    createTextElement("p", `${location.latitude.toFixed(5)}, ${location.longitude.toFixed(5)}`),
    createTextElement("p", location.no_fly_zone_status
      ? "Drooni kasutamisel vajab õhuruum lisakontrolli."
      : "Drooni kasutamisel kontrolli alati kehtivaid lennupiiranguid."),
    createTextElement("p", "Võtteolud", "popup-label"),
    conditions,
    createTextElement("p", "Fotod", "popup-label"),
    photoGallery,
    showPhotoUploadButton,
    photoUploadForm,
    streetViewLink,
    editButton,
    deleteButton,
  );

  return { container, conditions, photoGallery };
}


async function loadFlightConditions(locationId) {
  const response = await fetch(`/locations/${locationId}/flight-conditions`);

  if (!response.ok) {
    throw new Error("Võtteolude laadimine ebaõnnestus.");
  }

  return response.json();
}


async function loadLocationPhotos(locationId) {
  const response = await fetch(`/locations/${locationId}/photos`);

  if (!response.ok) {
    throw new Error("Võttepaiga piltide laadimine ebaõnnestus.");
  }

  return response.json();
}


async function uploadLocationPhoto(locationId, file, caption) {
  const formData = new FormData();
  formData.append("photo", file);

  if (caption) {
    formData.append("caption", caption);
  }

  const response = await fetch(`/locations/${locationId}/photos`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(
      await getApiError(
        response,
        "Pildi üleslaadimine ebaõnnestus.",
      ),
    );
  }

  return response.json();
}


async function deleteLocationPhoto(
  photo,
  galleryContainer,
  button,
  onLayoutChange,
) {
  const confirmed = window.confirm(
    `Kas eemaldada pilt „${photo.original_name}“?`,
  );

  if (!confirmed) {
    return;
  }

  button.disabled = true;
  button.textContent = "Eemaldan...";

  try {
    const response = await fetch(
      `/locations/${photo.location_id}/photos/${photo.id}`,
      { method: "DELETE" },
    );

    if (!response.ok) {
      throw new Error("Pildi eemaldamine ebaõnnestus.");
    }

    const photos = await loadLocationPhotos(photo.location_id);
    showLocationPhotos(galleryContainer, photos, onLayoutChange);
    showToast("Pilt eemaldati.");
  } catch (error) {
    console.error(error);
    button.disabled = false;
    button.textContent = "Eemalda";
    showToast("Pildi eemaldamine ebaõnnestus.");
  }
}


function showFlightConditions(container, data) {
  const { wind, sun } = data;
  const grid = document.createElement("div");
  grid.className = "conditions-grid";
  grid.append(
    createConditionCard("Tuul", wind ? `${wind.speed_mps} m/s` : "Pole seadistatud"),
    createConditionCard("Päikeseloojang", formatTime(sun.sunset)),
    createConditionCard("Golden hour", `${formatTime(sun.golden_hour_evening.begin)}–${formatTime(sun.golden_hour_evening.end)}`),
    createConditionCard("Blue hour", `${formatTime(sun.blue_hour_evening.begin)}–${formatTime(sun.blue_hour_evening.end)}`),
  );
  container.replaceChildren(grid);
}


function showLocationPhotos(container, photos, onLayoutChange = () => {}) {
  if (photos.length === 0) {
    container.replaceChildren(
      createTextElement("p", "Pilte pole veel lisatud.", "empty-photo-gallery"),
    );
    onLayoutChange();
    return;
  }

  const gallery = document.createElement("div");
  gallery.className = "photo-gallery";

  for (const [photoIndex, photo] of photos.entries()) {
    const item = document.createElement("div");
    const removeButton = createTextElement("button", "Eemalda", "remove-photo-button");
    const imageButton = document.createElement("button");
    const image = document.createElement("img");

    imageButton.type = "button";
    imageButton.className = "photo-thumbnail";
    imageButton.title = `Ava pilt: ${photo.caption || photo.original_name}`;
    imageButton.addEventListener("click", () => openPhotoViewer(photos, photoIndex));

    image.src = photo.url;
    image.alt = photo.caption || photo.original_name;

    imageButton.append(image);
    removeButton.type = "button";
    removeButton.addEventListener("click", () =>
      deleteLocationPhoto(
        photo,
        container,
        removeButton,
        onLayoutChange,
      ),
    );
    item.className = "photo-gallery__item";
    item.append(imageButton, removeButton);
    gallery.append(item);
  }

  container.replaceChildren(gallery);
  onLayoutChange();
}


function getLocationPopupOptions() {
  const isMobile = window.innerWidth <= 820;
  const availableWidth = Math.max(220, window.innerWidth - (isMobile ? 32 : 48));
  const popupWidth = Math.min(380, availableWidth);

  return {
    maxWidth: popupWidth,
    minWidth: Math.min(220, popupWidth),
    autoPanPaddingTopLeft: isMobile ? [12, 64] : [20, 82],
    autoPanPaddingBottomRight: isMobile ? [12, 12] : [20, 20],
  };
}


function keepPopupInsideMap(marker) {
  window.requestAnimationFrame(() => {
    if (!marker?.isPopupOpen()) {
      return;
    }

    const popup = marker.getPopup();
    popup.update();

    window.requestAnimationFrame(() => {
      const popupElement = popup.getElement();

      if (!popupElement) {
        return;
      }

      const popupBounds = popupElement.getBoundingClientRect();
      const mapBounds = map.getContainer().getBoundingClientRect();
      const padding = 16;
      let horizontalOffset = 0;
      let verticalOffset = 0;

      if (popupBounds.left < mapBounds.left + padding) {
        horizontalOffset = popupBounds.left - mapBounds.left - padding;
      } else if (popupBounds.right > mapBounds.right - padding) {
        horizontalOffset = popupBounds.right - mapBounds.right + padding;
      }

      if (popupBounds.top < mapBounds.top + padding) {
        verticalOffset = popupBounds.top - mapBounds.top - padding;
      } else if (popupBounds.bottom > mapBounds.bottom - padding) {
        verticalOffset = popupBounds.bottom - mapBounds.bottom + padding;
      }

      if (horizontalOffset !== 0 || verticalOffset !== 0) {
        map.panBy(
          [horizontalOffset, verticalOffset],
          { animate: true },
        );
      }
    });
  });
}


function createPhotoUploadForm(location, galleryContainer, onLayoutChange) {
  const form = document.createElement("form");
  const fileInput = document.createElement("input");
  const captionInput = document.createElement("input");
  const submitButton = createTextElement("button", "Laadi pilt üles", "upload-photo-button");
  const status = createTextElement("p", "", "photo-upload-status");

  form.className = "photo-upload-form";
  fileInput.type = "file";
  fileInput.accept = "image/*,.heic,.heif";
  fileInput.required = true;
  fileInput.setAttribute("aria-label", "Vali pildifail");
  captionInput.type = "text";
  captionInput.maxLength = 500;
  captionInput.placeholder = "Pildi kirjeldus (valikuline)";
  submitButton.type = "submit";

  form.append(fileInput, captionInput, submitButton, status);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const file = fileInput.files[0];

    if (!file) {
      status.textContent = "Vali pilt enne üleslaadimist.";
      return;
    }

    submitButton.disabled = true;
    status.textContent = "Laen pilti üles...";

    try {
      await uploadLocationPhoto(location.id, file, captionInput.value.trim());
      const photos = await loadLocationPhotos(location.id);
      showLocationPhotos(galleryContainer, photos, onLayoutChange);
      form.reset();
      status.textContent = "Pilt lisati.";
      showToast("Pilt lisati võttepaigale.");
    } catch (error) {
      console.error(error);
      status.textContent = error.message;
    } finally {
      submitButton.disabled = false;
    }
  });

  return form;
}


function focusLocation(location) {
  const coordinates = [location.latitude, location.longitude];
  const marker = markersById.get(location.id);

  map.once("moveend", () => {
    marker?.openPopup();
    keepPopupInsideMap(marker);
  });
  map.flyTo(coordinates, 15);
  closePanel();
}


function renderLocationsList(locations) {
  locationsList.replaceChildren();

  if (locations.length === 0) {
    locationsList.append(createTextElement("p", "Salvestatud võttepaiku veel pole.", "empty-list"));
    return;
  }

  for (const location of locations) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "location-list-item";
    item.append(
      createTextElement("strong", location.name),
      createTextElement("span", location.description || "Märkmed puuduvad"),
    );
    item.addEventListener("click", () => focusLocation(location));
    locationsList.append(item);
  }
}


async function loadLocations() {
  try {
    const response = await fetch("/locations");

    if (!response.ok) {
      throw new Error("Võttepaikade laadimine ebaõnnestus.");
    }

    const locations = await response.json();
    locationsLayer.clearLayers();
    markersById.clear();
    locationCount.textContent = `${locations.length} ${locations.length === 1 ? "võttepaik" : "võttepaika"}`;
    renderLocationsList(locations);

    for (const location of locations) {
      let marker;
      const refreshPopupLayout = () => {
        keepPopupInsideMap(marker);
      };
      const popup = createPopupContent(location, refreshPopupLayout);
      marker = L.marker([location.latitude, location.longitude])
        .addTo(locationsLayer)
        .bindPopup(popup.container, getLocationPopupOptions());

      markersById.set(location.id, marker);
      marker.on("popupopen", () => {
        loadFlightConditions(location.id)
          .then((data) => {
            showFlightConditions(popup.conditions, data);
            refreshPopupLayout();
          })
          .catch((error) => {
            popup.conditions.textContent = "Võtteolusid ei õnnestunud laadida.";
            console.error(error);
            refreshPopupLayout();
          });

        loadLocationPhotos(location.id)
          .then((photos) =>
            showLocationPhotos(
              popup.photoGallery,
              photos,
              refreshPopupLayout,
            ),
          )
          .catch((error) => {
            popup.photoGallery.textContent = "Pilte ei õnnestunud laadida.";
            console.error(error);
            refreshPopupLayout();
          });
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
  const isEditing = editingLocationId !== null;
  const requestUrl = isEditing ? `/locations/${editingLocationId}` : "/locations";
  const requestMethod = isEditing ? "PATCH" : "POST";

  submitButton.disabled = true;
  formStatus.textContent = isEditing ? "Salvestan muudatusi..." : "Salvestan...";

  try {
    const response = await fetch(requestUrl, {
      method: requestMethod,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(location),
    });

    if (!response.ok) {
      throw new Error("Võttepaiga salvestamine ebaõnnestus.");
    }

    await loadLocations();
    map.flyTo([location.latitude, location.longitude], 14);
    showToast(
      isEditing ? `„${location.name}“ muudeti.` : `„${location.name}“ salvestati.`,
    );
    resetDraft();
    setSelectionMode(false);
    closePanel();
  } catch (error) {
    console.error(error);
    formStatus.textContent = "Võttepaiga salvestamine ebaõnnestus.";
  } finally {
    submitButton.disabled = false;
  }
});


showLocationsButton.addEventListener("click", () => {
  if (!authenticatedUser) {
    openAuthenticationPanel("login");
    return;
  }

  setSelectionMode(false);
  openPanel("locations");
});

startAddModeButton.addEventListener("click", () => {
  if (!authenticatedUser) {
    openAuthenticationPanel("login");
    return;
  }

  resetDraft();
  closePanel();
  setSelectionMode(true, false);
});

closePanelButton.addEventListener("click", () => {
  if (isSelectingLocation) {
    cancelSelection();
  } else {
    resetDraft();
    closePanel();
  }
});

cancelMapSelectionButton.addEventListener("click", cancelSelection);

openManualCoordsButton?.addEventListener("click", () => {
  openPanel("form");
  const coordDetails = document.querySelector(".coordinate-details");
  if (coordDetails) {
    coordDetails.open = true;
  }
  if (window.innerWidth > 820) {
    latitudeManualInput.focus();
  }
});

reselectOnMapButton?.addEventListener("click", () => {
  closePanel();
});


map.on("click", (event) => {
  if (!isSelectingLocation) {
    return;
  }

  placeDraftMarker(event.latlng.lat, event.latlng.lng);
  formStatus.textContent = "";
  if (reselectOnMapButton) {
    reselectOnMapButton.hidden = false;
  }
  openPanel("form");
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
    Number.isFinite(latitude) && Number.isFinite(longitude) &&
    latitude >= -90 && latitude <= 90 &&
    longitude >= -180 && longitude <= 180
  ) {
    placeDraftMarker(latitude, longitude);
    map.panTo([latitude, longitude]);
    if (reselectOnMapButton) {
      reselectOnMapButton.hidden = false;
    }
  }
}


latitudeManualInput.addEventListener("input", updateDraftFromManualCoordinates);
longitudeManualInput.addEventListener("input", updateDraftFromManualCoordinates);
latitudeManualInput.addEventListener("change", updateDraftFromManualCoordinates);
longitudeManualInput.addEventListener("change", updateDraftFromManualCoordinates);


toggleAuthModeButton.addEventListener("click", () => {
  setAuthMode(authMode === "login" ? "register" : "login");
});

openLoginButton.addEventListener("click", () => {
  openAuthenticationPanel("login");
});

openRegisterButton.addEventListener("click", () => {
  openAuthenticationPanel("register");
});

closeAuthPanelButton.addEventListener("click", () => {
  authScreen.hidden = true;
});

googleLoginButton.addEventListener("click", () => {
  window.location.assign("/auth/google");
});


authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  authSubmitButton.disabled = true;
  authStatus.textContent = authMode === "register"
    ? "Loon kontot..."
    : "Login sisse...";

  const email = authEmailInput.value.trim();
  const password = authPasswordInput.value;

  try {
    if (authMode === "register") {
      const registrationResponse = await fetch("/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({
          email,
          display_name: authDisplayNameInput.value.trim(),
          password,
          accepted_terms: authAcceptedTermsInput.checked,
        }),
      });

      if (!registrationResponse.ok) {
        throw new Error(
          await getApiError(
            registrationResponse,
            "Konto loomine ebaõnnestus.",
          ),
        );
      }
    }

    const user = await login(email, password);
    authForm.reset();
    await showAuthenticatedApp(user);
  } catch (error) {
    console.error(error);
    authStatus.textContent = error.message;
  } finally {
    authSubmitButton.disabled = false;
  }
});


logoutButton.addEventListener("click", async () => {
  logoutButton.disabled = true;

  try {
    await fetch("/auth/logout", {
      method: "POST",
      credentials: "same-origin",
    });
  } finally {
    logoutButton.disabled = false;
    showLoggedOutApp();
  }
});


accountButton.addEventListener("click", () => {
  accountStatus.textContent = "";
  accountDialog.showModal();
});

closeAccountDialogButton.addEventListener("click", () => {
  accountDialog.close();
});

accountDialog.addEventListener("click", (event) => {
  if (event.target === accountDialog) {
    accountDialog.close();
  }
});

deleteAccountButton.addEventListener("click", async () => {
  const confirmed = window.confirm(
    "Kas kustutada jäädavalt sinu konto, kõik võttepaigad ja fotod?",
  );

  if (!confirmed) {
    return;
  }

  deleteAccountButton.disabled = true;
  accountStatus.textContent = "Kustutan kontot...";

  try {
    const response = await fetch("/auth/account", {
      method: "DELETE",
      credentials: "same-origin",
    });

    if (!response.ok) {
      throw new Error(
        await getApiError(
          response,
          "Konto kustutamine ebaõnnestus.",
        ),
      );
    }

    accountDialog.close();
    showLoggedOutApp();
    showToast("Konto ja sellega seotud andmed kustutati.");
  } catch (error) {
    console.error(error);
    accountStatus.textContent = error.message;
  } finally {
    deleteAccountButton.disabled = false;
  }
});


initializeAuthentication();


closePhotoViewerButton.addEventListener("click", closePhotoViewer);
previousPhotoButton.addEventListener("click", () => {
  if (viewerPhotoIndex > 0) {
    viewerPhotoIndex -= 1;
    updatePhotoViewer();
  }
});
nextPhotoButton.addEventListener("click", () => {
  if (viewerPhotoIndex < viewerPhotos.length - 1) {
    viewerPhotoIndex += 1;
    updatePhotoViewer();
  }
});
photoViewer.addEventListener("click", (event) => {
  if (event.target === photoViewer) {
    closePhotoViewer();
  }
});

window.addEventListener("scroll", () => {
  if (window.scrollY !== 0) {
    window.scrollTo(0, 0);
  }
});

document.addEventListener("focusout", (event) => {
  if (
    event.target.tagName === "INPUT" ||
    event.target.tagName === "TEXTAREA"
  ) {
    window.scrollTo(0, 0);
  }
});
