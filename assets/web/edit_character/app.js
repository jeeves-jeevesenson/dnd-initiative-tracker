const statusEl = document.getElementById("draft-status");
const exportButton = document.getElementById("export-button");
const refreshCacheButton = document.getElementById("refresh-cache-button");
const overwriteButton = document.getElementById("overwrite-button");
const formEl = document.getElementById("character-form");
const filenameInput = document.getElementById("filename-input");

const clone = (value) => JSON.parse(JSON.stringify(value));

const SPELL_PICKER_PATHS = new Set([
  "spellcasting.cantrips.known",
  "spellcasting.known_spells.known",
  "spellcasting.prepared_spells.prepared",
]);
const CLASS_OPTIONS = ["Barbarian", "Bard", "Cleric", "Druid", "Fighter", "Monk", "Paladin", "Ranger", "Rogue", "Sorcerer", "Warlock", "Wizard"];
const SPELL_SLOT_LEVELS = [
  { key: "1", label: "I" },
  { key: "2", label: "II" },
  { key: "3", label: "III" },
  { key: "4", label: "IV" },
  { key: "5", label: "V" },
  { key: "6", label: "VI" },
  { key: "7", label: "VII" },
  { key: "8", label: "VIII" },
  { key: "9", label: "IX" },
];

const spellPathKey = (path) => path.join(".");
const isSpellPickerPath = (path) => SPELL_PICKER_PATHS.has(spellPathKey(path));
const isSpellSlotsPath = (path) => spellPathKey(path) === "spellcasting.spell_slots";

const getFieldPlaceholder = (field) => field.placeholder || field.example || "";
const getFieldHelpText = (field) => field.help || (field.example ? `Example: ${field.example}` : "");

const appendHelpText = (container, field) => {
  const helpText = getFieldHelpText(field);
  if (!helpText) {
    return;
  }
  const help = document.createElement("p");
  help.className = "field-help";
  help.textContent = helpText;
  container.appendChild(help);
};

const loadSpellIds = (() => {
  let cache = null;
  let inflight = null;
  return async () => {
    if (cache) {
      return cache;
    }
    if (inflight) {
      return inflight;
    }
    inflight = fetch("/api/spells")
      .then((response) => {
        if (!response.ok) {
          throw new Error("Unable to load spell IDs.");
        }
        return response.json();
      })
      .then((payload) => {
        const ids = Array.isArray(payload?.ids) ? payload.ids : [];
        cache = ids;
        return ids;
      })
      .catch((error) => {
        console.warn("Unable to load spells", error);
        cache = [];
        return cache;
      })
      .finally(() => {
        inflight = null;
      });
    return inflight;
  };
})();

const setValueAtPath = (target, path, value) => {
  let cursor = target;
  path.forEach((segment, index) => {
    if (index === path.length - 1) {
      cursor[segment] = value;
      return;
    }
    if (cursor[segment] === undefined) {
      cursor[segment] = typeof path[index + 1] === "number" ? [] : {};
    }
    cursor = cursor[segment];
  });
};

const getValueAtPath = (target, path) => {
  return path.reduce((acc, segment) => {
    if (!acc) {
      return undefined;
    }
    return acc[segment];
  }, target);
};

const mergeDefaults = (payload, defaults) => {
  if (Array.isArray(defaults)) {
    return Array.isArray(payload) ? payload : clone(defaults);
  }
  if (defaults && typeof defaults === "object") {
    const merged = { ...(payload || {}) };
    Object.entries(defaults).forEach(([key, value]) => {
      if (merged[key] === undefined) {
        merged[key] = clone(value);
      } else {
        merged[key] = mergeDefaults(merged[key], value);
      }
    });
    return merged;
  }
  return payload === undefined ? defaults : payload;
};

const slugify = (value, separator = "_") => {
  const text = String(value || "").trim().toLowerCase();
  const normalized = text
    .replace(/['`]/g, separator)
    .replace(/[^a-z0-9\s_-]/g, "")
    .replace(/[\s-]+/g, separator);
  const trimmed = normalized.replace(new RegExp(`^${separator}+|${separator}+$`, "g"), "");
  return trimmed || "character";
};

const buildDefaultFromSchema = (schema) => {
  if (!schema) {
    return null;
  }
  if (schema.default !== undefined) {
    return clone(schema.default);
  }
  const type = schema.type;
  if (Array.isArray(type)) {
    return "";
  }
  if (type === "object") {
    const obj = {};
    (schema.fields || []).forEach((field) => {
      obj[field.key] = buildDefaultFromSchema(field);
    });
    return obj;
  }
  if (type === "array") {
    return [];
  }
  if (type === "map") {
    return {};
  }
  if (type === "boolean") {
    return false;
  }
  if (type === "integer" || type === "number") {
    return 0;
  }
  return "";
};

const buildDefaultsFromSchema = (schema) => {
  const defaults = {};
  (schema.sections || []).forEach((section) => {
    const sectionPath = section.path || [];
    const value = buildDefaultFromSchema(section);
    if (sectionPath.length === 0 && value && typeof value === "object" && !Array.isArray(value)) {
      Object.assign(defaults, value);
    } else {
      setValueAtPath(defaults, sectionPath, value);
    }
  });
  return defaults;
};

const normalizeSpeedValue = (value) => {
  if (typeof value === "number" && Number.isFinite(value)) {
    return Math.trunc(value);
  }
  if (typeof value === "string") {
    const match = value.match(/-?\d+/);
    if (match) {
      return Number.parseInt(match[0], 10);
    }
  }
  return 0;
};

const normalizeCharacterData = (data) => {
  if (!data || typeof data !== "object") {
    return data;
  }
  const vitals = data.vitals;
  if (!vitals || typeof vitals !== "object") {
    return data;
  }
  const speed = vitals.speed;
  if (!speed || typeof speed !== "object" || Array.isArray(speed)) {
    return data;
  }
  const legacyMap = {
    Normal: "walk",
    Climb: "climb",
    Fly: "fly",
    Swim: "swim",
  };
  const hasLegacy = Object.keys(legacyMap).some((key) => Object.prototype.hasOwnProperty.call(speed, key));
  if (!hasLegacy && !Object.prototype.hasOwnProperty.call(speed, "Burrow")) {
    return data;
  }
  const normalized = {
    walk: normalizeSpeedValue(speed.walk),
    climb: normalizeSpeedValue(speed.climb),
    fly: normalizeSpeedValue(speed.fly),
    swim: normalizeSpeedValue(speed.swim),
  };
  Object.entries(legacyMap).forEach(([legacyKey, schemaKey]) => {
    if (Object.prototype.hasOwnProperty.call(speed, legacyKey)) {
      normalized[schemaKey] = normalizeSpeedValue(speed[legacyKey]);
    }
  });
  vitals.speed = normalized;
  return data;
};

const loadSchema = async () => {
  try {
    const response = await fetch("/api/characters/schema");
    if (response.ok) {
      const payload = await response.json();
      if (payload && payload.schema) {
        return payload.schema;
      }
    }
  } catch (error) {
    console.warn("Unable to load schema from API", error);
  }
  const fallback = await fetch("/assets/web/new_character/schema.json");
  return fallback.json();
};

const createInput = (field, value, path, data) => {
  const wrapper = document.createElement("div");
  wrapper.className = "field";

  const label = document.createElement("label");
  label.textContent = field.label || field.key;
  wrapper.appendChild(label);

  let input;
  const inputType = Array.isArray(field.type) ? "string" : field.type;
  const useTextarea = field.key === "description" || field.key === "notes";
  if (inputType === "boolean") {
    input = document.createElement("input");
    input.type = "checkbox";
    input.checked = Boolean(value);
    input.addEventListener("change", () => {
      setValueAtPath(data, path, input.checked);
    });
  } else if (path.join(".").endsWith("leveling.classes.name")) {
    input = document.createElement("select");
    const emptyOption = document.createElement("option");
    emptyOption.value = "";
    emptyOption.textContent = "Select class";
    input.appendChild(emptyOption);
    CLASS_OPTIONS.forEach((name) => {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      option.selected = String(value || "") === name;
      input.appendChild(option);
    });
    input.addEventListener("change", () => setValueAtPath(data, path, input.value));
  } else if (inputType === "integer" || inputType === "number") {
    input = document.createElement("input");
    input.type = "number";
    input.value = value ?? 0;
    input.addEventListener("input", () => {
      const nextValue = input.value === "" ? 0 : Number(input.value);
      setValueAtPath(data, path, inputType === "integer" ? Math.trunc(nextValue) : nextValue);
    });
  } else if (useTextarea) {
    input = document.createElement("textarea");
    input.rows = 3;
    input.value = value ?? "";
    input.placeholder = getFieldPlaceholder(field);
    input.addEventListener("input", () => {
      setValueAtPath(data, path, input.value);
    });
  } else {
    input = document.createElement("input");
    input.type = "text";
    input.value = value ?? "";
    input.placeholder = getFieldPlaceholder(field);
    input.addEventListener("input", () => {
      setValueAtPath(data, path, input.value);
    });
  }

  wrapper.appendChild(input);
  appendHelpText(wrapper, field);
  return wrapper;
};

const renderArrayField = (field, path, data) => {
  const container = document.createElement("div");
  container.className = "array-field";

  const header = document.createElement("div");
  header.className = "array-header";

  const title = document.createElement("h3");
  title.textContent = field.label || field.key;
  header.appendChild(title);

  const addButton = document.createElement("button");
  addButton.type = "button";
  addButton.className = "ghost";
  addButton.textContent = "Add";
  header.appendChild(addButton);

  container.appendChild(header);
  appendHelpText(container, field);

  const itemsContainer = document.createElement("div");
  itemsContainer.className = "array-items";
  container.appendChild(itemsContainer);

  const renderItems = () => {
    const value = getValueAtPath(data, path) || [];
    itemsContainer.innerHTML = "";
    value.forEach((item, index) => {
      const itemWrapper = document.createElement("div");
      itemWrapper.className = "array-item";

      const itemHeader = document.createElement("div");
      itemHeader.className = "array-item-header";
      const itemTitle = document.createElement("span");
      itemTitle.textContent = `${field.label || field.key} #${index + 1}`;
      itemHeader.appendChild(itemTitle);
      const removeButton = document.createElement("button");
      removeButton.type = "button";
      removeButton.className = "ghost danger";
      removeButton.textContent = "Remove";
      removeButton.addEventListener("click", () => {
        value.splice(index, 1);
        setValueAtPath(data, path, value);
        renderItems();
      });
      itemHeader.appendChild(removeButton);
      itemWrapper.appendChild(itemHeader);

      const itemSchema = field.items || { type: "string" };
      if (itemSchema.type === "object") {
        (itemSchema.fields || []).forEach((child) => {
          const childPath = [...path, index, child.key];
          const childValue = getValueAtPath(data, childPath);
          itemWrapper.appendChild(renderField(child, childPath, data, childValue));
        });
      } else {
        const itemPath = [...path, index];
        const primitiveSchema = {
          ...itemSchema,
          label: itemSchema.label || field.label || "Value",
          key: itemSchema.key || field.key,
          placeholder: itemSchema.placeholder || field.placeholder,
        };
        itemWrapper.appendChild(renderField(primitiveSchema, itemPath, data, item));
      }

      itemsContainer.appendChild(itemWrapper);
    });
  };

  addButton.addEventListener("click", () => {
    const value = getValueAtPath(data, path) || [];
    const nextItem = buildDefaultFromSchema(field.items || { type: "string" });
    value.push(nextItem);
    setValueAtPath(data, path, value);
    renderItems();
  });

  renderItems();
  return container;
};

const renderMapField = (field, path, data) => {
  const container = document.createElement("div");
  container.className = "array-field";

  const header = document.createElement("div");
  header.className = "array-header";

  const title = document.createElement("h3");
  title.textContent = field.label || field.key;
  header.appendChild(title);

  const addButton = document.createElement("button");
  addButton.type = "button";
  addButton.className = "ghost";
  addButton.textContent = "Add Note";
  header.appendChild(addButton);

  container.appendChild(header);
  appendHelpText(container, field);

  const itemsContainer = document.createElement("div");
  itemsContainer.className = "array-items";
  container.appendChild(itemsContainer);

  const renderItems = () => {
    const value = getValueAtPath(data, path) || {};
    itemsContainer.innerHTML = "";
    Object.entries(value).forEach(([key, entryValue]) => {
      const row = document.createElement("div");
      row.className = "map-row";

      const keyInput = document.createElement("input");
      keyInput.type = "text";
      keyInput.value = key;
      keyInput.placeholder = field.key_placeholder || "Key";

      const valueInput = document.createElement("input");
      valueInput.type = "text";
      valueInput.value = entryValue ?? "";
      valueInput.placeholder = field.value_placeholder || field.placeholder || "Value";

      const removeButton = document.createElement("button");
      removeButton.type = "button";
      removeButton.className = "ghost danger";
      removeButton.textContent = "Remove";

      const updateKey = () => {
        const nextKey = keyInput.value.trim();
        if (nextKey === key) {
          return;
        }
        if (key) {
          delete value[key];
        }
        if (nextKey) {
          value[nextKey] = valueInput.value;
        }
        setValueAtPath(data, path, value);
        renderItems();
      };

      keyInput.addEventListener("change", updateKey);
      valueInput.addEventListener("input", () => {
        const nextKey = keyInput.value.trim();
        if (!nextKey) {
          return;
        }
        value[nextKey] = valueInput.value;
        setValueAtPath(data, path, value);
      });
      removeButton.addEventListener("click", () => {
        delete value[key];
        setValueAtPath(data, path, value);
        renderItems();
      });

      row.appendChild(keyInput);
      row.appendChild(valueInput);
      row.appendChild(removeButton);
      itemsContainer.appendChild(row);
    });
  };

  addButton.addEventListener("click", () => {
    const value = getValueAtPath(data, path) || {};
    const newKey = `note_${Object.keys(value).length + 1}`;
    value[newKey] = "";
    setValueAtPath(data, path, value);
    renderItems();
  });

  renderItems();
  return container;
};

const renderSpellPicker = (field, path, data) => {
  const container = document.createElement("div");
  container.className = "array-field spell-picker";

  const header = document.createElement("div");
  header.className = "array-header";
  const title = document.createElement("h3");
  title.textContent = field.label || field.key;
  header.appendChild(title);
  container.appendChild(header);

  const controls = document.createElement("div");
  controls.className = "spell-picker-controls";
  const input = document.createElement("input");
  input.type = "text";
  input.placeholder = "Search spells...";
  const listId = `spell-list-${Math.random().toString(36).slice(2)}`;
  input.setAttribute("list", listId);
  controls.appendChild(input);

  const addButton = document.createElement("button");
  addButton.type = "button";
  addButton.className = "ghost";
  addButton.textContent = "Add";
  controls.appendChild(addButton);

  container.appendChild(controls);

  const status = document.createElement("p");
  status.className = "spell-picker-status";
  status.textContent = "Loading spells…";
  container.appendChild(status);

  const datalist = document.createElement("datalist");
  datalist.id = listId;
  container.appendChild(datalist);

  const selectedContainer = document.createElement("div");
  selectedContainer.className = "spell-picker-selected";
  container.appendChild(selectedContainer);

  const setStatus = (text) => {
    status.textContent = text;
  };

  const renderSelected = () => {
    const value = getValueAtPath(data, path) || [];
    selectedContainer.innerHTML = "";
    if (!value.length) {
      const empty = document.createElement("div");
      empty.className = "spell-picker-empty";
      empty.textContent = "No spells selected yet.";
      selectedContainer.appendChild(empty);
      return;
    }
    value.forEach((spellId) => {
      const pill = document.createElement("div");
      pill.className = "spell-chip";
      const label = document.createElement("span");
      label.textContent = spellId;
      pill.appendChild(label);
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "ghost danger";
      remove.textContent = "Remove";
      remove.addEventListener("click", () => {
        const next = (getValueAtPath(data, path) || []).filter((item) => item !== spellId);
        setValueAtPath(data, path, next);
        renderSelected();
      });
      pill.appendChild(remove);
      selectedContainer.appendChild(pill);
    });
  };

  const addSpell = (spellId, available) => {
    const normalized = (spellId || "").trim();
    if (!normalized) {
      return;
    }
    if (available && !available.includes(normalized)) {
      setStatus(`Spell "${normalized}" not found.`);
      return;
    }
    const value = getValueAtPath(data, path) || [];
    if (value.includes(normalized)) {
      setStatus(`"${normalized}" is already selected.`);
      return;
    }
    value.push(normalized);
    setValueAtPath(data, path, value);
    input.value = "";
    setStatus(`${normalized} added.`);
    renderSelected();
  };

  addButton.addEventListener("click", async () => {
    const available = await loadSpellIds();
    addSpell(input.value, available);
  });

  input.addEventListener("keydown", async (event) => {
    if (event.key !== "Enter") {
      return;
    }
    event.preventDefault();
    const available = await loadSpellIds();
    addSpell(input.value, available);
  });

  loadSpellIds().then((ids) => {
    datalist.innerHTML = "";
    ids.forEach((spellId) => {
      const option = document.createElement("option");
      option.value = spellId;
      datalist.appendChild(option);
    });
    setStatus(ids.length ? "Select spells from the list." : "No spells found.");
  });

  renderSelected();
  return container;
};

const renderSpellSlots = (field, path, data) => {
  const container = document.createElement("div");
  container.className = "field-group spell-slots";

  const title = document.createElement("h3");
  title.textContent = field.label || field.key;
  container.appendChild(title);
  appendHelpText(container, field);

  const grid = document.createElement("div");
  grid.className = "spell-slot-grid";

  const headerRow = document.createElement("div");
  headerRow.className = "spell-slot-row spell-slot-header";

  const levelHeader = document.createElement("div");
  levelHeader.textContent = "Level";
  const maxHeader = document.createElement("div");
  maxHeader.textContent = "Max";
  const currentHeader = document.createElement("div");
  currentHeader.textContent = "Current";

  headerRow.appendChild(levelHeader);
  headerRow.appendChild(maxHeader);
  headerRow.appendChild(currentHeader);
  grid.appendChild(headerRow);

  SPELL_SLOT_LEVELS.forEach(({ key, label }) => {
    const row = document.createElement("div");
    row.className = "spell-slot-row";

    const levelLabel = document.createElement("div");
    levelLabel.className = "spell-slot-label";
    levelLabel.textContent = label;
    row.appendChild(levelLabel);

    ["max", "current"].forEach((slotKey) => {
      const input = document.createElement("input");
      input.type = "number";
      const inputPath = [...path, key, slotKey];
      let slotValue = getValueAtPath(data, inputPath);
      if (slotValue === undefined || slotValue === null || Number.isNaN(Number(slotValue))) {
        slotValue = 0;
        setValueAtPath(data, inputPath, slotValue);
      }
      input.value = slotValue;
      input.addEventListener("input", () => {
        const nextValue = input.value === "" ? 0 : Number(input.value);
        setValueAtPath(data, inputPath, Math.trunc(nextValue));
      });
      row.appendChild(input);
    });

    grid.appendChild(row);
  });

  container.appendChild(grid);
  return container;
};

const renderField = (field, path, data, value) => {
  if (isSpellSlotsPath(path)) {
    return renderSpellSlots(field, path, data);
  }
  if (field.type === "object") {
    const container = document.createElement("div");
    container.className = "field-group";
    const title = document.createElement("h3");
    title.textContent = field.label || field.key;
    container.appendChild(title);
    (field.fields || []).forEach((child) => {
      const childPath = [...path, child.key];
      const childValue = getValueAtPath(data, childPath);
      container.appendChild(renderField(child, childPath, data, childValue));
    });
    return container;
  }
  if (field.type === "array") {
    if (isSpellPickerPath(path)) {
      return renderSpellPicker(field, path, data);
    }
    return renderArrayField(field, path, data);
  }
  if (field.type === "map") {
    return renderMapField(field, path, data);
  }
  return createInput(field, value, path, data);
};

const TAB_LAYOUT = [
  { id: "basic", label: "Basic Info", sections: ["root", "identity"] },
  { id: "stats", label: "Stats", sections: ["leveling", "abilities", "proficiency", "defenses", "attacks"] },
  { id: "vitals", label: "Vitals", sections: ["vitals", "resources"] },
  { id: "feats", label: "Feats", sections: ["features"] },
  { id: "actions", label: "Actions", sections: ["actions", "reactions", "bonus_actions"] },
  { id: "spellcasting", label: "Spellcasting", sections: ["spellcasting"] },
  { id: "other", label: "Other", sections: ["inventory", "notes"] },
];

const renderForm = (schema, data) => {
  formEl.innerHTML = "";
  const tabs = document.createElement("div");
  tabs.className = "tab-bar";
  const panes = document.createElement("div");
  panes.className = "tab-panes";
  const paneById = new Map();
  TAB_LAYOUT.forEach((tab, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `tab-button${index === 0 ? " active" : ""}`;
    button.textContent = tab.label;
    button.dataset.tabTarget = tab.id;
    tabs.appendChild(button);

    const pane = document.createElement("div");
    pane.className = `tab-pane${index === 0 ? " active" : ""}`;
    pane.dataset.tabPane = tab.id;
    panes.appendChild(pane);
    paneById.set(tab.id, pane);
  });
  tabs.addEventListener("click", (event) => {
    const button = event.target.closest(".tab-button");
    if (!button) return;
    const target = button.dataset.tabTarget;
    tabs.querySelectorAll(".tab-button").forEach((el) => el.classList.toggle("active", el === button));
    panes.querySelectorAll(".tab-pane").forEach((el) => el.classList.toggle("active", el.dataset.tabPane === target));
  });
  formEl.appendChild(tabs);
  formEl.appendChild(panes);

  (schema.sections || []).forEach((section) => {
    const sectionEl = document.createElement("section");
    sectionEl.className = "section";
    const header = document.createElement("h2");
    header.textContent = section.label || section.id;
    sectionEl.appendChild(header);

    const sectionPath = section.path || [];
    if (section.type === "object") {
      (section.fields || []).forEach((field) => {
        const fieldPath = sectionPath.length ? [...sectionPath, field.key] : [field.key];
        const fieldValue = getValueAtPath(data, fieldPath);
        sectionEl.appendChild(renderField(field, fieldPath, data, fieldValue));
      });
    } else if (section.type === "array") {
      sectionEl.appendChild(renderArrayField(section, sectionPath, data));
    } else if (section.type === "map") {
      sectionEl.appendChild(renderMapField(section, sectionPath, data));
    }

    const targetTab = TAB_LAYOUT.find((tab) => tab.sections.includes(section.id))?.id || "other";
    const targetPane = paneById.get(targetTab) || paneById.get("other");
    targetPane.appendChild(sectionEl);
  });
};


const sanitizeCharacterPayload = (data) => {
  if (!data || typeof data !== "object") return data;
  const payload = clone(data);
  delete payload.format_version;
  return payload;
};

const refreshPlayerCache = async () => {
  try {
    const response = await fetch("/api/players/cache/refresh", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ clear_only: false }),
    });
    if (!response.ok) throw new Error("refresh failed");
    statusEl.textContent = "Player cache refreshed.";
  } catch (_error) {
    statusEl.textContent = "Unable to refresh cache.";
  }
};

const buildExportFilename = (data) => {
  const rawInput = filenameInput?.value?.trim() || "";
  const base = rawInput || slugify(data?.name || "");
  const withExtension = /\.ya?ml$/i.test(base) ? base : `${base}.yaml`;
  return withExtension || "character.yaml";
};

const downloadYaml = (yamlText, filename) => {
  const blob = new Blob([yamlText], { type: "application/x-yaml" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
};

const exportYaml = async (data) => {
  statusEl.textContent = "Preparing YAML export...";
  try {
    normalizeCharacterData(data);
    const response = await fetch("/api/characters/export", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ data: sanitizeCharacterPayload(data) }),
    });
    if (!response.ok) {
      const message = await response.text();
      throw new Error(message || "Unable to export YAML.");
    }
    const yamlText = await response.text();
    const filename = buildExportFilename(data);
    downloadYaml(yamlText, filename);
    statusEl.textContent = `Exported ${filename}.`;
  } catch (error) {
    console.warn("Unable to export YAML", error);
    statusEl.textContent = "Unable to export YAML. Please try again.";
  }
};

const fetchAssignedCharacter = async () => {
  try {
    const response = await fetch("/api/characters/by_ip");
    if (!response.ok) {
      return null;
    }
    const payload = await response.json();
    if (!payload || !payload.character) {
      return null;
    }
    return payload;
  } catch (error) {
    console.warn("Unable to load assigned character", error);
    return null;
  }
};

const overwriteCharacter = async (data, originalFilename) => {
  if (!originalFilename) {
    statusEl.textContent = "No assigned character found to overwrite.";
    return;
  }
  statusEl.textContent = "Overwriting character...";
  try {
    normalizeCharacterData(data);
    const response = await fetch(`/api/characters/${encodeURIComponent(originalFilename)}/overwrite`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        data: sanitizeCharacterPayload(data),
        filename: filenameInput?.value || "",
      }),
    });
    if (!response.ok) {
      const message = await response.text();
      throw new Error(message || "Unable to overwrite character.");
    }
    const payload = await response.json();
    const savedFilename = payload?.filename || originalFilename;
    originalFilename = savedFilename;
    if (filenameInput) {
      filenameInput.value = savedFilename;
    }
    statusEl.textContent = `Saved ${savedFilename}.`;
    return savedFilename;
  } catch (error) {
    console.warn("Unable to overwrite character", error);
    statusEl.textContent = "Unable to overwrite character. Please try again.";
    return originalFilename;
  }
};

const boot = async () => {
  const schema = await loadSchema();
  const defaults = buildDefaultsFromSchema(schema);
  let data = normalizeCharacterData(defaults);
  let originalFilename = "";

  const assigned = await fetchAssignedCharacter();
  if (assigned) {
    normalizeCharacterData(assigned.character);
    data = mergeDefaults(assigned.character, defaults);
    originalFilename = assigned.filename || "";
    if (filenameInput) {
      filenameInput.value = originalFilename;
    }
    statusEl.textContent = originalFilename
      ? `Loaded ${originalFilename}.`
      : "Loaded assigned character.";
  } else {
    statusEl.textContent = "No character is assigned to this device.";
    if (overwriteButton) {
      overwriteButton.disabled = true;
    }
  }

  normalizeCharacterData(data);
  renderForm(schema, data);

  if (overwriteButton && !originalFilename) {
    overwriteButton.disabled = true;
  }

  if (filenameInput) {
    filenameInput.addEventListener("input", () => {
      if (overwriteButton) {
        overwriteButton.disabled = !filenameInput.value.trim();
      }
    });
  }

  if (exportButton) {
    exportButton.addEventListener("click", () => exportYaml(data));
  }

  if (refreshCacheButton) {
    refreshCacheButton.addEventListener("click", refreshPlayerCache);
  }

  if (overwriteButton) {
    overwriteButton.addEventListener("click", async () => {
      const next = await overwriteCharacter(data, originalFilename);
      if (next) {
        originalFilename = next;
      }
    });
  }
};

boot();
