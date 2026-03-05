import unittest
import json
import os
import tempfile
from unittest import mock

import dnd_initative_tracker as tracker_mod


class _MockHttpResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class DmMapAttackAutomationTests(unittest.TestCase):
    def setUp(self):
        self.logs = []
        self.app = object.__new__(tracker_mod.InitiativeTracker)
        self.app._log = lambda message, cid=None: self.logs.append((cid, message))
        self.app._queue_concentration_save = lambda *_args, **_kwargs: None
        self.app._display_order = lambda: [self.app.combatants[cid] for cid in sorted(self.app.combatants.keys())]
        self.app._retarget_current_after_removal = lambda removed, pre_order=None: None
        self.app._rebuild_table = lambda scroll_to_current=True: None
        self.app._death_flavor_line = lambda attacker, amount, dtype, target: f"{attacker} downs {target} with {amount} {dtype}".strip()
        self.app._lan = None
        self.app.start_cid = None
        self.app._name_role_memory = {"Death Slaad": "pc", "Knight": "enemy"}

    def test_monster_attack_options_parse_slaad_actions_and_multiattack_counts(self):
        attacker = type(
            "Combatant",
            (),
            {
                "monster_spec": type(
                    "Spec",
                    (),
                    {
                        "raw_data": {
                            "actions": [
                                {
                                    "name": "Multiattack",
                                    "desc": "The slaad makes three attacks: one with its bite and two with its claws or greatsword.",
                                },
                                {
                                    "name": "Bite (Slaad Form Only)",
                                    "desc": "{@atk mw} {@hit 9} to hit, reach 5 ft., one target. {@h}9 ({@damage 1d8 + 5}) piercing damage plus 7 ({@damage 2d6}) necrotic damage.",
                                },
                                {
                                    "name": "Claws (Slaad Form Only)",
                                    "desc": "{@atk mw} {@hit 9} to hit, reach 5 ft., one target. {@h}10 ({@damage 1d10 + 5}) slashing damage plus 7 ({@damage 2d6}) necrotic damage.",
                                },
                                {
                                    "name": "Greatsword",
                                    "desc": "{@atk mw} {@hit 9} to hit, reach 5 ft., one target. {@h}12 ({@damage 2d6 + 5}) slashing damage plus 7 ({@damage 2d6}) necrotic damage.",
                                },
                            ]
                        }
                    },
                )()
            },
        )()

        options, counts = self.app._monster_attack_options_for_map(attacker)

        by_name = {str(entry.get("name")): entry for entry in options}
        self.assertIn("Bite (Slaad Form Only)", by_name)
        self.assertIn("Claws (Slaad Form Only)", by_name)
        self.assertIn("Greatsword", by_name)
        self.assertEqual(by_name["Bite (Slaad Form Only)"]["to_hit"], 9)
        self.assertEqual(
            by_name["Bite (Slaad Form Only)"]["damage_entries"],
            [{"formula": "1d8 + 5", "type": "piercing"}, {"formula": "2d6", "type": "necrotic"}],
        )
        self.assertEqual(counts.get("__total__"), 3)
        self.assertEqual(counts.get("bite"), 1)
        self.assertEqual(counts.get("claws"), 2)
        self.assertEqual(counts.get("greatsword"), 2)

    def test_monster_multiattack_description_for_map_returns_desc(self):
        attacker = type(
            "Combatant",
            (),
            {
                "monster_spec": type(
                    "Spec",
                    (),
                    {"raw_data": {"actions": [{"name": "Multiattack", "desc": "The dragon makes three attacks."}]}},
                )()
            },
        )()

        self.assertEqual(self.app._monster_multiattack_description_for_map(attacker), "The dragon makes three attacks.")

    def test_monster_attack_options_hydrate_from_persistent_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = f"{tmpdir}/logs"
            with mock.patch.dict("os.environ", {"INITTRACKER_DATA_DIR": tmpdir}, clear=False):
                os.makedirs(cache_dir, exist_ok=True)
                cache_path = f"{cache_dir}/monster_action_fallback_cache.json"
                payload = {
                    "version": 1,
                    "entries": {
                        "lizardfolk-sovereign": {
                            "name": "Lizardfolk Sovereign",
                            "sections": {
                                "actions": [
                                    {
                                        "name": "Trident",
                                        "desc": "Melee Attack Roll: +6, reach 5 ft. Hit: 8 (1d8 + 4) piercing damage.",
                                    }
                                ]
                            },
                            "updated_at": "2026-01-01T00:00:00Z",
                        }
                    },
                }
                with open(cache_path, "w", encoding="utf-8") as fh:
                    json.dump(payload, fh)

                attacker = type(
                    "Combatant",
                    (),
                    {
                        "monster_spec": type(
                            "Spec",
                            (),
                            {
                                "name": "Lizardfolk Sovereign",
                                "filename": "lizardfolk-sovereign.yaml",
                                "raw_data": {"name": "Lizardfolk Sovereign", "actions": []},
                            },
                        )()
                    },
                )()

                options, _counts = self.app._monster_attack_options_for_map(attacker)

        self.assertGreaterEqual(len(options), 1)
        self.assertEqual(options[0]["to_hit"], 6)
        self.assertEqual(options[0]["damage_entries"], [{"formula": "1d8 + 4", "type": "piercing"}])
        self.assertTrue(attacker.monster_spec.raw_data["actions"])

    def test_monster_attack_options_hydrate_from_local_5etools_and_write_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = f"{tmpdir}/monster_sources/5etools"
            with mock.patch.dict("os.environ", {"INITTRACKER_DATA_DIR": tmpdir}, clear=False):
                os.makedirs(source_dir, exist_ok=True)
                fixture_path = f"{source_dir}/bestiary.json"
                fixture = {
                    "monster": [
                        {
                            "name": "Lizardfolk Sovereign",
                            "action": [
                                {
                                    "name": "Mace",
                                    "entries": ["Melee Attack Roll: +5, reach 5 ft. Hit: 7 (1d6 + 4) bludgeoning damage."],
                                }
                            ],
                        }
                    ]
                }
                with open(fixture_path, "w", encoding="utf-8") as fh:
                    json.dump(fixture, fh)

                attacker = type(
                    "Combatant",
                    (),
                    {
                        "monster_spec": type(
                            "Spec",
                            (),
                            {
                                "name": "Lizardfolk Sovereign",
                                "filename": "lizardfolk-sovereign.yaml",
                                "raw_data": {"name": "Lizardfolk Sovereign", "actions": []},
                            },
                        )()
                    },
                )()

                options, _counts = self.app._monster_attack_options_for_map(attacker)
                cache_path = f"{tmpdir}/logs/monster_action_fallback_cache.json"
                with open(cache_path, "r", encoding="utf-8") as fh:
                    cached_payload = json.load(fh)
                source_dir_exists = os.path.isdir(f"{tmpdir}/monster_sources/5etools")

        self.assertGreaterEqual(len(options), 1)
        self.assertEqual(options[0]["to_hit"], 5)
        sections = cached_payload.get("entries", {}).get("lizardfolk-sovereign", {}).get("sections", {})
        self.assertTrue(isinstance(sections.get("actions"), list) and sections.get("actions"))
        self.assertTrue(source_dir_exists)


    def test_monster_attack_options_hydrate_online_by_default_and_write_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict("os.environ", {"INITTRACKER_DATA_DIR": tmpdir}, clear=False):
                attacker = type(
                    "Combatant",
                    (),
                    {
                        "monster_spec": type(
                            "Spec",
                            (),
                            {
                                "name": "Lizardfolk Sovereign",
                                "filename": "lizardfolk-sovereign.yaml",
                                "raw_data": {"name": "Lizardfolk Sovereign", "actions": []},
                            },
                        )()
                    },
                )()
                with mock.patch.object(self.app, "_download_default_5etools_packs", return_value=False), mock.patch(
                    "dnd_initative_tracker._load_backfill_helpers_module",
                    return_value=type(
                        "Helpers",
                        (),
                        {
                            "build_5etools_lookup": staticmethod(lambda _payload: {}),
                            "extract_sections_from_5etools_monster": staticmethod(lambda _monster: {}),
                            "_fetch_aidedd_html": staticmethod(lambda slug, timeout=15.0: f"html:{slug}:{timeout}"),
                            "extract_sections_from_aidedd_html": staticmethod(
                                lambda _html: {
                                    "actions": [
                                        {
                                            "name": "Trident",
                                            "desc": "Melee Attack Roll: +6, reach 5 ft. Hit: 8 (1d8 + 4) piercing damage.",
                                        }
                                    ]
                                }
                            ),
                        },
                    )(),
                ):
                    options, _counts = self.app._monster_attack_options_for_map(attacker)

                cache_path = f"{tmpdir}/logs/monster_action_fallback_cache.json"
                with open(cache_path, "r", encoding="utf-8") as fh:
                    cached_payload = json.load(fh)

        self.assertGreaterEqual(len(options), 1)
        self.assertEqual(options[0]["to_hit"], 6)
        sections = cached_payload.get("entries", {}).get("lizardfolk-sovereign", {}).get("sections", {})
        self.assertTrue(isinstance(sections.get("actions"), list) and sections.get("actions"))

    def test_monster_attack_options_rejects_metadata_only_online_sections(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict("os.environ", {"INITTRACKER_DATA_DIR": tmpdir}, clear=False):
                attacker = type(
                    "Combatant",
                    (),
                    {
                        "monster_spec": type(
                            "Spec",
                            (),
                            {
                                "name": "Lizardfolk Sovereign",
                                "filename": "lizardfolk-sovereign.yaml",
                                "raw_data": {"name": "Lizardfolk Sovereign", "actions": []},
                            },
                        )()
                    },
                )()
                with mock.patch.object(self.app, "_download_default_5etools_packs", return_value=False), mock.patch(
                    "dnd_initative_tracker._load_backfill_helpers_module",
                    return_value=type(
                        "Helpers",
                        (),
                        {
                            "build_5etools_lookup": staticmethod(lambda _payload: {}),
                            "extract_sections_from_5etools_monster": staticmethod(lambda _monster: {}),
                            "_fetch_aidedd_html": staticmethod(lambda slug, timeout=15.0: f"html:{slug}:{timeout}"),
                            "extract_sections_from_aidedd_html": staticmethod(
                                lambda _html: {
                                    "actions": [
                                        {"name": "Habitat", "desc": "Swamp"},
                                        {"name": "Treasure", "desc": "Standard"},
                                    ]
                                }
                            ),
                        },
                    )(),
                ):
                    options, counts = self.app._monster_attack_options_for_map(attacker)

                cache_path = f"{tmpdir}/logs/monster_action_fallback_cache.json"

        self.assertEqual(options, [])
        self.assertEqual(counts, {})
        self.assertFalse(os.path.exists(cache_path))

    def test_monster_attack_options_ignores_bad_cache_and_rehydrates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = f"{tmpdir}/logs"
            with mock.patch.dict("os.environ", {"INITTRACKER_DATA_DIR": tmpdir}, clear=False):
                os.makedirs(cache_dir, exist_ok=True)
                cache_path = f"{cache_dir}/monster_action_fallback_cache.json"
                payload = {
                    "version": 1,
                    "entries": {
                        "lizardfolk-sovereign": {
                            "name": "Lizardfolk Sovereign",
                            "sections": {
                                "actions": [
                                    {"name": "Habitat", "desc": "Swamp"},
                                    {"name": "Treasure", "desc": "Standard"},
                                ]
                            },
                            "updated_at": "2026-01-01T00:00:00Z",
                        }
                    },
                }
                with open(cache_path, "w", encoding="utf-8") as fh:
                    json.dump(payload, fh)

                attacker = type(
                    "Combatant",
                    (),
                    {
                        "monster_spec": type(
                            "Spec",
                            (),
                            {
                                "name": "Lizardfolk Sovereign",
                                "filename": "lizardfolk-sovereign.yaml",
                                "raw_data": {"name": "Lizardfolk Sovereign", "actions": []},
                            },
                        )()
                    },
                )()
                with mock.patch(
                    "dnd_initative_tracker._load_backfill_helpers_module",
                    return_value=type(
                        "Helpers",
                        (),
                        {
                            "build_5etools_lookup": staticmethod(lambda _payload: {}),
                            "extract_sections_from_5etools_monster": staticmethod(lambda _monster: {}),
                            "_fetch_aidedd_html": staticmethod(lambda slug, timeout=15.0: f"html:{slug}:{timeout}"),
                            "extract_sections_from_aidedd_html": staticmethod(
                                lambda _html: {
                                    "actions": [
                                        {
                                            "name": "Trident",
                                            "desc": "Melee Attack Roll: +6, reach 5 ft. Hit: 8 (1d8 + 4) piercing damage.",
                                        }
                                    ]
                                }
                            ),
                        },
                    )(),
                ):
                    options, counts = self.app._monster_attack_options_for_map(attacker)

                with open(cache_path, "r", encoding="utf-8") as fh:
                    cached_payload = json.load(fh)

        self.assertGreaterEqual(len(options), 1)
        self.assertEqual(options[0]["to_hit"], 6)
        sections = cached_payload.get("entries", {}).get("lizardfolk-sovereign", {}).get("sections", {})
        self.assertEqual(sections.get("actions", [])[0].get("name"), "Trident")

    def test_monster_attack_options_online_failure_falls_back_cleanly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict("os.environ", {"INITTRACKER_DATA_DIR": tmpdir}, clear=False):
                attacker = type(
                    "Combatant",
                    (),
                    {
                        "monster_spec": type(
                            "Spec",
                            (),
                            {
                                "name": "Lizardfolk Sovereign",
                                "filename": "lizardfolk-sovereign.yaml",
                                "raw_data": {"name": "Lizardfolk Sovereign", "actions": []},
                            },
                        )()
                    },
                )()
                with mock.patch(
                    "dnd_initative_tracker._load_backfill_helpers_module",
                    return_value=type(
                        "Helpers",
                        (),
                        {
                            "build_5etools_lookup": staticmethod(lambda _payload: {}),
                            "extract_sections_from_5etools_monster": staticmethod(lambda _monster: {}),
                            "_fetch_aidedd_html": staticmethod(
                                lambda _slug, timeout=15.0: (_ for _ in ()).throw(TimeoutError("timed out"))
                            ),
                            "extract_sections_from_aidedd_html": staticmethod(lambda _html: {}),
                        },
                    )(),
                ):
                    options, counts = self.app._monster_attack_options_for_map(attacker)
                source_dir_exists = os.path.isdir(f"{tmpdir}/monster_sources/5etools")

        self.assertEqual(options, [])
        self.assertEqual(counts, {})
        self.assertTrue(source_dir_exists)

    def test_monster_attack_options_online_opt_out_disables_fetch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(
                "os.environ",
                {"INITTRACKER_DATA_DIR": tmpdir, "INITTRACKER_DISABLE_MONSTER_ACTION_ONLINE": "true"},
                clear=False,
            ):
                attacker = type(
                    "Combatant",
                    (),
                    {
                        "monster_spec": type(
                            "Spec",
                            (),
                            {
                                "name": "Lizardfolk Sovereign",
                                "filename": "lizardfolk-sovereign.yaml",
                                "raw_data": {"name": "Lizardfolk Sovereign", "actions": []},
                            },
                        )()
                    },
                )()
                fetch_mock = mock.Mock(return_value="html")
                with mock.patch(
                    "dnd_initative_tracker._load_backfill_helpers_module",
                    return_value=type(
                        "Helpers",
                        (),
                        {
                            "build_5etools_lookup": staticmethod(lambda _payload: {}),
                            "extract_sections_from_5etools_monster": staticmethod(lambda _monster: {}),
                            "_fetch_aidedd_html": staticmethod(fetch_mock),
                            "extract_sections_from_aidedd_html": staticmethod(lambda _html: {}),
                        },
                    )(),
                ):
                    options, counts = self.app._monster_attack_options_for_map(attacker)

        self.assertEqual(options, [])
        self.assertEqual(counts, {})
        fetch_mock.assert_not_called()


    def test_monster_attack_options_bootstrap_downloads_5etools_and_writes_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict("os.environ", {"INITTRACKER_DATA_DIR": tmpdir}, clear=False), mock.patch(
                "dnd_initative_tracker.FALLBACK_5ETOOLS_MIN_BYTES", 1
            ):
                attacker = type(
                    "Combatant",
                    (),
                    {
                        "monster_spec": type(
                            "Spec",
                            (),
                            {
                                "name": "Lizardfolk Sovereign",
                                "filename": "lizardfolk-sovereign.yaml",
                                "raw_data": {"name": "Lizardfolk Sovereign", "actions": []},
                            },
                        )()
                    },
                )()

                pack_payload = json.dumps(
                    {
                        "monster": [
                            {
                                "name": "Lizardfolk Sovereign",
                                "action": [
                                    {"name": "Trident", "entries": ["Melee Attack Roll: +6, reach 5 ft. Hit: 8 (1d8 + 4) piercing damage."]}
                                ],
                            }
                        ]
                    }
                ).encode("utf-8")
                requested_urls = []

                def _mock_urlopen(request, timeout=0):
                    requested_urls.append(getattr(request, "full_url", ""))
                    return _MockHttpResponse(pack_payload)

                with mock.patch("dnd_initative_tracker.urllib.request.urlopen", side_effect=_mock_urlopen):
                    options, _counts = self.app._monster_attack_options_for_map(attacker)

                cache_path = f"{tmpdir}/logs/monster_action_fallback_cache.json"
                with open(cache_path, "r", encoding="utf-8") as fh:
                    cached_payload = json.load(fh)
                downloaded_exists = (
                    os.path.isfile(f"{tmpdir}/monster_sources/5etools/bestiary-xmm.json")
                    or os.path.isfile(f"{tmpdir}/monster_sources/5etools/bestiary-mm.json")
                )

        self.assertGreaterEqual(len(options), 1)
        self.assertEqual(options[0]["to_hit"], 6)
        self.assertGreaterEqual(len(requested_urls), 1)
        self.assertTrue(downloaded_exists)
        sections = cached_payload.get("entries", {}).get("lizardfolk-sovereign", {}).get("sections", {})
        self.assertTrue(isinstance(sections.get("actions"), list) and sections.get("actions"))

    def test_monster_attack_options_bootstrap_respects_online_disable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(
                "os.environ",
                {"INITTRACKER_DATA_DIR": tmpdir, "INITTRACKER_DISABLE_MONSTER_ACTION_ONLINE": "true"},
                clear=False,
            ):
                attacker = type(
                    "Combatant",
                    (),
                    {
                        "monster_spec": type(
                            "Spec",
                            (),
                            {
                                "name": "Lizardfolk Sovereign",
                                "filename": "lizardfolk-sovereign.yaml",
                                "raw_data": {"name": "Lizardfolk Sovereign", "actions": []},
                            },
                        )()
                    },
                )()

                with mock.patch("dnd_initative_tracker.urllib.request.urlopen") as urlopen_mock:
                    options, counts = self.app._monster_attack_options_for_map(attacker)

        self.assertEqual(options, [])
        self.assertEqual(counts, {})
        urlopen_mock.assert_not_called()

    def test_apply_hydrated_sections_replaces_non_parseable_actions_only(self):
        raw_data = {
            "traits": [{"name": "Existing Trait", "desc": "Keep me."}],
            "actions": [{"name": "Mace", "desc": "Weapon attack with no numbers."}],
        }
        hydrated = {
            "traits": [{"name": "Hydrated Trait", "desc": "Should not overwrite existing trait."}],
            "actions": [{"name": "Trident", "desc": "Melee Attack Roll: +6, reach 5 ft. Hit: 8 (1d8 + 4) piercing damage."}],
        }

        changed = self.app._apply_hydrated_monster_sections(raw_data, hydrated)

        self.assertTrue(changed)
        self.assertEqual(raw_data["traits"][0]["name"], "Existing Trait")
        self.assertEqual(raw_data["actions"][0]["name"], "Trident")

    def test_resolve_map_attack_rolls_to_hit_and_reports_manual_damage_rolls(self):
        attacker = type("Combatant", (), {"cid": 1, "name": "Death Slaad"})()
        target = type("Combatant", (), {"cid": 2, "name": "Knight", "ac": 15, "hp": 30})()
        self.app.combatants = {1: attacker, 2: target}

        attack_option = {
            "name": "Claws",
            "to_hit": 9,
            "damage_entries": [
                {"formula": "1d10 + 5", "type": "slashing"},
                {"formula": "2d6", "type": "necrotic"},
            ],
        }

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[12, 4]):
            result = self.app._resolve_map_attack(1, 2, attack_option, attack_count=2)

        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("hits"), 1)
        self.assertEqual(result.get("misses"), 1)
        self.assertEqual(result.get("total_damage"), 0)
        self.assertEqual(self.app.combatants[2].hp, 30)
        self.assertEqual(
            result.get("damage_rolls"),
            [
                {"formula": "1d10 + 5", "type": "slashing", "count": 1},
                {"formula": "2d6", "type": "necrotic", "count": 1},
            ],
        )
        self.assertEqual(result.get("damage_types"), ["slashing", "necrotic"])
        self.assertTrue(any("roll damage manually" in message for _cid, message in self.logs))

    def test_apply_map_attack_manual_damage_updates_hp_and_logs_components(self):
        attacker = type("Combatant", (), {"cid": 1, "name": "Death Slaad"})()
        target = type("Combatant", (), {"cid": 2, "name": "Knight", "ac": 15, "hp": 30})()
        self.app.combatants = {1: attacker, 2: target}

        result = self.app._apply_map_attack_manual_damage(
            1,
            2,
            "Claws",
            [
                {"amount": 9, "type": "slashing"},
                {"amount": 5, "type": "necrotic"},
            ],
        )

        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("total_damage"), 14)
        self.assertEqual(self.app.combatants[2].hp, 16)
        self.assertTrue(any("applies 14 damage" in message for _cid, message in self.logs))

    def test_apply_map_attack_manual_damage_accepts_simple_addition_expressions(self):
        attacker = type("Combatant", (), {"cid": 1, "name": "Death Slaad"})()
        target = type("Combatant", (), {"cid": 2, "name": "Knight", "ac": 15, "hp": 30})()
        self.app.combatants = {1: attacker, 2: target}

        parsed_entries = []
        amount_inputs = {"slashing": "2+3", "necrotic": "4+1"}
        for dtype, raw in amount_inputs.items():
            evaluated = self.app._evaluate_spell_formula(raw, {})
            amount = int(evaluated) if evaluated is not None else 0
            if amount > 0:
                parsed_entries.append({"amount": amount, "type": dtype})

        result = self.app._apply_map_attack_manual_damage(1, 2, "Claws", parsed_entries)

        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("total_damage"), 10)
        self.assertEqual(self.app.combatants[2].hp, 20)

    def test_apply_map_attack_manual_damage_applies_resistance_and_immunity(self):
        attacker = type("Combatant", (), {"cid": 1, "name": "Death Slaad"})()
        target = type("Combatant", (), {"cid": 2, "name": "Knight", "ac": 15, "hp": 30})()
        target.monster_spec = type(
            "Spec",
            (),
            {"raw_data": {"damage_resistances": ["necrotic"], "damage_immunities": ["poison"]}},
        )()
        self.app.combatants = {1: attacker, 2: target}

        result = self.app._apply_map_attack_manual_damage(
            1,
            2,
            "Claws",
            [
                {"amount": 10, "type": "slashing"},
                {"amount": 10, "type": "necrotic"},
                {"amount": 10, "type": "poison"},
            ],
        )

        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("total_damage"), 15)
        self.assertEqual(self.app.combatants[2].hp, 15)


    def test_enemy_map_attack_logs_hide_hidden_roll_details(self):
        attacker = type("Combatant", (), {"cid": 1, "name": "Death Slaad"})()
        target = type("Combatant", (), {"cid": 2, "name": "Knight", "ac": 15, "hp": 30})()
        self.app.combatants = {1: attacker, 2: target}
        self.app._name_role_memory = {"Death Slaad": "enemy", "Knight": "pc"}

        attack_option = {
            "name": "Claws",
            "to_hit": 9,
            "damage_entries": [
                {"formula": "1d10 + 5", "type": "slashing"},
                {"formula": "2d6", "type": "necrotic"},
            ],
        }

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[12, 4]):
            result = self.app._resolve_map_attack(1, 2, attack_option, attack_count=2)

        self.assertTrue(result.get("ok"))
        self.assertTrue(any("roll damage manually." in message for _cid, message in self.logs))
        self.assertFalse(any("1d10 + 5" in message for _cid, message in self.logs))
        self.assertFalse(any("vs AC" in message for _cid, message in self.logs))

    def test_enemy_manual_damage_logs_hide_damage_type_breakdown(self):
        attacker = type("Combatant", (), {"cid": 1, "name": "Death Slaad"})()
        target = type("Combatant", (), {"cid": 2, "name": "Knight", "ac": 15, "hp": 30})()
        self.app.combatants = {1: attacker, 2: target}
        self.app._name_role_memory = {"Death Slaad": "enemy", "Knight": "pc"}

        result = self.app._apply_map_attack_manual_damage(
            1,
            2,
            "Claws",
            [
                {"amount": 9, "type": "slashing"},
                {"amount": 5, "type": "necrotic"},
            ],
        )

        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("total_damage"), 14)
        self.assertTrue(any("applies 14 damage to Knight." in message for _cid, message in self.logs))
        self.assertFalse(any("slashing" in message or "necrotic" in message for _cid, message in self.logs))

    def test_resolve_map_attack_sequence_advantage_and_disadvantage_keep_correct_die(self):
        attacker = type("Combatant", (), {"cid": 1, "name": "Death Slaad"})()
        target = type("Combatant", (), {"cid": 2, "name": "Knight", "ac": 30, "hp": 30})()
        self.app.combatants = {1: attacker, 2: target}
        attack_option = {"name": "Claws", "key": "claws", "to_hit": 9, "damage_entries": [{"formula": "1d10 + 5", "type": "slashing"}]}

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[1, 20, 1, 20]):
            result = self.app._resolve_map_attack_sequence(
                1,
                2,
                [
                    {"attack_option": attack_option, "attack_key": "claws", "count": 1, "roll_mode": "advantage"},
                    {"attack_option": attack_option, "attack_key": "claws", "count": 1, "roll_mode": "disadvantage"},
                ],
            )

        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("hits"), 1)
        self.assertEqual(result.get("crit_hits"), 1)
        self.assertEqual(result.get("misses"), 1)
        blocks = result.get("sequence_blocks") or []
        self.assertEqual(blocks[0].get("crit_hits"), 1)
        self.assertEqual(blocks[1].get("misses"), 1)
        self.assertTrue(any("advantage, kept 20" in message for _cid, message in self.logs))
        self.assertTrue(any("disadvantage, kept 1" in message for _cid, message in self.logs))

    def test_resolve_map_attack_sequence_keeps_block_order_and_aggregates_damage_templates(self):
        attacker = type("Combatant", (), {"cid": 1, "name": "Death Slaad"})()
        target = type("Combatant", (), {"cid": 2, "name": "Knight", "ac": 15, "hp": 30})()
        self.app.combatants = {1: attacker, 2: target}
        bite = {"name": "Bite", "key": "bite", "to_hit": 9, "damage_entries": [{"formula": "1d8 + 5", "type": "piercing"}]}
        claws = {"name": "Claws", "key": "claws", "to_hit": 9, "damage_entries": [{"formula": "1d10 + 5", "type": "slashing"}]}

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[10, 6, 1]):
            result = self.app._resolve_map_attack_sequence(
                1,
                2,
                [
                    {"attack_option": bite, "attack_key": "bite", "count": 1, "roll_mode": "normal"},
                    {"attack_option": claws, "attack_key": "claws", "count": 2, "roll_mode": "normal"},
                ],
            )

        self.assertTrue(result.get("ok"))
        blocks = result.get("sequence_blocks") or []
        self.assertEqual([block.get("attack_name") for block in blocks], ["Bite", "Claws"])
        self.assertEqual(result.get("hits"), 2)
        self.assertEqual(result.get("misses"), 1)
        self.assertEqual(
            result.get("damage_rolls"),
            [
                {"formula": "1d8 + 5", "type": "piercing", "count": 1},
                {"formula": "1d10 + 5", "type": "slashing", "count": 1},
            ],
        )

    def test_resolve_map_attack_sequence_splits_blobbed_damage_types(self):
        attacker = type("Combatant", (), {"cid": 1, "name": "Death Slaad"})()
        target = type("Combatant", (), {"cid": 2, "name": "Knight", "ac": 15, "hp": 30})()
        self.app.combatants = {1: attacker, 2: target}
        attack_option = {
            "name": "Elemental Claws",
            "key": "elemental-claws",
            "to_hit": 9,
            "damage_entries": [{"formula": "2d6 + 5", "type": "slashing and fire damage"}],
        }

        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[10]):
            result = self.app._resolve_map_attack_sequence(
                1,
                2,
                [{"attack_option": attack_option, "attack_key": "elemental-claws", "count": 1, "roll_mode": "normal"}],
            )

        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("attack_name"), "Elemental Claws")
        self.assertCountEqual(
            result.get("damage_rolls"),
            [
                {"formula": "2d6 + 5", "type": "slashing", "count": 1},
                {"formula": "2d6 + 5", "type": "fire", "count": 1},
            ],
        )
        self.assertCountEqual(result.get("damage_types"), ["slashing", "fire"])

    def test_resolve_map_attack_sequence_stops_when_target_removed_mid_sequence(self):
        attacker = type("Combatant", (), {"cid": 1, "name": "Death Slaad"})()
        target = type("Combatant", (), {"cid": 2, "name": "Knight", "ac": 15, "hp": 30})()
        self.app.combatants = {1: attacker, 2: target}
        attack_option = {"name": "Claws", "key": "claws", "to_hit": 9, "damage_entries": [{"formula": "1d10 + 5", "type": "slashing"}]}

        def pop_target_on_first_attack(message, cid=None):
            self.logs.append((cid, message))
            if "attack 1/1" in message and 2 in self.app.combatants:
                self.app.combatants.pop(2, None)

        self.app._log = pop_target_on_first_attack
        with mock.patch("dnd_initative_tracker.random.randint", side_effect=[10]):
            result = self.app._resolve_map_attack_sequence(
                1,
                2,
                [
                    {"attack_option": attack_option, "attack_key": "claws", "count": 1, "roll_mode": "normal"},
                    {"attack_option": attack_option, "attack_key": "claws", "count": 2, "roll_mode": "normal"},
                ],
            )

        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("target_removed"))
        self.assertEqual(len(result.get("sequence_blocks") or []), 1)


if __name__ == "__main__":
    unittest.main()
