"""Offline compatibility checks; no emulator or account configuration is changed."""

import json
import unittest
from datetime import datetime, time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from module.atom.image import RuleImage
from module.config.config_model import ConfigModel
from module.exception import RequestHumanTakeover
from module.ocr.base_ocr import OcrMethod
from tasks.AbyssShadows.assets import AbyssShadowsAssets
from tasks.AbyssShadows.config import AbyssShadows, Code, CodeList, EnemyType
from tasks.AbyssShadows.page import page_abyss, page_abyss_map
from tasks.AbyssShadows.script_task import ScriptTask
from tasks.GameUi.page import page_main, page_shikigami_records
from tasks.GameUi.registry import PageRegistry
from tasks.GameUi.session import NavigatorSession


class AbyssShadowsIntegrationTests(unittest.TestCase):
    def task(self, config=None):
        task = ScriptTask.__new__(ScriptTask)
        task.config = SimpleNamespace(model=SimpleNamespace(abyss_shadows=config or AbyssShadows()))
        task.device = Mock()
        return task

    def test_old_configuration_preserves_schedule_soul_and_combat(self):
        legacy = {
            'abyss_shadows_time': {'custom_run_time_friday': '19:15:00',
                                  'custom_run_time_saturday': '19:30:00',
                                  'custom_run_time_sunday': '19:45:00'},
            'abyss_shadows_combat_time': {'CombatTime_enable': True,
                                         'boss_combat_time': 75, 'general_combat_time': 45,
                                         'elite_combat_time': 30},
            'switch_soul_config': {'enable': True, 'switch_group_team': '2,3',
                                   'enable_switch_by_name': True, 'group_name': 'group'},
        }
        cfg = AbyssShadows(**legacy)
        self.assertEqual([cfg.abyss_shadows_time.abyss_shadows_4,
                          cfg.abyss_shadows_time.abyss_shadows_5,
                          cfg.abyss_shadows_time.abyss_shadows_6],
                         [time(19, 15), time(19, 30), time(19, 45)])
        self.assertEqual(cfg.process_manage.strategy_boss, '75')
        self.assertEqual(cfg.process_manage.strategy_general, '45')
        self.assertEqual(cfg.process_manage.strategy_elite, '30')
        self.assertTrue(cfg.process_manage.try_complete_enemy_count)
        self.assertEqual(len(CodeList(cfg.process_manage.attack_order)), 12)
        self.assertEqual(cfg.switch_soul_config.switch_group_team, '2,3')
        self.assertTrue(cfg.switch_soul_config.enable_switch_by_name)
        restored = AbyssShadows(**cfg.model_dump())
        self.assertEqual(restored, cfg)
        legacy['abyss_shadows_combat_time']['CombatTime_enable'] = False
        cfg = AbyssShadows(**legacy)
        for enemy in EnemyType:
            self.assertFalse(cfg.process_manage.generate_quit_condition(enemy).is_valid(999999999))

    def test_new_fields_take_precedence_over_legacy_fields(self):
        cfg = AbyssShadows(abyss_shadows_time={'abyss_shadows_4': '21:00:00',
                                             'custom_run_time_friday': '19:00:00'},
                           process_manage={'strategy_boss': 'TRUE'},
                           abyss_shadows_combat_time={'CombatTime_enable': True})
        self.assertEqual(cfg.abyss_shadows_time.abyss_shadows_4, time(21))
        self.assertTrue(cfg.process_manage.generate_quit_condition(EnemyType.BOSS).is_valid())

    def test_template_and_settings_page_load_with_hidden_progress(self):
        old_data = json.loads(Path('config/template.json').read_text(encoding='utf-8'))
        with patch.object(ConfigModel, 'read_json', return_value=old_data):
            model = ConfigModel('offline-test')
        args = model.script_task('AbyssShadows')
        self.assertIn('process_manage', args)
        self.assertNotIn('saved_params', args)
        self.assertIn('switch_soul_config', args)
        self.assertEqual(len(model.abyss_shadows.model_json_schema()['properties']), 5)

    def test_navigation_paths_and_resources_on_main_runtime(self):
        PageRegistry.load_all_pages()
        task = self.task()
        task.navigator = NavigatorSession(task_category='AbyssShadows')
        task.navigator.bootstrap(PageRegistry.all())
        self.assertEqual([edge.destination.key for edge in task._build_path(page_main, page_abyss)],
                         ['page_guild', 'page_shirin', 'page_abyss'])
        self.assertIsNotNone(task._build_path(page_abyss_map, page_main))
        self.assertEqual(task._build_path(page_abyss_map, page_shikigami_records)[0].destination.key,
                         'page_shikigami_records')
        self.assertEqual(task._build_path(page_shikigami_records, page_abyss_map)[0].destination.key,
                         'page_abyss_map')
        for name, rule in vars(AbyssShadowsAssets).items():
            if isinstance(rule, RuleImage):
                with self.subTest(asset=name):
                    self.assertTrue(Path(rule.file).is_file())
                    self.assertGreater(rule.image.size, 0)

    def test_color_filters_preserve_dev_semantics_without_global_ocr_changes(self):
        gray = np.array([[[204, 204, 204], [100, 100, 100], [255, 255, 255]]], dtype=np.uint8)
        filtered = AbyssShadowsAssets.O_DRAGON_DONE.pre_process(gray)
        np.testing.assert_array_equal(filtered, [[[204, 204, 204], [0, 0, 0], [255, 255, 255]]])
        orange = np.array([[[255, 170, 85], [0, 0, 255]]], dtype=np.uint8)
        filtered = AbyssShadowsAssets.O_DAMAGE.pre_process(orange)
        np.testing.assert_array_equal(filtered, [[[255, 170, 85], [0, 0, 0]]])
        self.assertEqual(list(OcrMethod.__members__), ['DEFAULT'])

    def test_orders_resume_and_fill_missing_rewards(self):
        cfg = AbyssShadows(process_manage={'attack_order': 'A-1', 'try_complete_enemy_count': True})
        task = self.task(cfg)
        task.ps_list = CodeList('A-1')
        task.done_list = CodeList('A-1')
        task.unavailable_list = CodeList('A;B-1')
        self.assertEqual(task.get_next(), Code('B-2'))
        cfg.process_manage.try_complete_enemy_count = False
        self.assertIsNone(task.get_next())

    def test_scheduling_weekend_retry_and_next_friday(self):
        task = self.task()
        cases = [(datetime(2026, 10, 30, 19), False, datetime(2026, 10, 30, 20)),
                 (datetime(2026, 10, 30, 22), False, datetime(2026, 10, 31, 20)),
                 (datetime(2026, 11, 1, 20), True, datetime(2026, 11, 6, 20)),
                 (datetime(2026, 11, 2, 12), False, datetime(2026, 11, 6, 20))]
        for now, success, expected in cases:
            with self.subTest(now=now):
                self.assertEqual(task.get_next_dt(now, success), expected)
        now = datetime(2026, 10, 30, 20, 5)
        self.assertEqual(task.get_next_dt(now), now + task.config.model.abyss_shadows.scheduler.failure_interval)

    def test_preset_switches_again_after_other_enemy_type(self):
        task = self.task(AbyssShadows(process_manage={'enable_switch_preset_in_as': True,
                                                    'mark_main': 'NONE'}))
        task.cur_preset = None
        task.switch_preset_team_with_str = Mock()
        task.wait_until_appear = Mock()
        task.ui_click_until_disappear = Mock()
        task.screenshot = Mock()
        task.appear_then_click = Mock(return_value=False)
        task.appear = Mock(return_value=True)
        task.O_DAMAGE = Mock()
        task.O_DAMAGE.ocr_digit.return_value = 0
        for code in ('A-4', 'A-5', 'A-2', 'B-4'):
            task.run_battle(Code(code))
        self.assertEqual([call.args[0] for call in task.switch_preset_team_with_str.call_args_list],
                         ['6,3', '6,2', '6,3'])

    def test_empty_strategy_still_returns_a_condition(self):
        cfg = AbyssShadows(process_manage={'strategy_boss': ''})
        condition = cfg.process_manage.generate_quit_condition(EnemyType.BOSS)
        self.assertFalse(condition.is_valid())
        self.assertFalse(condition.is_need_damage_value())

    def test_start_uses_main_confirmation_and_bounds_failed_wait(self):
        task = self.task()
        task.wait_until_appear = Mock()
        task.appear = Mock(return_value=True)
        task.ui_click = Mock(return_value=True)
        task.ui_click_until_disappear = Mock()
        task.start_abyss_shadows()
        task.ui_click.assert_called_with(task.I_BTN_START, stop=task.I_UI_CONFIRM,
                                         interval=2, timeout=8)
        task.ui_click_until_disappear.assert_called_with(task.I_UI_CONFIRM, interval=2)
        task.ui_click.return_value = False
        task.ui_click_until_disappear.reset_mock()
        with self.assertRaises(RequestHumanTakeover):
            task.start_abyss_shadows()
        # Only difficulty selection was completed; no unrecognized confirmation is clicked.
        task.ui_click_until_disappear.assert_called_once_with(task.I_DIFFICULTY_EASY, interval=2)


if __name__ == '__main__':
    unittest.main()
