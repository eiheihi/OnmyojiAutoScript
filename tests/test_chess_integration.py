"""Offline checks for the dev Chess port on the existing OAS runtime."""

import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from module.atom.image import RuleImage
from module.config.config_menu import ConfigMenu
from module.config.config_model import ConfigModel
from module.exception import TaskEnd
from tasks.Chess.assets import ChessAssets
from tasks.Chess.config import Chess
from tasks.Chess.runtime.press_and_drag import Press_and_Drag
from tasks.Chess.script_task import ScriptTask
from tasks.Chess.strategy.lineup import LINEUP_REGISTRY
from tasks.GameUi.assets import GameUiAssets
from tasks.GameUi.page import page_chess, page_chess_battle, page_main, page_touch_fish
from tasks.GameUi.registry import PageRegistry
from tasks.GameUi.session import NavigatorSession
from tasks.GlobalGame.assets import GlobalGameAssets


class ChessIntegrationTests(unittest.TestCase):
    def task(self):
        return ScriptTask.__new__(ScriptTask)

    def test_old_config_gets_disabled_chess_defaults(self):
        old_data = json.loads(Path('config/template.json').read_text(encoding='utf-8'))
        old_data.pop('chess')
        with patch.object(ConfigModel, 'read_json', return_value=old_data):
            model = ConfigModel('offline-test')
        self.assertFalse(model.chess.scheduler.enable)
        self.assertEqual(model.chess.chess_config.run_count, 1)
        self.assertEqual(model.chess.chess_config.lineup_bond.value, '荒川')
        args = model.script_task('Chess')['chess_config']
        lineup = next(arg for arg in args if arg['name'] == 'lineup_bond')
        self.assertEqual(set(lineup['enumEnum']), {v['display_name'] for v in LINEUP_REGISTRY.values()})
        self.assertIn('Chess', ConfigMenu().menu['Weekly Task'])

    def test_navigation_reaches_chess_and_preserves_other_pages(self):
        task = self.task()
        task.navigator = NavigatorSession(task_category='Chess')
        task.navigator.bootstrap(PageRegistry.all())
        path = task._build_path(page_main, page_chess)
        self.assertEqual([edge.destination.key for edge in path],
                         ['page_town', 'page_entertainment', 'page_chess'])
        self.assertIsNotNone(task._build_path(page_chess, page_main))
        recovery = task._build_path(page_chess_battle, page_main)
        self.assertEqual(recovery[0].destination.key, 'page_chess')
        self.assertIsNotNone(PageRegistry.get(page_touch_fish.key))

    def test_all_static_image_rules_have_readable_resources(self):
        for cls in (ChessAssets, GameUiAssets):
            for name, rule in vars(cls).items():
                if isinstance(rule, RuleImage):
                    with self.subTest(asset=name):
                        self.assertTrue(Path(rule.file).is_file(), rule.file)
                        self.assertGreater(rule.image.size, 0)

    def test_dynamic_templates_load_on_current_rule_image(self):
        task = self.task()
        for key in LINEUP_REGISTRY:
            task.select_lineup_strategy(key)
            for group in (task.lineup_shikigami_hand_rules, task.shikigami_shop_rules):
                self.assertTrue(group)
                for _, rule in group:
                    self.assertTrue(rule.is_template_match)
                    self.assertGreater(rule.image.size, 0)
        for group in (task.shikigami_hand_rules, task.soul_hand_rules, task.all_shikigami_shop_rules):
            self.assertTrue(group)
            for _, rule in group:
                self.assertGreater(rule.image.size, 0)
        self.assertGreater(task.hakuzosu_protect_rule.image.size, 0)

    def test_classification_uses_real_matcher_without_frame_id(self):
        task = self.task()
        rule = task.shikigami_hand_rules[0][1]
        image = np.zeros((720, 1280, 3), dtype=np.uint8)
        height, width = rule.image.shape[:2]
        image[550:550 + height, 200:200 + width] = rule.image
        task.device = SimpleNamespace(image=image)
        task.shikigami_hand_rules = [('sample', rule)]
        task.soul_hand_rules = []
        result = task.classify_hand_card((190, 540, width + 30, height + 20))
        self.assertEqual(result['name'], 'sample')
        self.assertGreater(result['score'], 0.99)

    def test_board_occupancy_uses_current_matcher(self):
        task = self.task()
        task.device = SimpleNamespace(image=np.zeros((720, 1280, 3), dtype=np.uint8))
        task._is_boss_challenge_round = lambda: False
        x, y, _, _ = task._set_jade_area(1)
        rule = task.board_occupancy_rules[0]
        height, width = rule.image.shape[:2]
        task.device.image[y:y + height, x:x + width] = rule.image
        self.assertTrue(task._board_set_has_shikigami(1))

    def test_all_hand_templates_can_be_compared_in_83_by_117_card_roi(self):
        task = self.task()
        rule = dict(task.shikigami_hand_rules)['ashura']
        image = np.zeros((720, 1280, 3), dtype=np.uint8)
        height, width = rule.image.shape[:2]
        self.assertEqual((width, height), (83, 117))
        image[573:573 + height, 563:563 + width] = rule.image
        task.device = SimpleNamespace(image=image)
        # Keep the full template list: snow maiden is 84x116, so only its
        # width exceeds this ROI. The earlier matching Ashura must survive.
        result = task.classify_hand_card((563, 573, 83, 117))
        self.assertEqual(result['name'], 'ashura')
        self.assertGreater(result['score'], 0.99)

    def test_multi_match_rejects_oversized_and_empty_search_regions(self):
        task = self.task()
        rule = dict(task.shikigami_hand_rules)['yuki_onna']
        image = np.zeros((720, 1280, 3), dtype=np.uint8)
        height, width = rule.image.shape[:2]
        for method in (rule.match_all, rule.match_all_any):
            for roi in ([563, 573, width - 1, height + 1],
                        [0, 0, width + 1, height - 1],
                        [0, 0, width - 1, height - 1], [0, 0, 0, 0],
                        [1279, 719, width, height]):
                with self.subTest(method=method.__name__, roi=roi):
                    rule.last_score = 0.95
                    self.assertEqual(method(image, roi=roi), [])
                    self.assertEqual(rule.last_score, -1.0)

    def test_drag_supports_current_device_without_cache_or_timing_helpers(self):
        device = SimpleNamespace(
            config=SimpleNamespace(script=SimpleNamespace(
                device=SimpleNamespace(control_method='ADB'))),
            handle_control_check=Mock(), swipe_adb=Mock(),
        )
        Press_and_Drag(device, (200, 600), (400, 300))
        device.swipe_adb.assert_called_once()

    def run_task(self, **settings):
        task = self.task()
        config = Chess(chess_config=settings)
        task.config = SimpleNamespace(chess=config)
        task.start_time = datetime.now()
        task._recover_interrupted_chess_game = Mock()
        task.goto_page = Mock()
        task.screenshot = Mock()
        task._coin_is_full = Mock(return_value=False)
        task.run_one_game = Mock(return_value=5)
        task.set_next_run = Mock()
        return task

    def test_run_stops_at_game_count_and_marks_task_finished(self):
        task = self.run_task(run_count=2)
        with self.assertRaises(TaskEnd):
            task.run()
        self.assertEqual(task.run_one_game.call_count, 2)
        task.set_next_run.assert_called_once_with(task='Chess', success=True, finish=True)

    def test_full_coin_stops_before_next_game(self):
        task = self.run_task(run_count=-1, coin_full_exit=True)
        task._coin_is_full.return_value = True
        with self.assertRaises(TaskEnd):
            task.run()
        task.run_one_game.assert_not_called()

    def test_time_limit_prevents_new_game(self):
        task = self.run_task(run_count=-1)
        task.start_time -= timedelta(hours=1)
        with self.assertRaises(TaskEnd):
            task.run()
        task.run_one_game.assert_not_called()

    def test_exit_accepts_new_global_and_legacy_confirmation_buttons(self):
        for confirm, cancel in (
            (GlobalGameAssets.I_UI_CONFIRM, GlobalGameAssets.I_UI_CANCEL),
            (GlobalGameAssets.I_UI_CONFIRM_OLD, GlobalGameAssets.I_UI_CANCEL_OLD),
            (GameUiAssets.I_CHESS_EXIT_CONFIRM, GameUiAssets.I_CHESS_EXIT_CANCEL),
        ):
            with self.subTest(confirm=confirm.file):
                task = self.task()
                task.device = SimpleNamespace(stuck_record_clear=Mock())
                state = {'frame': 0}
                task.screenshot = lambda: state.update(frame=state['frame'] + 1)

                def appear(rule):
                    # After clicking confirm, a frame may still show cancel.
                    # Do not start the result flow until the whole dialog closes.
                    if state['frame'] == 1:
                        return rule is confirm or rule is cancel
                    if state['frame'] == 2:
                        return rule is cancel
                    if state['frame'] > 3:
                        self.fail('Exit did not advance after the dialog closed')
                    return False

                task.appear = appear
                task.click = Mock()
                task.return_to_chess_lobby = Mock(return_value=True)
                with patch('tasks.GameUi.chess_battle.time.sleep'):
                    self.assertTrue(task.exit_chess_battle())
                task.click.assert_called_once_with(confirm)
                self.assertEqual(state['frame'], 3)
                task.return_to_chess_lobby.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
