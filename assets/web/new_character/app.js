const STORAGE_KEY = "inittracker:new-character-draft-v2";

const statusEl = document.getElementById("draft-status");
const button = document.getElementById("draft-button");
const formEl = document.getElementById("character-form");

const clone = (value) => JSON.parse(JSON.stringify(value));

const SPELL_PICKER_PATHS = new Set([
  "spellcasting.cantrips.known",
  "spellcasting.known_spells.known",
  "spellcasting.prepared_spells.prepared",
]);

const spellPathKey = (path) => path.join(".");
const isSpellPickerPath = (path) => SPELL_PICKER_PATHS.has(spellPathKey(path));

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
    input.addEventListener("input", () => {
      setValueAtPath(data, path, input.value);
    });
  } else {
    input = document.createElement("input");
    input.type = "text";
    input.value = value ?? "";
    input.addEventListener("input", () => {
      setValueAtPath(data, path, input.value);
    });
  }

  wrapper.appendChild(input);
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
      keyInput.placeholder = "Key";

      const valueInput = document.createElement("input");
      valueInput.type = "text";
      valueInput.value = entryValue ?? "";
      valueInput.placeholder = "Value";

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

const renderField = (field, path, data, value) => {
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

const renderForm = (schema, data) => {
  formEl.innerHTML = "";
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

    formEl.appendChild(sectionEl);
  });
};

const loadDraft = (defaults) => {
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return defaults;
  }
  try {
    const payload = JSON.parse(raw);
    if (payload && typeof payload === "object") {
      const merged = mergeDefaults(payload.data || payload, defaults);
      if (payload.savedAt) {
        statusEl.textContent = `Last saved ${payload.savedAt}.`;
      }
      return merged;
    }
  } catch (error) {
    console.warn("Unable to parse draft", error);
  }
  return defaults;
};

const saveDraft = (data) => {
  const payload = {
    data,
    savedAt: new Date().toLocaleString(),
  };
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  statusEl.textContent = `Draft saved at ${payload.savedAt}.`;
};

const boot = async () => {
  const schema = await loadSchema();
  const defaults = buildDefaultsFromSchema(schema);
  const data = loadDraft(defaults);
  renderForm(schema, data);
  button.addEventListener("click", () => saveDraft(data));
};

boot();
