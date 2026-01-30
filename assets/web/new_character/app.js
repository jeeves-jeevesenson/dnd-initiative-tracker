const STORAGE_KEY = "inittracker:new-character-draft";

const fields = {
  name: document.getElementById("character-name"),
  className: document.getElementById("character-class"),
  level: document.getElementById("character-level"),
  notes: document.getElementById("character-notes"),
};

const statusEl = document.getElementById("draft-status");
const button = document.getElementById("draft-button");

const loadDraft = () => {
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return;
  }
  try {
    const draft = JSON.parse(raw);
    if (draft && typeof draft === "object") {
      fields.name.value = draft.name || "";
      fields.className.value = draft.className || "";
      fields.level.value = draft.level || "1";
      fields.notes.value = draft.notes || "";
      statusEl.textContent = `Last saved ${draft.savedAt || "just now"}.`;
    }
  } catch (error) {
    console.warn("Unable to parse draft", error);
  }
};

const saveDraft = () => {
  const payload = {
    name: fields.name.value.trim(),
    className: fields.className.value.trim(),
    level: fields.level.value,
    notes: fields.notes.value.trim(),
    savedAt: new Date().toLocaleString(),
  };
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  statusEl.textContent = `Draft saved at ${payload.savedAt}.`;
};

button.addEventListener("click", saveDraft);

loadDraft();
