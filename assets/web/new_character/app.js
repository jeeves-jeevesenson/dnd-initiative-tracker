const STORAGE_KEY = "inittracker:new-character-draft-v2";

const statusEl = document.getElementById("draft-status");
const button = document.getElementById("draft-button");
const exportButton = document.getElementById("export-button");
const resetButton = document.getElementById("reset-button");
const clearDraftButton = document.getElementById("clear-draft-button");
const formEl = document.getElementById("character-form");
const filenameInput = document.getElementById("filename-input");

const clone = (value) => JSON.parse(JSON.stringify(value));

const SPELL_PICKER_PATHS = new Set([
  "spellcasting.cantrips.known",
  "spellcasting.known_spells.known",
  "spellcasting.prepared_spells.prepared",
]);
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

const loadSpellData = (() => {
  let cache = null;
  let inflight = null;
  return async () => {
    if (cache) {
      return cache;
    }
    if (inflight) {
      return inflight;
    }
    inflight = fetch("/api/spells?details=true")
      .then((response) => {
        if (!response.ok) {
          throw new Error("Unable to load spell IDs.");
        }
        return response.json();
      })
      .then((payload) => {
        const ids = Array.isArray(payload?.ids) ? payload.ids : [];
        const spells = Array.isArray(payload?.spells) ? payload.spells : [];
        cache = { ids, spells };
        return cache;
      })
      .catch((error) => {
        console.warn("Unable to load spells", error);
        cache = { ids: [], spells: [] };
        return cache;
      })
      .finally(() => {
        inflight = null;
      });
    return inflight;
  };
})();

const getSpellLevel = (level) => {
  if (level === undefined || level === null) {
    return null;
  }
  if (typeof level === "number") {
    return level;
  }
  if (typeof level === "string") {
    const normalized = level.trim().toLowerCase();
    if (normalized === "cantrip") {
      return 0;
    }
    const numeric = Number(normalized);
    if (Number.isFinite(numeric)) {
      return numeric;
    }
  }
  return null;
};

const getSpellLevelFromRecord = (spell) => getSpellLevel(spell?.level ?? spell?.parsed?.level);

const getCharacterLevel = (data) => {
  const leveling = data?.leveling || {};
  const level = Number(leveling?.level ?? 0);
  if (level) {
    return level;
  }
  if (Array.isArray(leveling?.classes)) {
    return leveling.classes.reduce((sum, entry) => sum + Number(entry?.level ?? 0), 0);
  }
  return 0;
};

const maxSpellLevelForCharacter = (level) => {
  const numericLevel = Number(level ?? 0);
  if (!Number.isFinite(numericLevel) || numericLevel <= 0) {
    return 0;
  }
  if (numericLevel >= 17) {
    return 9;
  }
  if (numericLevel >= 15) {
    return 8;
  }
  if (numericLevel >= 13) {
    return 7;
  }
  if (numericLevel >= 11) {
    return 6;
  }
  if (numericLevel >= 9) {
    return 5;
  }
  if (numericLevel >= 7) {
    return 4;
  }
  if (numericLevel >= 5) {
    return 3;
  }
  if (numericLevel >= 3) {
    return 2;
  }
  return 1;
};

const filterSpellIds = (payload, { requireLevel } = {}) => {
  const ids = Array.isArray(payload?.ids) ? payload.ids : [];
  const spells = Array.isArray(payload?.spells) ? payload.spells : [];
  if (!spells.length || requireLevel === undefined) {
    return ids;
  }
  return spells
    .map((spell) => {
      if (!spell || !spell.id) {
        return null;
      }
      const level = getSpellLevelFromRecord(spell);
      return level === requireLevel ? spell.id : null;
    })
    .filter(Boolean);
};

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
const CLASS_OPTIONS = [
  "Barbarian", "Bard", "Cleric", "Druid", "Fighter", "Monk", "Paladin", "Ranger", "Rogue", "Sorcerer", "Warlock", "Wizard",
];
const SAVE_PROFICIENCIES = new Map([
  ["barbarian", ["str", "con"]],
  ["bard", ["dex", "cha"]],
  ["cleric", ["wis", "cha"]],
  ["druid", ["int", "wis"]],
  ["fighter", ["str", "con"]],
  ["monk", ["str", "dex"]],
  ["paladin", ["wis", "cha"]],
  ["ranger", ["str", "dex"]],
  ["rogue", ["dex", "int"]],
  ["sorcerer", ["con", "cha"]],
  ["warlock", ["wis", "cha"]],
  ["wizard", ["int", "wis"]],
]);

const ABILITY_KEYS = ["str", "dex", "con", "int", "wis", "cha"];
const ABILITY_LABELS = { str: "STR", dex: "DEX", con: "CON", int: "INT", wis: "WIS", cha: "CHA" };
const ABILITY_SKILL_GROUPS = {
  str: ["athletics"],
  dex: ["acrobatics", "sleight_of_hand", "stealth"],
  con: [],
  int: ["arcana", "history", "investigation", "nature", "religion"],
  wis: ["animal_handling", "insight", "medicine", "perception", "survival"],
  cha: ["deception", "intimidation", "performance", "persuasion"],
};
const SKILL_TO_ABILITY = {
  acrobatics: "dex", animal_handling: "wis", arcana: "int", athletics: "str", deception: "cha",
  history: "int", insight: "wis", intimidation: "cha", investigation: "int", medicine: "wis",
  nature: "int", perception: "wis", performance: "cha", persuasion: "cha", religion: "int",
  sleight_of_hand: "dex", stealth: "dex", survival: "wis",
};
const TOOL_OPTIONS = [
  "Alchemist’s Supplies", "Brewer’s Supplies", "Calligrapher’s Supplies", "Carpenter’s Tools", "Cartographer’s Tools",
  "Cobbler’s Tools", "Cook’s Utensils", "Glassblower’s Tools", "Jeweler’s Tools", "Leatherworker’s Tools", "Mason’s Tools",
  "Painter’s Supplies", "Potter’s Tools", "Smith’s Tools", "Tinker’s Tools", "Weaver’s Tools", "Woodcarver’s Tools",
  "Disguise Kit", "Forgery Kit", "Herbalism Kit", "Navigator’s Tools", "Poisoner’s Kit", "Thieves’ Tools",
  "Dice (Gaming set)", "Dragonchess", "Playing Cards", "Three-dragon Ante", "Bagpipes", "Drum", "Dulcimer", "Flute",
  "Horn", "Lute", "Lyre", "Pan Flute", "Shawm", "Viol"
];
const WEAPON_OPTIONS = ["Club", "Dagger", "Greatclub", "Handaxe", "Javelin", "Light Hammer", "Mace", "Quarterstaff", "Sickle", "Spear", "Light Crossbow", "Dart", "Shortbow", "Sling", "Battleaxe", "Flail", "Glaive", "Greataxe", "Greatsword", "Halberd", "Lance", "Longsword", "Maul", "Morningstar", "Pike", "Rapier", "Scimitar", "Shortsword", "Trident", "War Pick", "Warhammer", "Whip", "Blowgun", "Hand Crossbow", "Heavy Crossbow", "Longbow", "Musket", "Pistol"];
const ARMOR_OPTIONS = ["ALL light armor", "ALL medium armor", "ALL heavy armor", "Shield"];
const BROAD_WEAPON_OPTIONS = ["ALL simple weapons", "ALL martial weapons"];
const SIMPLE_WEAPONS = new Set(["Club", "Dagger", "Greatclub", "Handaxe", "Javelin", "Light Hammer", "Mace", "Quarterstaff", "Sickle", "Spear", "Light Crossbow", "Dart", "Shortbow", "Sling"]);
const HIDDEN_ROOT_FIELDS = new Set(["campaign", "ip"]);
const DAMAGE_TYPES = [
  "slashing", "slashing_non_magical", "piercing", "piercing_non_magical", "bludgeoning", "bludgeoning_non_magical",
  "acid", "cold", "fire", "force", "lightning", "necrotic", "poison", "psychic", "radiant", "thunder"
];
const INITIATIVE_TOKENS = ["str_mod", "dex_mod", "con_mod", "int_mod", "wis_mod", "cha_mod", "proficiency_bonus"];


const abilityModifier = (score) => Math.floor((Number(score || 0) - 10) / 2);
const proficiencyBonusForLevel = (level) => Math.min(6, 2 + Math.floor((Math.max(1, Number(level || 1)) - 1) / 4));
const totalLevelFromData = (data) => {
  const classes = Array.isArray(data?.leveling?.classes) ? data.leveling.classes : [];
  const classTotal = classes.reduce((sum, entry) => sum + Math.max(0, Number(entry?.level || 0)), 0);
  return classTotal || Math.max(0, Number(data?.leveling?.level || 0));
};
const deriveHitDiceRows = (classes) => {
  const byDie = {};
  (classes || []).forEach((entry) => {
    const die = HIT_DICE_BY_CLASS.get(String(entry?.name || '').trim().toLowerCase());
    const lvl = Math.max(0, Number(entry?.level || 0));
    if (!die || !lvl) return;
    byDie[die] = (byDie[die] || 0) + lvl;
  });
  return HIT_DICE_ORDER.filter((die) => byDie[die]).map((die) => ({ die, max: byDie[die] }));
};
const ensurePerDieTracker = (data) => {
  if (!data.vitals) data.vitals = {};
  if (!data.vitals.hit_dice_tracker || typeof data.vitals.hit_dice_tracker !== 'object') data.vitals.hit_dice_tracker = {};
  const tracker = data.vitals.hit_dice_tracker;
  deriveHitDiceRows(data?.leveling?.classes).forEach(({die, max}) => {
    if (!tracker[die] || typeof tracker[die] !== 'object') tracker[die] = { max, remaining: max };
    tracker[die].max = max;
    if (tracker[die].remaining === undefined || tracker[die].remaining === null) tracker[die].remaining = max;
    tracker[die].remaining = Math.max(0, Math.min(max, Number(tracker[die].remaining || 0)));
  });
};


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
  let saveOverride = false;
  let boundForm = null;
  let boundData = null;
  let lastAutoSaves = new Set();

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
    const leveling = boundData?.leveling || {};
    const levelFromClasses = Array.isArray(leveling?.classes)
      ? leveling.classes.reduce((sum, entry) => sum + Number(entry?.level ?? 0), 0)
      : 0;
    const totalLevel = levelFromClasses || Number(leveling?.level ?? 0) || 1;
    const proficiency = Math.min(6, 2 + Math.floor((Math.max(1, totalLevel) - 1) / 4));
    const hitDie = getHitDice(leveling?.classes);

    if (hitDie) {
      applyAutoValue("vitals.hit_dice.die", hitDie);
    }
    if (totalLevel) {
      applyAutoValue("vitals.hit_dice.total", totalLevel);
    }
    applyAutoValue("proficiency.bonus", proficiency);
    if (!saveOverride && Array.isArray(leveling?.classes) && leveling.classes.length) {
      let best = null;
      leveling.classes.forEach((entry, idx) => {
        const lvl = Number(entry?.level ?? 0);
        if (!best || lvl > best.lvl) {
          best = { idx, lvl, name: String(entry?.name || "").trim().toLowerCase() };
        }
      });
      const autoSaves = new Set((SAVE_PROFICIENCIES.get(best?.name) || []).map((s) => s.toLowerCase()));
      const currentSaves = new Set((Array.isArray(boundData?.proficiency?.saves) ? boundData.proficiency.saves : []).map((s) => String(s).toLowerCase()));
      const manual = new Set(Array.from(currentSaves).filter((s) => !lastAutoSaves.has(s)));
      const merged = Array.from(new Set([...manual, ...autoSaves])).map((s) => s.toUpperCase());
      applyAutoValue("proficiency.saves", merged);
      lastAutoSaves = autoSaves;
    }

    const castingAbility = String(boundData?.spellcasting?.casting_ability || "").trim();
    if (castingAbility && Number.isFinite(proficiency)) {
      applyAutoValue("spellcasting.save_dc_formula", "8 + proficiency_bonus + casting_mod");
      applyAutoValue("spellcasting.spell_attack_formula", "proficiency_bonus + casting_mod");
    }

    ABILITY_KEYS.forEach((ability) => {
      const el = boundForm?.querySelector(`[data-mod-for="abilities.${ability}"]`);
      if (el) {
        const modValue = toModifier(abilities?.[ability] ?? 10);
        el.textContent = modValue >= 0 ? `+${modValue}` : String(modValue);
      }
    });

    ensurePerDieTracker(boundData);

    const passiveBlocks = ["base_10", "wis_mod"];
    const profSkills = new Set((boundData?.proficiency?.skills?.proficient || []).map((v)=>String(v).toLowerCase()));
    const expSkills = new Set((boundData?.proficiency?.skills?.expertise || []).map((v)=>String(v).toLowerCase()));
    if (profSkills.has("perception")) passiveBlocks.push("proficiency_bonus");
    if (expSkills.has("perception")) passiveBlocks.push("proficiency_bonus");
    applyAutoValue("vitals.passive_perception.formula", passiveBlocks);
    const passiveValue = 10 + toModifier(abilities?.wis ?? 10) + (profSkills.has("perception") ? proficiency : 0) + (expSkills.has("perception") ? proficiency : 0);
    applyAutoValue("vitals.passive_perception.value", passiveValue);

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
      if (String(path).startsWith("proficiency.saves")) saveOverride = true;
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

  const resetSaveProficiencySync = () => { saveOverride = false; recalculate(); };

  return {
    bind,
    handleChange,
    recalculate,
    resetSaveProficiencySync,
  };
})();

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
    if (path.join(".") === "spellcasting.enabled") {
      input = document.createElement("button");
      input.type = "button";
      input.dataset.path = path.join(".");
      input.className = `spell-toggle ${Boolean(value) ? "on" : "off"}`;
      input.textContent = Boolean(value) ? "Spellcasting Enabled" : "Spellcasting Disabled";
      input.addEventListener("click", () => {
        const next = !Boolean(getValueAtPath(data, path));
        setValueAtPath(data, path, next);
        input.className = `spell-toggle ${next ? "on" : "off"}`;
        input.textContent = next ? "Spellcasting Enabled" : "Spellcasting Disabled";
      });
    } else {
      input = document.createElement("input");
      input.type = "checkbox";
      input.dataset.path = path.join(".");
      input.checked = Boolean(value);
      input.addEventListener("change", () => {
        setValueAtPath(data, path, input.checked);
      });
    }
  } else if (path.join(".") === "proficiency.bonus") {
    input = document.createElement("input");
    input.type = "number";
    input.dataset.path = path.join(".");
    input.value = value ?? 2;
    input.readOnly = true;
  } else if (ABILITY_KEYS.includes(path[path.length - 1]) && path[0] === "abilities") {
    const row = document.createElement("div");
    row.className = "ability-row";
    const mod = document.createElement("span");
    mod.className = "ability-mod";
    mod.dataset.modFor = path.join(".");
    const m = Math.floor((Number(value ?? 10) - 10) / 2);
    mod.textContent = m >= 0 ? `+${m}` : String(m);
    input = document.createElement("input");
    input.type = "number";
    input.dataset.path = path.join(".");
    input.value = value ?? 10;
    input.addEventListener("input", () => {
      const nextValue = input.value === "" ? 0 : Number(input.value);
      setValueAtPath(data, path, Math.trunc(nextValue));
      const mm = Math.floor((Math.trunc(nextValue) - 10) / 2);
      mod.textContent = mm >= 0 ? `+${mm}` : String(mm);
    });
    row.append(mod, input);
    wrapper.appendChild(row);
    appendHelpText(wrapper, field);
    return wrapper;
  } else if (path.join(".") === "leveling.classes.name") {
    input = document.createElement("select");
    input.dataset.path = path.join(".");
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
    input.addEventListener("change", () => {
      setValueAtPath(data, path, input.value);
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


const renderSavesMatrix = (path, data) => {
  const container = document.createElement("div");
  container.className = "field-group";
  const head = document.createElement("div");
  head.className = "array-header";
  const title = document.createElement("h3");
  title.textContent = "Saving Throws";
  const reset = document.createElement("button");
  reset.type = "button";
  reset.className = "ghost";
  reset.textContent = "Reset to Class Defaults";
  reset.addEventListener("click", () => derivedStats.resetSaveProficiencySync());
  head.append(title, reset);
  container.appendChild(head);
  const current = new Set((getValueAtPath(data, path) || []).map((v) => String(v).toLowerCase()));
  const expPath = ["proficiency", "save_expertise"];
  const expCurrent = new Set((getValueAtPath(data, expPath) || []).map((v) => String(v).toLowerCase()));
  ABILITY_KEYS.forEach((ability) => {
    const row = document.createElement("div");
    row.className = "save-row";
    const label = document.createElement("span");
    label.textContent = ABILITY_LABELS[ability];
    const prof = document.createElement("input");
    prof.type = "checkbox";
    prof.checked = current.has(ability);
    prof.addEventListener("change", () => {
      const next = new Set((getValueAtPath(data, path) || []).map((v) => String(v).toLowerCase()));
      if (prof.checked) next.add(ability); else next.delete(ability);
      setValueAtPath(data, path, Array.from(next).map((v) => v.toUpperCase()));
    });
    const exp = document.createElement("input");
    exp.type = "checkbox";
    exp.checked = expCurrent.has(ability);
    exp.addEventListener("change", () => {
      const next = new Set((getValueAtPath(data, expPath) || []).map((v) => String(v).toLowerCase()));
      if (exp.checked) next.add(ability); else next.delete(ability);
      setValueAtPath(data, expPath, Array.from(next).map((v) => v.toUpperCase()));
    });
    const profLabel = document.createElement("label"); profLabel.textContent = "Proficient";
    const expLabel = document.createElement("label"); expLabel.textContent = "Expertise";
    row.append(label, profLabel, prof, expLabel, exp);
    container.appendChild(row);
  });
  return container;
};

const renderSkillsMatrix = (data) => {
  const container = document.createElement("div");
  container.className = "field-group";
  const title = document.createElement("h3");
  title.textContent = "Skills";
  container.appendChild(title);
  const profBonus = Number(getValueAtPath(data, ["proficiency", "bonus"]) || 2);

  Object.entries(ABILITY_SKILL_GROUPS).forEach(([ability, skills]) => {
    const group = document.createElement("div");
    group.className = "field-group";
    const groupTitle = document.createElement("h3");
    groupTitle.textContent = ABILITY_LABELS[ability];
    group.appendChild(groupTitle);

    skills.forEach((skill) => {
      const row = document.createElement("div");
      row.className = "save-row";
      const label = document.createElement("span");
      label.textContent = skill.replaceAll("_", " ");
      const prof = document.createElement("input");
      prof.type = "checkbox";
      const exp = document.createElement("input");
      exp.type = "checkbox";
      const bonus = document.createElement("strong");
      const sync = () => {
        const profSet = new Set((getValueAtPath(data, ["proficiency", "skills", "proficient"]) || []).map((v) => String(v).toLowerCase()));
        const expSet = new Set((getValueAtPath(data, ["proficiency", "skills", "expertise"]) || []).map((v) => String(v).toLowerCase()));
        prof.checked = profSet.has(skill);
        exp.checked = expSet.has(skill);
        const scoreMod = abilityModifier(getValueAtPath(data, ["abilities", ability]) || 10);
        const total = scoreMod + (prof.checked ? profBonus : 0) + (exp.checked ? profBonus : 0);
        bonus.textContent = total >= 0 ? `+${total}` : String(total);
      };
      prof.addEventListener("change", () => {
        const profSet = new Set((getValueAtPath(data, ["proficiency", "skills", "proficient"]) || []).map((v) => String(v).toLowerCase()));
        if (prof.checked) profSet.add(skill); else profSet.delete(skill);
        setValueAtPath(data, ["proficiency", "skills", "proficient"], Array.from(profSet));
        if (!prof.checked) {
          const expSet = new Set((getValueAtPath(data, ["proficiency", "skills", "expertise"]) || []).map((v) => String(v).toLowerCase()));
          expSet.delete(skill);
          setValueAtPath(data, ["proficiency", "skills", "expertise"], Array.from(expSet));
        }
        derivedStats.handleChange("proficiency.skills.proficient", { source: "system" });
        sync();
      });
      exp.addEventListener("change", () => {
        const expSet = new Set((getValueAtPath(data, ["proficiency", "skills", "expertise"]) || []).map((v) => String(v).toLowerCase()));
        const profSet = new Set((getValueAtPath(data, ["proficiency", "skills", "proficient"]) || []).map((v) => String(v).toLowerCase()));
        if (exp.checked) {
          expSet.add(skill);
          profSet.add(skill);
        } else {
          expSet.delete(skill);
        }
        setValueAtPath(data, ["proficiency", "skills", "expertise"], Array.from(expSet));
        setValueAtPath(data, ["proficiency", "skills", "proficient"], Array.from(profSet));
        derivedStats.handleChange("proficiency.skills.expertise", { source: "system" });
        sync();
      });
      sync();
      const l1 = document.createElement("label"); l1.textContent = "Proficient";
      const l2 = document.createElement("label"); l2.textContent = "Expertise";
      row.append(label, l1, prof, l2, exp, bonus);
      group.appendChild(row);
    });
    container.appendChild(group);
  });
  return container;
};

const renderChecklistArray = (titleText, options, path, data) => {
  const container = document.createElement("div");
  container.className = "field-group";
  const title = document.createElement("h3"); title.textContent = titleText; container.appendChild(title);
  const set = new Set((getValueAtPath(data, path) || []).map((v) => String(v).toLowerCase()));
  options.forEach((opt) => {
    const row = document.createElement("label");
    row.className = "check-row";
    const cb = document.createElement("input"); cb.type="checkbox"; cb.checked = set.has(opt.toLowerCase());
    cb.addEventListener("change", () => {
      const next = new Set((getValueAtPath(data, path) || []).map((v) => String(v).toLowerCase()));
      if (cb.checked) next.add(opt.toLowerCase()); else next.delete(opt.toLowerCase());
      setValueAtPath(data, path, Array.from(next));
    });
    const txt=document.createElement("span"); txt.textContent=opt;
    row.append(cb,txt); container.appendChild(row);
  });
  return container;
};

const renderCanonicalProficiencies = (path, data) => {
  const container = document.createElement("div");
  container.className = "field-group";
  const wep = document.createElement("div"); wep.className = "field-group";
  const wtitle = document.createElement("h3"); wtitle.textContent = "Weapons"; wep.appendChild(wtitle);
  const toolsPath = path;
  const getSet = () => new Set((getValueAtPath(data, toolsPath) || []).map((v) => String(v).toLowerCase()));
  const saveSet = (set) => setValueAtPath(data, toolsPath, Array.from(set));
  BROAD_WEAPON_OPTIONS.forEach((opt) => {
    const row = document.createElement("label"); row.className = "check-row";
    const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = getSet().has(opt.toLowerCase());
    cb.addEventListener("change", () => {
      const set = getSet();
      if (cb.checked) set.add(opt.toLowerCase()); else set.delete(opt.toLowerCase());
      saveSet(set);
    });
    const txt = document.createElement("span"); txt.textContent = opt;
    row.append(cb, txt); wep.appendChild(row);
  });
  WEAPON_OPTIONS.forEach((opt) => {
    const row = document.createElement("label"); row.className = "check-row";
    const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = getSet().has(opt.toLowerCase());
    cb.addEventListener("change", () => { const set = getSet(); if (cb.checked) set.add(opt.toLowerCase()); else set.delete(opt.toLowerCase()); saveSet(set); });
    const txt = document.createElement("span"); txt.textContent = opt;
    row.append(cb, txt); wep.appendChild(row);
  });

  const armor = document.createElement("div"); armor.className = "field-group";
  const at = document.createElement("h3"); at.textContent = "Armor"; armor.appendChild(at);
  ARMOR_OPTIONS.forEach((opt) => {
    const row = document.createElement("label"); row.className = "check-row";
    const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = getSet().has(opt.toLowerCase());
    cb.addEventListener("change", () => { const set = getSet(); if (cb.checked) set.add(opt.toLowerCase()); else set.delete(opt.toLowerCase()); saveSet(set); });
    const txt = document.createElement("span"); txt.textContent = opt.replace('ALL ', '');
    row.append(cb, txt); armor.appendChild(row);
  });
  const help = document.createElement("p"); help.className = "field-help"; help.textContent = "Untrained armor gives disadvantage on STR/DEX d20 tests and blocks spellcasting. Heavy armor STR requirements can reduce speed.";
  armor.appendChild(help);

  const tools = document.createElement("div"); tools.className = "field-group";
  const tt = document.createElement("h3"); tt.textContent = "Tools"; tools.appendChild(tt);
  const select = document.createElement("select");
  const blank = document.createElement("option"); blank.value=''; blank.textContent='Add tool proficiency'; select.appendChild(blank);
  TOOL_OPTIONS.forEach((opt)=>{const o=document.createElement('option');o.value=opt.toLowerCase();o.textContent=opt;select.appendChild(o);});
  const add = document.createElement("button"); add.type='button'; add.className='ghost'; add.textContent='Add Tool';
  const list = document.createElement("div");
  const renderTools = ()=>{
    list.innerHTML='';
    const set = getSet();
    Array.from(set).filter((v)=>TOOL_OPTIONS.map((x)=>x.toLowerCase()).includes(v)).forEach((tool)=>{
      const row=document.createElement('div'); row.className='save-row';
      const name=document.createElement('span'); name.textContent=tool;
      const rm=document.createElement('button'); rm.type='button'; rm.className='ghost danger'; rm.textContent='Remove';
      rm.addEventListener('click',()=>{const s=getSet(); s.delete(tool); saveSet(s); renderTools();});
      row.append(name,rm); list.appendChild(row);
    });
  };
  add.addEventListener('click',()=>{if(!select.value)return; const set=getSet(); set.add(select.value); saveSet(set); renderTools();});
  tools.append(select, add, list);
  renderTools();

  container.append(wep, armor, tools);
  return container;
};

const renderHitDiceTracker = (data) => {
  ensurePerDieTracker(data);
  const container = document.createElement('div'); container.className='field-group';
  const title = document.createElement('h3'); title.textContent='Per-die Hit Dice Tracker'; container.appendChild(title);
  const tracker = data?.vitals?.hit_dice_tracker || {};
  deriveHitDiceRows(data?.leveling?.classes).forEach(({die,max})=>{
    const row=document.createElement('div'); row.className='save-row';
    const name=document.createElement('span'); name.textContent=die;
    const maxEl=document.createElement('span'); maxEl.textContent=`max ${max}`;
    const input=document.createElement('input'); input.type='number'; input.value=tracker?.[die]?.remaining ?? max;
    input.addEventListener('input',()=>{tracker[die].remaining=Math.max(0,Math.min(max,Number(input.value||0)));});
    row.append(name,maxEl,input); container.appendChild(row);
  });
  return container;
};

const renderPassivePerceptionBlocks = (path, data) => {
  const container=document.createElement('div'); container.className='field-group';
  const title=document.createElement('h3'); title.textContent='Passive Perception'; container.appendChild(title);
  const blocks = Array.isArray(getValueAtPath(data,path)) ? getValueAtPath(data,path) : ['base_10','wis_mod'];
  const formula=document.createElement('p'); formula.className='field-help'; formula.textContent=`Formula: ${blocks.join(' + ')}`;
  const value = Number(getValueAtPath(data,['vitals','passive_perception','value'])||10);
  const valInput=document.createElement('input'); valInput.type='number'; valInput.value=value; valInput.readOnly=true;
  container.append(formula,valInput);
  return container;
};

const renderInitiativeBlocks = (path, data) => {
  const container = document.createElement("div"); container.className = "field-group";
  const title = document.createElement("h3"); title.textContent = "Initiative Formula Blocks"; container.appendChild(title);
  const rawValue = getValueAtPath(data, path);
  let blocks = Array.isArray(rawValue) ? rawValue : String(rawValue || "dex_mod").split("+").map((v)=>v.trim()).filter(Boolean);
  if (!blocks.length) blocks=["dex_mod"];
  const list = document.createElement("div");
  const render = () => {
    list.innerHTML = "";
    blocks.forEach((token, idx) => {
      const row = document.createElement("div"); row.className="save-row";
      const select = document.createElement("select");
      INITIATIVE_TOKENS.forEach((t)=>{const o=document.createElement('option');o.value=t;o.textContent=t;o.selected=t===token;select.appendChild(o);});
      select.addEventListener("change", ()=>{blocks[idx]=select.value;setValueAtPath(data,path,[...blocks]);});
      const remove=document.createElement("button"); remove.type='button'; remove.className='ghost danger'; remove.textContent='×';
      remove.addEventListener('click',()=>{if(blocks.length>1){blocks.splice(idx,1);setValueAtPath(data,path,[...blocks]);render();}});
      row.append(select, remove); list.appendChild(row);
    });
  };
  const add = document.createElement("button"); add.type='button'; add.className='ghost'; add.textContent='+';
  add.addEventListener('click',()=>{blocks.push('dex_mod');setValueAtPath(data,path,[...blocks]);render();});
  container.append(list, add); render();
  return container;
};


const inferActionTypeFromSpell = (spellId, spellDetails) => {
  const spell = (spellDetails || []).find((entry) => entry?.id === spellId);
  const casting = String(spell?.casting_time || "").toLowerCase();
  if (casting.includes("reaction")) return "reaction";
  if (casting.includes("bonus")) return "bonus";
  return "action";
};

const ensurePoolsFromFeatures = (data) => {
  const pools = Array.isArray(data?.resources?.pools) ? data.resources.pools : [];
  const byId = new Map(pools.map((pool) => [String(pool?.id || ""), pool]));
  const features = Array.isArray(data?.features) ? data.features : [];
  features.forEach((feature) => {
    const granted = feature?.grants?.pools || [];
    granted.forEach((pool) => {
      const id = String(pool?.id || "").trim();
      if (!id) return;
      if (!byId.has(id)) {
        const created = { id, label: pool?.label || id, max_formula: pool?.max_formula || "1", reset: pool?.reset || "long_rest", current: 0 };
        pools.push(created);
        byId.set(id, created);
      }
    });
  });
  if (!data.resources) data.resources = {};
  data.resources.pools = pools;
};

const renderFeatsEditor = (path, data) => {
  const container = document.createElement("div");
  container.className = "feats-editor";
  const list = document.createElement("div");
  list.className = "feats-list";
  const detail = document.createElement("div");
  detail.className = "feats-detail";
  const header = document.createElement("div");
  header.className = "array-header";
  const title = document.createElement("h3");
  title.textContent = "Feats";
  const add = document.createElement("button");
  add.type = "button"; add.className = "ghost"; add.textContent = "Add Feat";
  header.append(title, add);
  container.append(header);
  const body = document.createElement("div"); body.className = "feats-body";
  body.append(list, detail);
  container.append(body);

  let selected = 0;
  let dirty = false;
  const feats = () => getValueAtPath(data, path) || [];

  const markDirty = () => { dirty = true; statusEl.textContent = "Unsaved changes"; };
  const markSaved = () => { dirty = false; };

  const renderDetail = async () => {
    detail.innerHTML = "";
    const feat = feats()[selected];
    if (!feat) return;
    ["id", "name", "category", "source", "description"].forEach((fieldKey) => {
      const row = document.createElement("div"); row.className = "field";
      const label = document.createElement("label"); label.textContent = fieldKey;
      const input = fieldKey === "description" ? document.createElement("textarea") : document.createElement("input");
      if (fieldKey !== "description") input.type = "text";
      input.value = feat[fieldKey] || "";
      input.addEventListener("input", () => { feat[fieldKey] = input.value; markDirty(); renderList(); });
      row.append(label, input); detail.append(row);
    });

    const cfg = document.createElement("button"); cfg.type = "button"; cfg.className = "ghost"; cfg.textContent = "Configure granted pools & spells…";
    cfg.addEventListener("click", async () => {
      const overlay = document.createElement("div"); overlay.className = "overlay";
      const modal = document.createElement("div"); modal.className = "overlay-modal";
      const h = document.createElement("h3"); h.textContent = "Granted Pools & Spells";
      modal.appendChild(h);

      if (!feat.grants) feat.grants = {};
      if (!Array.isArray(feat.grants.pools)) feat.grants.pools = [];
      if (!feat.grants.spells) feat.grants.spells = { cantrips: [], casts: [] };
      if (!Array.isArray(feat.grants.spells.cantrips)) feat.grants.spells.cantrips = [];
      if (!Array.isArray(feat.grants.spells.casts)) feat.grants.spells.casts = [];

      const poolsWrap = document.createElement("div"); poolsWrap.className = "field-group";
      const poolsTitle = document.createElement("h4"); poolsTitle.textContent = "Resource Pools"; poolsWrap.appendChild(poolsTitle);
      const poolAdd = document.createElement("button"); poolAdd.type = "button"; poolAdd.className = "ghost"; poolAdd.textContent = "Add Pool";
      poolsWrap.appendChild(poolAdd);
      const poolRows = document.createElement("div"); poolsWrap.appendChild(poolRows);

      const renderPools = () => {
        poolRows.innerHTML = "";
        feat.grants.pools.forEach((pool, idx) => {
          const row = document.createElement("div"); row.className = "array-item";
          const reset = pool.reset || "long_rest";
          row.innerHTML = `<input type="text" data-k="id" placeholder="id" value="${pool.id||""}">
<input type="text" data-k="label" placeholder="label" value="${pool.label||""}">
<input type="text" data-k="max_formula" placeholder="max formula" value="${pool.max_formula||"1"}">`;
          const sel = document.createElement("select");
          ["short_rest","long_rest"].forEach((v)=>{const o=document.createElement('option');o.value=v;o.textContent=v;o.selected=v===reset;sel.appendChild(o);});
          sel.addEventListener("change", ()=>{pool.reset=sel.value;markDirty();});
          const rm = document.createElement("button"); rm.type="button"; rm.className="ghost danger"; rm.textContent="Remove";
          rm.addEventListener("click", ()=>{feat.grants.pools.splice(idx,1);renderPools();markDirty();});
          row.querySelectorAll("input").forEach((inp)=>inp.addEventListener("input",()=>{pool[inp.dataset.k]=inp.value;markDirty();}));
          row.append(sel, rm);
          poolRows.appendChild(row);
        });
      };
      poolAdd.addEventListener("click", ()=>{feat.grants.pools.push({id:"",label:"",max_formula:"1",reset:"long_rest"});renderPools();markDirty();});
      renderPools();

      const spellWrap = document.createElement("div"); spellWrap.className = "field-group";
      const spellTitle = document.createElement("h4"); spellTitle.textContent = "Granted Spells"; spellWrap.appendChild(spellTitle);
      const spellAdd = document.createElement("button"); spellAdd.type = "button"; spellAdd.className = "ghost"; spellAdd.textContent = "Add Spell";
      spellWrap.appendChild(spellAdd);
      const spellRows = document.createElement("div"); spellWrap.appendChild(spellRows);
      const spellPayload = await loadSpellData();
      const spells = Array.isArray(spellPayload?.spells) ? spellPayload.spells : [];

      const renderSpells = () => {
        spellRows.innerHTML = "";
        feat.grants.spells.casts.forEach((cast, idx) => {
          const row = document.createElement("div"); row.className = "array-item";
          const spellSel = document.createElement("select");
          const blank = document.createElement("option"); blank.value=""; blank.textContent="Select spell"; spellSel.appendChild(blank);
          spells.forEach((sp)=>{const o=document.createElement('option');o.value=sp.id;o.textContent=`${sp.name||sp.id}`;o.selected=sp.id===cast.spell;spellSel.appendChild(o);});
          spellSel.addEventListener("change", ()=>{cast.spell=spellSel.value;cast.action_type=inferActionTypeFromSpell(cast.spell,spells);markDirty();});
          const action = document.createElement("input"); action.type='text'; action.value=cast.action_type||"action"; action.readOnly=true;
          const poolSel = document.createElement("select");
          const poolBlank = document.createElement('option'); poolBlank.value=''; poolBlank.textContent='Pool'; poolSel.appendChild(poolBlank);
          const allPools = [...(data?.resources?.pools || []), ...(feat.grants.pools || [])];
          allPools.forEach((pool)=>{const id=pool?.id||''; if(!id) return; const o=document.createElement('option');o.value=id;o.textContent=id;o.selected=id===cast?.consumes?.pool;poolSel.appendChild(o);});
          poolSel.addEventListener("change", ()=>{cast.consumes = cast.consumes || {}; cast.consumes.pool = poolSel.value; markDirty();});
          const cost = document.createElement("input"); cost.type='number'; cost.value=cast?.consumes?.cost ?? 1;
          cost.addEventListener("input", ()=>{cast.consumes = cast.consumes || {}; cast.consumes.cost = Number(cost.value || 1); markDirty();});
          const dmg = document.createElement("input"); dmg.type='text'; dmg.placeholder='damage rider'; dmg.value=cast.damage_rider||'';
          dmg.addEventListener("input", ()=>{cast.damage_rider=dmg.value; markDirty();});
          const rm = document.createElement("button"); rm.type='button'; rm.className='ghost danger'; rm.textContent='Remove';
          rm.addEventListener("click", ()=>{feat.grants.spells.casts.splice(idx,1);renderSpells();markDirty();});
          row.append(spellSel, action, poolSel, cost, dmg, rm);
          spellRows.appendChild(row);
        });
      };
      spellAdd.addEventListener("click", ()=>{feat.grants.spells.casts.push({spell:"",action_type:"action",consumes:{pool:"",cost:1}});renderSpells();markDirty();});
      renderSpells();

      const controls = document.createElement("div"); controls.className = "action-buttons";
      const saveBtn = document.createElement("button"); saveBtn.type='button'; saveBtn.className='primary'; saveBtn.textContent='Save Grants';
      const closeBtn = document.createElement("button"); closeBtn.type='button'; closeBtn.className='ghost'; closeBtn.textContent='Close';
      saveBtn.addEventListener('click',()=>{ensurePoolsFromFeatures(data); markDirty(); overlay.remove();});
      closeBtn.addEventListener('click',()=>overlay.remove());
      controls.append(saveBtn, closeBtn);

      modal.append(poolsWrap, spellWrap, controls);
      overlay.appendChild(modal);
      document.body.appendChild(overlay);
    });
    detail.appendChild(cfg);

    const saveIndicator = document.createElement("p"); saveIndicator.className = "status"; saveIndicator.textContent = dirty ? "Unsaved changes" : "";
    detail.appendChild(saveIndicator);
  };

  const renderList = () => {
    list.innerHTML = "";
    feats().forEach((feat, idx) => {
      const btn = document.createElement("button"); btn.type = "button";
      btn.className = `ghost feat-item${idx === selected ? " active" : ""}`;
      btn.textContent = feat?.name || feat?.id || `Feat ${idx + 1}`;
      btn.addEventListener("click", async () => {
        if (dirty && !window.confirm("You have unsaved feat changes. Switch anyway?")) return;
        selected = idx;
        await renderDetail();
        renderList();
      });
      list.appendChild(btn);
    });
  };

  add.addEventListener("click", async () => {
    const next = feats();
    next.push({ id: "", name: "", category: "", source: "", description: "", grants: { pools: [], spells: { cantrips: [], casts: [] } } });
    setValueAtPath(data, path, next);
    selected = next.length - 1;
    dirty = true;
    renderList();
    await renderDetail();
  });

  renderList();
  renderDetail();
  return container;
};

const renderSpellPicker = (field, path, data) => {
  const isCantripPicker = spellPathKey(path) === "spellcasting.cantrips.known";
  const isKnownSpellPicker = spellPathKey(path) === "spellcasting.known_spells.known";
  const SORT_MODES = {
    alphabetical: "Alphabetical",
    level: "Level",
  };
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

  const sortSelect = document.createElement("select");
  sortSelect.className = "spell-sort";
  Object.entries(SORT_MODES).forEach(([value, label]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    sortSelect.appendChild(option);
  });
  controls.appendChild(sortSelect);

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

  const spellDisplayById = new Map();
  let spellIndex = new Map();
  let availableSpells = [];
  let lastKnownSpellLevel = null;

  const getSpellName = (spell) => {
    const rawName = typeof spell?.name === "string" ? spell.name.trim() : "";
    if (rawName) {
      return rawName;
    }
    return spell?.id || "";
  };

  const getSpellLevelLabel = (spell) => {
    const level = getSpellLevelFromRecord(spell);
    if (level === 0) {
      return "Cantrip";
    }
    if (level === null) {
      return "Level ?";
    }
    return `Level ${level}`;
  };

  const getSpellDisplayLabel = (spell) => {
    const name = getSpellName(spell);
    const levelLabel = getSpellLevelLabel(spell);
    if (!name) {
      return "";
    }
    return `${name} (${levelLabel})`;
  };

  const normalizeSpellName = (name) => (name || "").trim().toLowerCase();

  const buildSpellIndex = (spells) => {
    spellDisplayById.clear();
    const nextIndex = new Map();
    spells.forEach((spell) => {
      if (!spell?.id) {
        return;
      }
      const name = getSpellName(spell);
      const label = getSpellDisplayLabel(spell);
      spellDisplayById.set(spell.id, label || spell.id);
      [spell.id, name, label].forEach((candidate) => {
        if (!candidate) {
          return;
        }
        const key = normalizeSpellName(candidate);
        if (!nextIndex.has(key)) {
          nextIndex.set(key, spell);
        }
      });
    });
    spellIndex = nextIndex;
  };

  const sortSpells = (spells, mode) => {
    const sorted = [...spells];
    if (mode === "level") {
      sorted.sort((a, b) => {
        const levelA = getSpellLevelFromRecord(a);
        const levelB = getSpellLevelFromRecord(b);
        const levelDiff = (levelA ?? Number.POSITIVE_INFINITY) - (levelB ?? Number.POSITIVE_INFINITY);
        if (levelDiff !== 0) {
          return levelDiff;
        }
        const nameA = normalizeSpellName(getSpellName(a));
        const nameB = normalizeSpellName(getSpellName(b));
        return nameA.localeCompare(nameB);
      });
      return sorted;
    }
    sorted.sort((a, b) => {
      const nameA = normalizeSpellName(getSpellName(a));
      const nameB = normalizeSpellName(getSpellName(b));
      return nameA.localeCompare(nameB);
    });
    return sorted;
  };

  const renderDatalist = () => {
    datalist.innerHTML = "";
    const sorted = sortSpells(availableSpells, sortSelect.value);
    sorted.forEach((spell) => {
      const label = getSpellDisplayLabel(spell);
      if (!label) {
        return;
      }
      const option = document.createElement("option");
      option.value = label;
      datalist.appendChild(option);
    });
    setStatus(sorted.length ? "Select spells from the list." : "No spells found.");
  };

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
      label.textContent = spellDisplayById.get(spellId) || spellId;
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

  const addSpell = (spellEntry) => {
    const normalized = normalizeSpellName(spellEntry);
    if (!normalized) {
      return;
    }
    const match = spellIndex.get(normalized);
    if (!match) {
      setStatus(`Spell "${spellEntry}" not found.`);
      return;
    }
    const spellId = match.id;
    const value = getValueAtPath(data, path) || [];
    if (value.includes(spellId)) {
      setStatus(`"${spellDisplayById.get(spellId) || spellId}" is already selected.`);
      return;
    }
    value.push(spellId);
    setValueAtPath(data, path, value);
    input.value = "";
    setStatus(`${spellDisplayById.get(spellId) || spellId} added.`);
    renderSelected();
  };

  const loadAvailableSpells = async () => {
    const payload = await loadSpellData();
    const spells = Array.isArray(payload?.spells) ? payload.spells : [];
    if (spells.length) {
      return spells;
    }
    return (Array.isArray(payload?.ids) ? payload.ids : []).map((id) => ({ id }));
  };

  const loadAndRenderSpells = async () => {
    let spells = await loadAvailableSpells();
    if (isCantripPicker) {
      spells = spells.filter((spell) => getSpellLevelFromRecord(spell) === 0);
    } else if (isKnownSpellPicker) {
      const maxLevel = maxSpellLevelForCharacter(getCharacterLevel(data));
      spells = spells.filter((spell) => {
        const level = getSpellLevelFromRecord(spell);
        return level !== null && level <= maxLevel;
      });
      lastKnownSpellLevel = maxLevel;
    }
    availableSpells = spells;
    buildSpellIndex(spells);
    renderDatalist();
  };

  addButton.addEventListener("click", async () => {
    await loadAndRenderSpells();
    addSpell(input.value);
  });

  input.addEventListener("keydown", async (event) => {
    if (event.key !== "Enter") {
      return;
    }
    event.preventDefault();
    await loadAndRenderSpells();
    addSpell(input.value);
  });

  sortSelect.addEventListener("change", () => {
    renderDatalist();
  });

  if (isKnownSpellPicker && formEl) {
    const handleLevelChange = async (event) => {
      const targetPath = event?.target?.dataset?.path;
      if (!targetPath) {
        return;
      }
      if (targetPath === "leveling.level" || targetPath.startsWith("leveling.classes")) {
        const maxLevel = maxSpellLevelForCharacter(getCharacterLevel(data));
        if (maxLevel !== lastKnownSpellLevel) {
          await loadAndRenderSpells();
        }
      }
    };
    formEl.addEventListener("input", handleLevelChange);
    formEl.addEventListener("change", handleLevelChange);
  }

  loadAndRenderSpells();

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
      input.dataset.path = inputPath.join(".");
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
  const pathText = path.join(".");
  if (pathText === "proficiency.saves") { return renderSavesMatrix(path, data); }
  if (pathText === "proficiency.skills.proficient") { return renderSkillsMatrix(data); }
  if (pathText === "proficiency.skills.expertise") { const d=document.createElement("div"); d.style.display="none"; return d; }
  if (pathText === "proficiency.tools") { return renderCanonicalProficiencies(path, data); }
  if (pathText === "defenses.resistances") { return renderChecklistArray("Resistances", DAMAGE_TYPES, path, data); }
  if (pathText === "defenses.immunities") { return renderChecklistArray("Immunities", DAMAGE_TYPES, path, data); }
  if (pathText === "defenses.vulnerabilities") { return renderChecklistArray("Vulnerabilities", DAMAGE_TYPES, path, data); }
  if (pathText === "vitals.initiative.formula") { return renderInitiativeBlocks(path, data); }
  if (pathText === "vitals.passive_perception.formula") { return renderPassivePerceptionBlocks(path, data); }
  if (pathText === "vitals.hit_dice") { return renderHitDiceTracker(data); }
  if (pathText === "features") { return renderFeatsEditor(path, data); }
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
      (section.fields || []).filter((field) => !(section.id === "root" && HIDDEN_ROOT_FIELDS.has(field.key))).forEach((field) => {
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


const sanitizeCharacterPayload = (data) => {
  if (!data || typeof data !== "object") return data;
  const payload = clone(data);
  delete payload.format_version;
  return payload;
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
    ensurePoolsFromFeatures(data);
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

const boot = async () => {
  const schema = await loadSchema();
  const defaults = buildDefaultsFromSchema(schema);
  const draft = loadDraft(defaults);
  const data = draft.data;
  renderForm(schema, data);
  derivedStats.bind(formEl, data);
  derivedStats.recalculate();
  formEl.addEventListener("input", () => { statusEl.textContent = "Unsaved changes"; });
  formEl.addEventListener("change", () => { statusEl.textContent = "Unsaved changes"; });
  formEl.addEventListener("input", (event) => {
    if (event.target?.dataset?.path === "name" || event.target?.dataset?.path === "identity.name") {
      if (filenameInput && !filenameInput.value.trim()) {
        filenameInput.value = `${slugify(data?.name || "")}.yaml`;
      }
    }
  });
  if (filenameInput) {
    filenameInput.value = draft.filename || `${slugify(data?.name || "")}.yaml`;
    filenameInput.addEventListener("input", () => {
      saveDraft(data, filenameInput.value, { showStatus: false });
    });
  }
  button.addEventListener("click", () => saveDraft(data, filenameInput?.value || ""));
  if (exportButton) {
    exportButton.addEventListener("click", () => exportYaml(data));
  }

  if (resetButton) {
    resetButton.addEventListener("click", () => {
      const fresh = buildDefaultsFromSchema(schema);
      Object.keys(data).forEach((key) => delete data[key]);
      Object.assign(data, fresh);
      renderForm(schema, data);
      derivedStats.bind(formEl, data);
      derivedStats.recalculate();
      saveDraft(data, filenameInput?.value || "", { showStatus: false });
      statusEl.textContent = "Reset to schema defaults.";
    });
  }

  if (clearDraftButton) {
    clearDraftButton.addEventListener("click", () => {
      window.localStorage.removeItem(STORAGE_KEY);
      statusEl.textContent = "Local draft cleared.";
    });
  }
};

boot();
