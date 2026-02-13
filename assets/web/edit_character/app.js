const statusEl = document.getElementById("draft-status");
const overwriteButton = document.getElementById("overwrite-button");
const refreshCacheButton = document.getElementById("refresh-cache-button");
const exportButton = document.getElementById("export-button");
const formEl = document.getElementById("character-form");
const filenameInput = document.getElementById("filename-input");
const characterSelect = document.getElementById("character-select");
const openCharacterButton = document.getElementById("open-character-button");
const uploadYamlInput = document.getElementById("upload-yaml-input");
const uploadYamlButton = document.getElementById("upload-yaml-button");

const REQUIRED_EDITOR_ELEMENT_IDS = [
  "draft-status",
  "overwrite-button",
  "refresh-cache-button",
  "export-button",
  "filename-input",
  "character-form",
  "character-select",
  "open-character-button",
  "upload-yaml-input",
  "upload-yaml-button",
];

const assertRequiredEditorElements = () => {
  const missing = REQUIRED_EDITOR_ELEMENT_IDS.filter((id) => !document.getElementById(id));
  if (!missing.length) {
    return;
  }
  const banner = document.createElement("div");
  banner.setAttribute("role", "alert");
  banner.style.background = "#7f1d1d";
  banner.style.color = "#fff";
  banner.style.padding = "12px 16px";
  banner.style.margin = "12px";
  banner.style.borderRadius = "8px";
  banner.style.fontFamily = "system-ui, sans-serif";
  banner.style.fontSize = "14px";
  banner.style.lineHeight = "1.4";
  banner.textContent = `Editor failed to start. Missing required element IDs: ${missing.join(", ")}`;
  document.body.prepend(banner);
  throw new Error(`Edit character template missing required IDs: ${missing.join(", ")}`);
};

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
const getDruidLevelFromData = (data) => {
  const classes = Array.isArray(data?.leveling?.classes) ? data.leveling.classes : [];
  if (classes.length) {
    return classes.reduce((sum, entry) => {
      const className = String(entry?.name || "").trim().toLowerCase();
      if (className !== "druid") {
        return sum;
      }
      return sum + Math.max(0, Number(entry?.level || 0));
    }, 0);
  }
  const className = String(data?.leveling?.class || "").trim().toLowerCase();
  if (className === "druid") {
    return Math.max(0, Number(data?.leveling?.level || 0));
  }
  return 0;
};

const isPreparedWildShapesFieldVisible = (field, data, sectionId) => {
  if (sectionId !== "root" || field?.key !== "prepared_wild_shapes") {
    return true;
  }
  return getDruidLevelFromData(data) >= 2;
};

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



const featEditorGuard = {
  hasPendingChanges: () => false,
  resolvePendingChanges: () => true,
};

const slugifyFeatId = (value) => {
  const normalized = String(value || "")
    .toLowerCase()
    .replace(/\s+/g, "_")
    .replace(/[^a-z0-9_]/g, "")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "");
  return normalized || "custom_feat";
};

const createUniqueFeatId = (name, existingIds, fallback = "custom_feat") => {
  const root = slugifyFeatId(name || fallback);
  let next = root;
  let suffix = 2;
  while (existingIds.has(next)) {
    next = `${root}_${suffix}`;
    suffix += 1;
  }
  return next;
};

const inferActionTypeFromSpell = (spellId, spellDetails) => {
  const spell = (spellDetails || []).find((entry) => entry?.id === spellId);
  const casting = String(spell?.casting_time || "").toLowerCase();
  if (casting.includes("reaction")) return { value: "reaction", unknown: false };
  if (casting.includes("bonus")) return { value: "bonus", unknown: false };
  if (casting.includes("minute")) return { value: "minute", unknown: false };
  if (casting.includes("hour")) return { value: "hour", unknown: false };
  if (casting.includes("action")) return { value: "action", unknown: false };
  return { value: "action", unknown: true };
};

const ACTION_TYPE_OPTIONS = [
  { value: "action", label: "Action" },
  { value: "bonus", label: "Bonus Action" },
  { value: "reaction", label: "Reaction" },
  { value: "free", label: "Free (Any Time)" },
  { value: "minute", label: "1+ Minute" },
  { value: "hour", label: "1+ Hour" },
  { value: "special", label: "Special" },
];

const collectFeatPoolIds = (feature) => {
  const pools = Array.isArray(feature?.grants?.pools) ? feature.grants.pools : [];
  return pools.map((entry) => String(entry?.id || "").trim()).filter(Boolean);
};

const ensurePoolsFromFeatures = (data, { confirmOverwrite } = {}) => {
  const pools = Array.isArray(data?.resources?.pools) ? data.resources.pools : [];
  const features = Array.isArray(data?.features) ? data.features : [];
  const featManaged = new Set();
  features.forEach((feature) => collectFeatPoolIds(feature).forEach((id) => featManaged.add(id)));
  const byId = new Map(pools.map((pool) => [String(pool?.id || "").trim(), pool]));
  let blocked = false;
  features.forEach((feature) => {
    const granted = Array.isArray(feature?.grants?.pools) ? feature.grants.pools : [];
    granted.forEach((pool) => {
      const id = String(pool?.id || "").trim();
      if (!id) return;
      const next = {
        id,
        label: pool?.label || id,
        max_formula: pool?.max_formula || "1",
        reset: pool?.reset === "short_rest" ? "short_rest" : "long_rest",
      };
      const existing = byId.get(id);
      if (!existing) {
        pools.push({ ...next, current: 0 });
        byId.set(id, pools[pools.length - 1]);
        return;
      }
      const external = !featManaged.has(id);
      if (external && confirmOverwrite) {
        const ok = confirmOverwrite(id, existing, next);
        if (!ok) {
          blocked = true;
          return;
        }
      }
      existing.label = next.label;
      existing.max_formula = next.max_formula;
      existing.reset = next.reset;
      if (existing.current === undefined || existing.current === null) {
        existing.current = 0;
      }
    });
  });
  if (!data.resources) data.resources = {};
  data.resources.pools = pools;
  return !blocked;
};

const renderFeatsEditor = (path, data) => {
  const container = document.createElement("div");
  container.className = "feats-editor";

  const header = document.createElement("div");
  header.className = "feats-toolbar";
  const search = document.createElement("input");
  search.type = "search";
  search.placeholder = "Filter feats…";
  const add = document.createElement("button");
  add.type = "button";
  add.className = "ghost";
  add.textContent = "+ Add Feat";
  header.append(search, add);

  const list = document.createElement("div");
  list.className = "feats-list";
  const detail = document.createElement("div");
  detail.className = "feats-detail";
  const body = document.createElement("div");
  body.className = "feats-body";
  body.append(list, detail);

  container.append(header, body);

  const feats = () => {
    const current = getValueAtPath(data, path);
    return Array.isArray(current) ? current : [];
  };

  let selectedIndex = 0;
  let featDraft = null;
  let featSnapshot = null;
  let grantsModalOpen = false;
  const dirtyByIndex = new Set();

  const hasUnsaved = () => JSON.stringify(featDraft || {}) !== JSON.stringify(featSnapshot || {});
  const syncStatus = () => {
    if (hasUnsaved()) {
      statusEl.textContent = "Unsaved feat changes";
      dirtyByIndex.add(selectedIndex);
    } else {
      dirtyByIndex.delete(selectedIndex);
    }
  };

  const loadSelection = (index) => {
    const selected = feats()[index];
    if (!selected) {
      featDraft = null;
      featSnapshot = null;
      return;
    }
    selectedIndex = index;
    featDraft = clone(selected);
    featSnapshot = clone(selected);
    syncStatus();
  };

  const saveSelectedFeat = () => {
    if (!featDraft) return true;
    const all = feats();
    all[selectedIndex] = clone(featDraft);
    setValueAtPath(data, path, all);
    featSnapshot = clone(featDraft);
    syncStatus();
    renderList();
    renderDetail();
    return true;
  };

  const discardSelectedChanges = () => {
    if (!featSnapshot) return;
    featDraft = clone(featSnapshot);
    syncStatus();
    renderList();
    renderDetail();
  };

  const resolveUnsavedFeat = () => {
    if (!hasUnsaved()) return true;
    const shouldSave = window.confirm("You have unsaved changes to this feat. Save or discard?\n\nPress OK to Save, Cancel to Discard.");
    if (shouldSave) {
      return saveSelectedFeat();
    }
    discardSelectedChanges();
    return true;
  };

  const openGrantsModal = async () => {
    if (!featDraft) return;
    grantsModalOpen = true;
    const overlay = document.createElement("div");
    overlay.className = "overlay grants-overlay";
    overlay.tabIndex = -1;

    const modal = document.createElement("div");
    modal.className = "overlay-modal grants-modal";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");

    const modalHeader = document.createElement("div");
    modalHeader.className = "grants-modal-header";
    const title = document.createElement("h3");
    title.textContent = `Configure Grants — ${featDraft.name || featDraft.id || "Feat"}`;
    const closeX = document.createElement("button");
    closeX.type = "button";
    closeX.className = "ghost";
    closeX.textContent = "✕";
    modalHeader.append(title, closeX);

    const tabs = document.createElement("div");
    tabs.className = "grants-tabs";
    const poolsTab = document.createElement("button");
    poolsTab.type = "button"; poolsTab.className = "tab-button active"; poolsTab.textContent = "Resource Pools";
    const spellsTab = document.createElement("button");
    spellsTab.type = "button"; spellsTab.className = "tab-button"; spellsTab.textContent = "Granted Spells";
    tabs.append(poolsTab, spellsTab);

    const poolsPane = document.createElement("div");
    poolsPane.className = "grants-pane active";
    const spellsPane = document.createElement("div");
    spellsPane.className = "grants-pane";

    const footer = document.createElement("div");
    footer.className = "action-buttons";
    const cancel = document.createElement("button");
    cancel.type = "button"; cancel.className = "ghost"; cancel.textContent = "Cancel";
    const apply = document.createElement("button");
    apply.type = "button"; apply.className = "primary"; apply.textContent = "Apply";
    footer.append(cancel, apply);

    const grants = clone(featDraft.grants || {});
    if (!Array.isArray(grants.pools)) grants.pools = [];
    if (!grants.spells || typeof grants.spells !== "object") grants.spells = {};
    if (!Array.isArray(grants.spells.casts)) grants.spells.casts = [];
    const snapshot = JSON.stringify(grants);

    const poolIdsFromOtherFeats = () => {
      const ids = new Set();
      feats().forEach((feature, idx) => {
        if (idx === selectedIndex) return;
        collectFeatPoolIds(feature).forEach((id) => ids.add(id));
      });
      return ids;
    };

    const renderPools = () => {
      poolsPane.innerHTML = "";
      const error = document.createElement("p");
      error.className = "status";
      const rows = document.createElement("div");
      rows.className = "grants-list";
      const duplicateIds = new Set();
      const seen = new Set();
      const existingResourceIds = new Set((Array.isArray(data?.resources?.pools) ? data.resources.pools : []).map((pool) => String(pool?.id || "").trim()).filter(Boolean));
      const otherFeatIds = poolIdsFromOtherFeats();

      grants.pools.forEach((pool, idx) => {
        const id = String(pool?.id || "").trim();
        if (id && seen.has(id)) duplicateIds.add(id);
        if (id) seen.add(id);

        const row = document.createElement("div");
        row.className = "save-row";
        const idInput = document.createElement("input"); idInput.type = "text"; idInput.placeholder = "id"; idInput.value = pool?.id || "";
        const labelInput = document.createElement("input"); labelInput.type = "text"; labelInput.placeholder = "label"; labelInput.value = pool?.label || "";
        const formulaInput = document.createElement("input"); formulaInput.type = "text"; formulaInput.placeholder = "max_formula"; formulaInput.value = pool?.max_formula || "1";
        const resetInput = document.createElement("select");
        ["short_rest", "long_rest"].forEach((entry) => {
          const option = document.createElement("option");
          option.value = entry;
          option.textContent = entry;
          option.selected = entry === (pool?.reset || "long_rest");
          resetInput.appendChild(option);
        });
        const remove = document.createElement("button"); remove.type = "button"; remove.className = "ghost danger"; remove.textContent = "Remove";

        idInput.addEventListener("input", () => {
          const previous = String(grants.pools[idx]?.id || "").trim();
          grants.pools[idx].id = idInput.value;
          const next = String(idInput.value || "").trim();
          if (previous && next && previous !== next) {
            grants.spells.casts.forEach((cast) => {
              if (cast?.consumes?.pool === previous) {
                cast.consumes.pool = next;
              }
            });
          }
        });
        labelInput.addEventListener("input", () => { grants.pools[idx].label = labelInput.value; });
        formulaInput.addEventListener("input", () => { grants.pools[idx].max_formula = formulaInput.value; });
        resetInput.addEventListener("change", () => { grants.pools[idx].reset = resetInput.value; });
        remove.addEventListener("click", () => {
          const removed = String(grants.pools[idx]?.id || "").trim();
          grants.pools.splice(idx, 1);
          grants.spells.casts.forEach((cast) => {
            if (cast?.consumes?.pool === removed) {
              delete cast.consumes;
            }
          });
          renderPools();
          renderSpells();
        });

        row.append(idInput, labelInput, formulaInput, resetInput, remove);
        rows.appendChild(row);
      });

      const hasConflict = grants.pools.some((pool) => {
        const id = String(pool?.id || "").trim();
        if (!id) return false;
        if (duplicateIds.has(id)) return true;
        if (otherFeatIds.has(id)) return true;
        if (existingResourceIds.has(id) && !collectFeatPoolIds(feats()[selectedIndex]).includes(id)) {
          return false;
        }
        return false;
      });

      if (duplicateIds.size) {
        error.textContent = `Duplicate pool ID(s): ${Array.from(duplicateIds).join(", ")}`;
      } else if (grants.pools.some((pool) => otherFeatIds.has(String(pool?.id || "").trim()))) {
        error.textContent = "Pool IDs must be unique across all feats.";
      } else {
        error.textContent = "";
      }
      apply.disabled = Boolean(error.textContent) || grants.pools.some((pool) => !String(pool?.id || "").trim());

      const addPool = document.createElement("button");
      addPool.type = "button";
      addPool.className = "ghost";
      addPool.textContent = "+ Add Resource Pool";
      addPool.addEventListener("click", () => {
        grants.pools.push({ id: "", label: "", max_formula: "1", reset: "long_rest" });
        renderPools();
      });

      const savePools = document.createElement("button");
      savePools.type = "button";
      savePools.className = "primary";
      savePools.textContent = "Save Resource Pools";
      savePools.disabled = apply.disabled;
      savePools.addEventListener("click", () => {
        featDraft.grants = clone(grants);
        const committed = saveSelectedFeat();
        if (!committed) return;
        const ok = ensurePoolsFromFeatures(data, {
          confirmOverwrite: (id) => window.confirm(`Pool '${id}' already exists in character resources. Overwrite it with feat configuration?`),
        });
        if (!ok) return;
        statusEl.textContent = "Unsaved changes";
        renderPools();
        renderSpells();
      });

      poolsPane.append(error, rows, addPool, savePools);
    };

    const { spells } = await loadSpellData();

    const renderSpells = () => {
      spellsPane.innerHTML = "";
      const toolbar = document.createElement("div");
      toolbar.className = "array-header";
      const addCantrip = document.createElement("button"); addCantrip.type = "button"; addCantrip.className = "ghost"; addCantrip.textContent = "+ Add Cantrip";
      const addSpell = document.createElement("button"); addSpell.type = "button"; addSpell.className = "ghost"; addSpell.textContent = "+ Add Spell";
      toolbar.append(addCantrip, addSpell);
      spellsPane.appendChild(toolbar);

      const rows = document.createElement("div");
      rows.className = "grants-list";

      grants.spells.casts.forEach((cast, idx) => {
        const row = document.createElement("div");
        row.className = "granted-spell-row";

        const levelHint = Number(cast?.level_hint ?? 1);
        const poolChoices = [
          ...(Array.isArray(data?.resources?.pools) ? data.resources.pools : []),
          ...grants.pools,
        ].map((entry) => String(entry?.id || "").trim()).filter(Boolean);

        const select = document.createElement("select");
        const placeholder = document.createElement("option"); placeholder.value = ""; placeholder.textContent = "Select spell";
        select.appendChild(placeholder);
        spells.filter((entry) => {
          const level = getSpellLevelFromRecord(entry);
          return levelHint === 0 ? level === 0 : level !== 0;
        }).forEach((entry) => {
          const option = document.createElement("option");
          option.value = entry.id;
          option.textContent = `${entry.name || entry.id}`;
          option.selected = entry.id === cast.spell;
          select.appendChild(option);
        });
        select.addEventListener("change", () => {
          cast.spell = select.value;
          const actionMeta = inferActionTypeFromSpell(cast.spell, spells);
          cast.action_type = actionMeta.value;
          cast.action_type_unknown = actionMeta.unknown;
          renderSpells();
        });

        const actionTypeSelect = document.createElement("select");
        ACTION_TYPE_OPTIONS.forEach((entry) => {
          const option = document.createElement("option");
          option.value = entry.value;
          option.textContent = `Activation: ${entry.label}`;
          option.selected = (cast?.action_type || "action") === entry.value;
          actionTypeSelect.appendChild(option);
        });
        actionTypeSelect.addEventListener("change", () => {
          cast.action_type = actionTypeSelect.value;
          cast.action_type_unknown = false;
        });

        const actionWarn = document.createElement("span");
        actionWarn.className = "status";
        actionWarn.textContent = cast?.action_type_unknown ? "Action type unknown; defaulted to Action" : "";

        const consumesType = document.createElement("select");
        [{ value: "none", label: "Consumes: None" }, { value: "pool", label: "Consumes: Resource Pool" }].forEach((entry) => {
          const option = document.createElement("option");
          option.value = entry.value;
          option.textContent = entry.label;
          option.selected = (cast?.consumes?.pool ? "pool" : "none") === entry.value;
          consumesType.appendChild(option);
        });

        const poolSelect = document.createElement("select");
        const blankPool = document.createElement("option"); blankPool.value = ""; blankPool.textContent = "Select pool";
        poolSelect.appendChild(blankPool);
        poolChoices.forEach((id) => {
          const option = document.createElement("option");
          option.value = id;
          option.textContent = id;
          option.selected = cast?.consumes?.pool === id;
          poolSelect.appendChild(option);
        });
        poolSelect.disabled = !cast?.consumes?.pool && consumesType.value === "none";

        const cost = document.createElement("input");
        cost.type = "number";
        cost.min = "1";
        cost.value = Number(cast?.consumes?.cost || 1);
        cost.disabled = consumesType.value === "none";

        consumesType.addEventListener("change", () => {
          if (consumesType.value === "none") {
            delete cast.consumes;
          } else {
            cast.consumes = cast.consumes || { pool: "", cost: 1 };
          }
          renderSpells();
        });
        poolSelect.addEventListener("change", () => {
          cast.consumes = cast.consumes || { cost: 1 };
          cast.consumes.pool = poolSelect.value;
        });
        cost.addEventListener("input", () => {
          cast.consumes = cast.consumes || { pool: "" };
          cast.consumes.cost = Math.max(1, Number(cost.value || 1));
        });

        const advanced = document.createElement("details");
        const advancedSummary = document.createElement("summary");
        advancedSummary.textContent = "Advanced";
        const modifierInput = document.createElement("input");
        modifierInput.type = "text";
        modifierInput.placeholder = "modifier";
        modifierInput.value = cast?.modifier || "";
        modifierInput.addEventListener("input", () => { cast.modifier = modifierInput.value; });
        const damageRider = document.createElement("input");
        damageRider.type = "text";
        damageRider.placeholder = "damage rider";
        damageRider.value = cast?.damage_rider || "";
        damageRider.addEventListener("input", () => { cast.damage_rider = damageRider.value; });
        advanced.append(advancedSummary, modifierInput, damageRider);

        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "ghost danger";
        remove.textContent = "Remove";
        remove.addEventListener("click", () => {
          grants.spells.casts.splice(idx, 1);
          renderSpells();
        });

        row.append(select, actionTypeSelect, actionWarn, consumesType, poolSelect, cost, advanced, remove);
        rows.appendChild(row);
      });

      addCantrip.addEventListener("click", () => {
        grants.spells.casts.push({ spell: "", level_hint: 0, action_type: "action" });
        renderSpells();
      });
      addSpell.addEventListener("click", () => {
        grants.spells.casts.push({ spell: "", level_hint: 1, action_type: "action" });
        renderSpells();
      });

      spellsPane.appendChild(rows);
    };

    const hasModalUnsaved = () => JSON.stringify(grants) !== snapshot;
    const closeWithGuard = () => {
      if (hasModalUnsaved()) {
        const shouldClose = window.confirm("You have unsaved changes to this feat grants modal. Discard changes?");
        if (!shouldClose) return;
      }
      overlay.remove();
      grantsModalOpen = false;
      renderDetail();
    };

    tabs.addEventListener("click", (event) => {
      const btn = event.target.closest("button");
      if (!btn) return;
      const poolsActive = btn === poolsTab;
      poolsTab.classList.toggle("active", poolsActive);
      spellsTab.classList.toggle("active", !poolsActive);
      poolsPane.classList.toggle("active", poolsActive);
      spellsPane.classList.toggle("active", !poolsActive);
    });

    closeX.addEventListener("click", closeWithGuard);
    cancel.addEventListener("click", closeWithGuard);
    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) closeWithGuard();
    });
    overlay.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeWithGuard();
      }
      if (event.key === "Tab") {
        const focusable = modal.querySelectorAll("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])");
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    });

    apply.addEventListener("click", () => {
      featDraft.grants = clone(grants);
      const committed = saveSelectedFeat();
      if (!committed) return;
      const ok = ensurePoolsFromFeatures(data, {
        confirmOverwrite: (id) => window.confirm(`Pool '${id}' already exists in character resources. Overwrite it with feat configuration?`),
      });
      if (!ok) return;
      overlay.remove();
      grantsModalOpen = false;
      statusEl.textContent = "Unsaved changes";
      renderDetail();
    });

    modal.append(modalHeader, tabs, poolsPane, spellsPane, footer);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
    renderPools();
    renderSpells();
    closeX.focus();
  };

  const renderList = () => {
    list.innerHTML = "";
    const query = search.value.trim().toLowerCase();
    feats().forEach((feat, idx) => {
      const title = String(feat?.name || feat?.id || `Feat ${idx + 1}`);
      const subtitle = [feat?.category, feat?.source].filter(Boolean).join(" · ");
      if (query && !`${title} ${subtitle}`.toLowerCase().includes(query)) {
        return;
      }
      const row = document.createElement("button");
      row.type = "button";
      row.className = `feat-row${idx === selectedIndex ? " active" : ""}`;
      const name = document.createElement("strong");
      name.textContent = title;
      const meta = document.createElement("small");
      meta.textContent = subtitle;
      const dirty = document.createElement("span");
      dirty.className = "feat-dirty";
      dirty.textContent = dirtyByIndex.has(idx) ? "●" : "";
      row.append(name, meta, dirty);
      row.addEventListener("click", () => {
        if (idx === selectedIndex) return;
        if (!resolveUnsavedFeat()) return;
        loadSelection(idx);
        renderList();
        renderDetail();
      });
      list.appendChild(row);
    });
  };

  const renderDetail = () => {
    detail.innerHTML = "";
    if (!featDraft) {
      const empty = document.createElement("p");
      empty.className = "status";
      empty.textContent = "No feat selected.";
      detail.appendChild(empty);
      return;
    }

    const fields = ["id", "name", "category", "source", "description"];
    fields.forEach((fieldKey) => {
      const row = document.createElement("div");
      row.className = "field";
      const label = document.createElement("label");
      label.textContent = fieldKey;
      const input = fieldKey === "description" ? document.createElement("textarea") : document.createElement("input");
      if (fieldKey !== "description") input.type = "text";
      input.value = featDraft[fieldKey] || "";
      input.addEventListener("input", () => {
        featDraft[fieldKey] = input.value;
        syncStatus();
        renderList();
      });
      row.append(label, input);
      detail.appendChild(row);
    });

    const actions = document.createElement("div");
    actions.className = "action-buttons";
    const save = document.createElement("button");
    save.type = "button"; save.className = "primary"; save.textContent = "Save Feat Changes";
    const revert = document.createElement("button");
    revert.type = "button"; revert.className = "ghost"; revert.textContent = "Revert";
    const remove = document.createElement("button");
    remove.type = "button"; remove.className = "ghost danger"; remove.textContent = "Remove Feat";
    const grants = document.createElement("button");
    grants.type = "button"; grants.className = "ghost"; grants.textContent = "Configure Grants…";

    save.addEventListener("click", saveSelectedFeat);
    revert.addEventListener("click", discardSelectedChanges);
    remove.addEventListener("click", () => {
      if (!window.confirm("Remove this feat?")) return;
      const all = feats();
      all.splice(selectedIndex, 1);
      setValueAtPath(data, path, all);
      selectedIndex = Math.max(0, selectedIndex - 1);
      loadSelection(selectedIndex);
      statusEl.textContent = "Unsaved changes";
      renderList();
      renderDetail();
    });
    grants.addEventListener("click", openGrantsModal);

    actions.append(save, revert, remove, grants);
    detail.appendChild(actions);
  };

  const openAddFeatPicker = () => {
    if (!resolveUnsavedFeat()) return;
    const overlay = document.createElement("div");
    overlay.className = "overlay";
    const modal = document.createElement("div");
    modal.className = "overlay-modal";
    const heading = document.createElement("h3");
    heading.textContent = "Add Feat";
    const helper = document.createElement("p");
    helper.className = "status";
    helper.textContent = "Feat library unavailable in this repo. Create a custom feat.";
    const nameInput = document.createElement("input");
    nameInput.type = "text";
    nameInput.placeholder = "Feat name";
    const create = document.createElement("button");
    create.type = "button";
    create.className = "primary";
    create.textContent = "Create Custom Feat";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "ghost";
    cancel.textContent = "Cancel";
    const footer = document.createElement("div");
    footer.className = "action-buttons";
    footer.append(cancel, create);
    modal.append(heading, helper, nameInput, footer);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    cancel.addEventListener("click", () => overlay.remove());
    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) overlay.remove();
    });
    create.addEventListener("click", () => {
      const all = feats();
      const existing = new Set(all.map((entry) => String(entry?.id || "").trim()).filter(Boolean));
      const name = nameInput.value.trim() || "Custom Feat";
      const id = createUniqueFeatId(name, existing);
      all.push({ id, name, category: "", source: "", description: "", grants: { pools: [], spells: { casts: [] } } });
      setValueAtPath(data, path, all);
      selectedIndex = all.length - 1;
      loadSelection(selectedIndex);
      statusEl.textContent = "Unsaved changes";
      overlay.remove();
      renderList();
      renderDetail();
    });
  };

  featEditorGuard.hasPendingChanges = () => hasUnsaved() || grantsModalOpen;
  featEditorGuard.resolvePendingChanges = () => resolveUnsavedFeat();

  add.addEventListener("click", openAddFeatPicker);
  search.addEventListener("input", renderList);

  if (!feats().length) {
    setValueAtPath(data, path, []);
  }
  loadSelection(0);
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
  let activeTabId = TAB_LAYOUT[0]?.id || "basic";
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
    if (activeTabId === "feats" && target !== "feats" && featEditorGuard.hasPendingChanges()) {
      const ok = featEditorGuard.resolvePendingChanges();
      if (!ok) {
        return;
      }
    }
    activeTabId = target;
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
      (section.fields || []).filter((field) => !(section.id === "root" && HIDDEN_ROOT_FIELDS.has(field.key)) && isPreparedWildShapesFieldVisible(field, data, section.id)).forEach((field) => {
        const fieldPath = sectionPath.length ? [...sectionPath, field.key] : [field.key];
        const fieldValue = getValueAtPath(data, fieldPath);
        sectionEl.appendChild(renderField(field, fieldPath, data, fieldValue));
      });
    } else if (section.type === "array") {
      const sectionPathText = sectionPath.join(".");
      if (section.id === "features" || sectionPathText === "features") {
        sectionEl.appendChild(renderFeatsEditor(sectionPath, data));
      } else {
        sectionEl.appendChild(renderArrayField(section, sectionPath, data));
      }
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


const refreshPlayerCache = async () => {
  try {
    const response = await fetch("/api/players/cache/refresh", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({ clear_only: false })});
    statusEl.textContent = response.ok ? "Player cache refreshed." : "Unable to refresh cache.";
  } catch (_error) {
    statusEl.textContent = "Unable to refresh cache.";
  }
};

const fetchCharacterList = async () => {
  try {
    const response = await fetch("/api/characters");
    if (!response.ok) return [];
    const payload = await response.json();
    return Array.isArray(payload?.files) ? payload.files : [];
  } catch (_error) {
    return [];
  }
};

const fetchCharacterByName = async (name) => {
  const normalized = String(name || "").trim();
  if (!normalized) return null;
  try {
    const response = await fetch(`/api/characters/${encodeURIComponent(normalized)}`);
    if (!response.ok) return null;
    return await response.json();
  } catch (_error) {
    return null;
  }
};

const selectedCharacterFromUrl = () => {
  const params = new URLSearchParams(window.location.search || "");
  return String(params.get("file") || "").trim();
};

const populateCharacterSelect = (files, selectedFile) => {
  if (!characterSelect) return;
  characterSelect.textContent = "";
  const chooseOption = document.createElement("option");
  chooseOption.value = "";
  chooseOption.textContent = "Choose a YAML file…";
  characterSelect.appendChild(chooseOption);
  for (const file of files) {
    const option = document.createElement("option");
    option.value = file;
    option.textContent = file;
    characterSelect.appendChild(option);
  }
  characterSelect.value = selectedFile && files.includes(selectedFile) ? selectedFile : "";
};

const openSelectedCharacter = () => {
  const selected = String(characterSelect?.value || "").trim();
  if (!selected) {
    statusEl.textContent = "Choose a YAML file first.";
    return;
  }
  const nextUrl = new URL(window.location.href);
  nextUrl.searchParams.set("file", selected);
  window.location.href = nextUrl.toString();
};

const uploadYaml = async () => {
  const file = uploadYamlInput?.files?.[0];
  if (!file) {
    statusEl.textContent = "Choose a YAML file to upload.";
    return;
  }
  try {
    const yamlText = await file.text();
    const response = await fetch("/api/characters/upload", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename: file.name, yaml_text: yamlText }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload?.detail?.message || "upload failed");
    const saved = String(payload?.filename || file.name);
    statusEl.textContent = `Uploaded ${saved}.`;
    const nextUrl = new URL(window.location.href);
    nextUrl.searchParams.set("file", saved);
    window.location.href = nextUrl.toString();
  } catch (_error) {
    statusEl.textContent = "Unable to upload YAML. Please check the file and try again.";
  }
};

const overwriteCharacter = async (data, originalFilename) => {
  const target = originalFilename || filenameInput?.value || "";
  if (!target) { statusEl.textContent = "No character selected to overwrite."; return originalFilename; }
  try {
    ensurePoolsFromFeatures(data);
    const response = await fetch(`/api/characters/${encodeURIComponent(target)}/overwrite`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ data: sanitizeCharacterPayload(data), filename: filenameInput?.value || "" }),
    });
    if (!response.ok) throw new Error("overwrite failed");
    const payload = await response.json();
    const saved = payload?.filename || target;
    if (filenameInput) filenameInput.value = saved;
    statusEl.textContent = `Saved ${saved}.`;
    return saved;
  } catch (_error) {
    statusEl.textContent = "Unable to overwrite character. Please try again.";
    return originalFilename;
  }
};

const boot = async () => {
  const schema = await loadSchema();
  const defaults = buildDefaultsFromSchema(schema);
  let data = defaults;
  let originalFilename = "";
  const files = await fetchCharacterList();
  const selectedFile = selectedCharacterFromUrl();
  populateCharacterSelect(files, selectedFile);
  const selectedCharacter = await fetchCharacterByName(selectedFile);
  if (selectedCharacter?.character) {
    data = mergeDefaults(selectedCharacter.character, defaults);
    originalFilename = selectedCharacter.filename || selectedFile || "";
  }
  if (filenameInput) filenameInput.value = originalFilename;
  renderForm(schema, data);
  derivedStats.bind(formEl, data);
  derivedStats.recalculate();
  formEl.addEventListener("input", () => { statusEl.textContent = "Unsaved changes"; });
  formEl.addEventListener("change", () => { statusEl.textContent = "Unsaved changes"; });
  window.addEventListener("beforeunload", (event) => {
    if (!featEditorGuard.hasPendingChanges()) return;
    event.preventDefault();
    event.returnValue = "You have unsaved changes to this feat. Save or discard?";
  });
  if (exportButton) exportButton.addEventListener("click", () => exportYaml(data));
  if (refreshCacheButton) refreshCacheButton.addEventListener("click", refreshPlayerCache);
  if (openCharacterButton) openCharacterButton.addEventListener("click", openSelectedCharacter);
  if (uploadYamlButton) uploadYamlButton.addEventListener("click", uploadYaml);
  if (overwriteButton) {
    overwriteButton.addEventListener("click", async () => { originalFilename = await overwriteCharacter(data, originalFilename); });
  }
  statusEl.textContent = originalFilename ? `Loaded ${originalFilename}.` : "Choose a YAML file and click Open selected YAML.";
};

assertRequiredEditorElements();
boot();
