const STORAGE_KEY = "inittracker:new-character-draft-v2";

const statusEl = document.getElementById("draft-status");
const button = document.getElementById("draft-button");
const exportButton = document.getElementById("export-button");
const formEl = document.getElementById("character-form");
const filenameInput = document.getElementById("filename-input");

const clone = (value) => JSON.parse(JSON.stringify(value));

const SPELL_PICKER_PATHS = new Set([
  "spellcasting.cantrips.known",
  "spellcasting.known_spells.known",
  "spellcasting.prepared_spells.prepared",
]);

const spellPathKey = (path) => path.join(".");
const isSpellPickerPath = (path) => SPELL_PICKER_PATHS.has(spellPathKey(path));

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

const HIT_DICE_BY_CLASS = new Map([
  ["barbarian", "d12"],
  ["fighter", "d10"],
  ["paladin", "d10"],
  ["ranger", "d10"],
  ["artificer", "d8"],
  ["bard", "d8"],
  ["cleric", "d8"],
  ["druid", "d8"],
  ["monk", "d8"],
  ["rogue", "d8"],
  ["warlock", "d8"],
  ["sorcerer", "d6"],
  ["wizard", "d6"],
]);
const HIT_DICE_ORDER = ["d12", "d10", "d8", "d6"];

const derivedStats = (() => {
  const AUTO_FIELDS = new Set([
    "vitals.hit_dice.die",
    "vitals.hit_dice.total",
    "spellcasting.save_dc_formula",
    "spellcasting.spell_attack_formula",
    "attacks.melee_attack_mod",
    "attacks.ranged_attack_mod",
    "attacks.weapon_to_hit",
  ]);
  const WATCH_PATHS = [
    "leveling.level",
    "leveling.classes",
    "abilities",
    "proficiency.bonus",
    "spellcasting.casting_ability",
  ];
  const overrides = new Set();
  let boundForm = null;
  let boundData = null;

  const pathKey = (path) => (Array.isArray(path) ? path.join(".") : path);
  const splitPath = (path) => (Array.isArray(path) ? path : path.split(".").filter(Boolean));

  const shouldRecalculate = (path) => {
    const key = pathKey(path);
    return WATCH_PATHS.some((watch) => key === watch || key.startsWith(`${watch}.`));
  };

  const markOverride = (path) => {
    const key = pathKey(path);
    if (AUTO_FIELDS.has(key)) {
      overrides.add(key);
    }
  };

  const updateInputValue = (path, value) => {
    if (!boundForm) {
      return;
    }
    const key = pathKey(path);
    const input = boundForm.querySelector(`[data-path="${key}"]`);
    if (!input) {
      return;
    }
    if (input.type === "checkbox") {
      input.checked = Boolean(value);
    } else {
      input.value = value ?? "";
    }
  };

  const applyAutoValue = (path, value) => {
    const key = pathKey(path);
    if (overrides.has(key)) {
      return;
    }
    const current = getValueAtPath(boundData, splitPath(path));
    if (current === value) {
      return;
    }
    setValueAtPath(boundData, splitPath(path), value);
    updateInputValue(path, value);
  };

  const toModifier = (score) => Math.floor((Number(score) - 10) / 2);

  const getHitDice = (classes) => {
    const dice = (classes || [])
      .map((entry) => String(entry?.name || "").trim().toLowerCase())
      .map((name) => HIT_DICE_BY_CLASS.get(name))
      .filter(Boolean);
    const uniqueDice = Array.from(new Set(dice));
    if (!uniqueDice.length) {
      return "";
    }
    if (uniqueDice.length === 1) {
      return uniqueDice[0];
    }
    const sorted = HIT_DICE_ORDER.filter((die) => uniqueDice.includes(die));
    return sorted.join("/");
  };

  const recalculate = () => {
    if (!boundData) {
      return;
    }
    const abilities = boundData?.abilities || {};
    const proficiency = Number(boundData?.proficiency?.bonus ?? 0);
    const leveling = boundData?.leveling || {};
    const totalLevel =
      Number(leveling?.level ?? 0) ||
      (Array.isArray(leveling?.classes)
        ? leveling.classes.reduce((sum, entry) => sum + Number(entry?.level ?? 0), 0)
        : 0);
    const hitDie = getHitDice(leveling?.classes);

    if (hitDie) {
      applyAutoValue("vitals.hit_dice.die", hitDie);
    }
    if (totalLevel) {
      applyAutoValue("vitals.hit_dice.total", totalLevel);
    }

    const castingAbility = String(boundData?.spellcasting?.casting_ability || "").trim();
    if (castingAbility && Number.isFinite(proficiency)) {
      applyAutoValue("spellcasting.save_dc_formula", "8 + prof + casting_mod");
      applyAutoValue("spellcasting.spell_attack_formula", "prof + casting_mod");
    }

    const strMod = toModifier(abilities?.str ?? 10);
    const dexMod = toModifier(abilities?.dex ?? 10);
    const meleeMod = strMod + proficiency;
    const rangedMod = dexMod + proficiency;
    const weaponToHit = Math.max(strMod, dexMod) + proficiency;
    applyAutoValue("attacks.melee_attack_mod", meleeMod);
    applyAutoValue("attacks.ranged_attack_mod", rangedMod);
    applyAutoValue("attacks.weapon_to_hit", weaponToHit);
  };

  const handleChange = (path, { source } = {}) => {
    if (source === "user") {
      markOverride(path);
    }
    if (shouldRecalculate(path)) {
      recalculate();
    }
  };

  const bind = (form, data) => {
    boundForm = form;
    boundData = data;
    form.addEventListener("input", (event) => {
      const target = event.target;
      if (!target?.dataset?.path) {
        return;
      }
      handleChange(target.dataset.path, { source: "user" });
    });
    form.addEventListener("change", (event) => {
      const target = event.target;
      if (!target?.dataset?.path) {
        return;
      }
      handleChange(target.dataset.path, { source: "user" });
    });
  };

  return {
    bind,
    handleChange,
    recalculate,
  };
})();

const slugify = (value, separator = "_") => {
  const text = String(value || "").trim().toLowerCase();
  const normalized = text.replace(/[^\w\s-]/g, "").replace(/[\s-]+/g, separator);
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
    input.dataset.path = path.join(".");
    input.checked = Boolean(value);
    input.addEventListener("change", () => {
      setValueAtPath(data, path, input.checked);
    });
  } else if (inputType === "integer" || inputType === "number") {
    input = document.createElement("input");
    input.type = "number";
    input.dataset.path = path.join(".");
    input.value = value ?? 0;
    input.addEventListener("input", () => {
      const nextValue = input.value === "" ? 0 : Number(input.value);
      setValueAtPath(data, path, inputType === "integer" ? Math.trunc(nextValue) : nextValue);
    });
  } else if (useTextarea) {
    input = document.createElement("textarea");
    input.rows = 3;
    input.dataset.path = path.join(".");
    input.value = value ?? "";
    input.placeholder = getFieldPlaceholder(field);
    input.addEventListener("input", () => {
      setValueAtPath(data, path, input.value);
    });
  } else {
    input = document.createElement("input");
    input.type = "text";
    input.dataset.path = path.join(".");
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
        derivedStats.handleChange(path, { source: "system" });
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
    derivedStats.handleChange(path, { source: "system" });
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
        derivedStats.handleChange(path, { source: "system" });
      });
      removeButton.addEventListener("click", () => {
        delete value[key];
        setValueAtPath(data, path, value);
        derivedStats.handleChange(path, { source: "system" });
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
    derivedStats.handleChange(path, { source: "system" });
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
    return { data: defaults, filename: "" };
  }
  try {
    const payload = JSON.parse(raw);
    if (payload && typeof payload === "object") {
      const merged = mergeDefaults(payload.data || payload, defaults);
      if (payload.savedAt) {
        statusEl.textContent = `Last saved ${payload.savedAt}.`;
      }
      return {
        data: merged,
        filename: typeof payload.filename === "string" ? payload.filename : "",
      };
    }
  } catch (error) {
    console.warn("Unable to parse draft", error);
  }
  return { data: defaults, filename: "" };
};

const saveDraft = (data, filename, { showStatus = true } = {}) => {
  const payload = {
    data,
    filename,
    savedAt: new Date().toLocaleString(),
  };
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  if (showStatus) {
    statusEl.textContent = `Draft saved at ${payload.savedAt}.`;
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
    const response = await fetch("/api/characters/export", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ data }),
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

const boot = async () => {
  const schema = await loadSchema();
  const defaults = buildDefaultsFromSchema(schema);
  const draft = loadDraft(defaults);
  const data = draft.data;
  renderForm(schema, data);
  derivedStats.bind(formEl, data);
  derivedStats.recalculate();
  if (filenameInput) {
    filenameInput.value = draft.filename || "";
    filenameInput.addEventListener("input", () => {
      saveDraft(data, filenameInput.value, { showStatus: false });
    });
  }
  button.addEventListener("click", () => saveDraft(data, filenameInput?.value || ""));
  if (exportButton) {
    exportButton.addEventListener("click", () => exportYaml(data));
  }
};

boot();
