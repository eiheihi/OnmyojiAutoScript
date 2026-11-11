import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from module.exception import TaskEnd, GameStuckError
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.MetaDemon.config import DefaultStrategy, MetaDemon
from tasks.MetaDemon.script_task import ScriptTask


class MetaDemonStrategyTests(unittest.TestCase):
    def setUp(self):
        self.strategy = DefaultStrategy(
            md_preset_group_team_default_1='2,1',
            md_preset_group_team_tsukuyomi='2,2',
            md_preset_group_team_shuten='2,3',
            md_preset_group_team_kidomaru='2,4',
        )

    def test_high_star_special_names(self):
        for team, names in ((2, ('月读', '雪御前')),
                            (3, ('酒吞童子', '鬼王酒吞童子')),
                            (4, ('修罗鬼童丸', '鬼童丸'))):
            for name in names:
                with self.subTest(name=name):
                    self.assertEqual(self.strategy.get_group_team(name, True), [2, team])
                    self.assertEqual(self.strategy.get_group_team(name, False), [2, 1])

    def test_unknown_or_unrecognized_name_uses_default(self):
        for name in ('', None, '大天狗', '酒吞童于', '鬼王'):
            with self.subTest(name=name):
                self.assertEqual(self.strategy.get_group_team(name, True), [2, 1])

    def test_ocr_whitespace(self):
        self.assertEqual(self.strategy.get_group_team(' 修罗\n鬼童丸 ', True), [2, 4])

    def test_special_then_normal_switches_back(self):
        self.assertEqual(self.strategy.get_group_team('月读', True), [2, 2])
        self.assertEqual(self.strategy.get_group_team('月读', False), [2, 1])
        self.assertEqual(self.strategy.get_group_team('大天狗', True), [2, 1])

    def test_old_default_config_loads_and_exposes_four_teams(self):
        config = MetaDemon.model_validate({
            'meta_demon_config': {'md_use_strategy': True, 'md_strategy_count': 0},
            'md_default_strategy': {
                'md_preset_group_team_default_1': '3,2',
                'md_preset_group_team_default_2': '4,2',
            },
        })
        self.assertEqual(config.md_default_strategy.get_group_team(), [3, 2])
        self.assertEqual(len(config.model_dump()['md_default_strategy']), 4)
        self.assertEqual(MetaDemon.model_validate(config.model_dump()), config)


class MetaDemonSoulTests(unittest.TestCase):
    def setUp(self):
        self.config = MetaDemon()
        self.config.md_soul_default.enable = True
        self.config.md_soul_default.switch_group_team = '1,1'
        self.config.md_soul_tsukuyomi.enable = True
        self.config.md_soul_tsukuyomi.switch_group_team = '2,3'
        self.task = ScriptTask.__new__(ScriptTask)
        self.task.config = SimpleNamespace(meta_demon=self.config)
        self.task.ui_click = Mock()
        self.task.goto_page = Mock()
        self.task.enter_activity = Mock()
        self.task.return_from_records = Mock()
        self.task.run_switch_soul = Mock()
        self.task.run_switch_soul_by_name = Mock()

    def test_switch_special_then_restore_default_and_skip_repeats(self):
        self.assertTrue(self.task.switch_strategy_soul('default'))
        self.assertTrue(self.task.switch_strategy_soul('tsukuyomi'))
        self.assertFalse(self.task.switch_strategy_soul('tsukuyomi'))
        self.assertTrue(self.task.switch_strategy_soul('default'))
        self.assertEqual([c.args[0] for c in self.task.run_switch_soul.call_args_list],
                         [(1, 1), (2, 3), (1, 1)])
        self.assertEqual(self.task.return_from_records.call_count, 3)
        self.task.goto_page.assert_not_called()
        self.task.enter_activity.assert_not_called()
        self.assertIs(self.task.ui_click.call_args.args[0], self.task.C_MD_RECORDS)

    def test_name_switch_takes_precedence(self):
        soul = self.config.md_soul_tsukuyomi
        soul.enable_switch_by_name = True
        soul.group_name = ' group '
        soul.team_name = ' team '
        self.assertTrue(self.task.switch_strategy_soul('tsukuyomi'))
        self.task.run_switch_soul_by_name.assert_called_once_with('group', 'team')
        self.task.run_switch_soul.assert_not_called()

    def test_disabled_soul_stays_in_activity(self):
        self.assertFalse(self.task.switch_strategy_soul('shuten'))
        self.task.ui_click.assert_not_called()

    def test_invalid_soul_fails_before_leaving_activity(self):
        self.config.md_soul_tsukuyomi.switch_group_team = '1,5'
        with self.assertRaises(ValueError):
            self.task.switch_strategy_soul('tsukuyomi')
        self.task.ui_click.assert_not_called()

    def test_failed_switch_does_not_cache_success(self):
        self.task.run_switch_soul.side_effect = RuntimeError('switch failed')
        with self.assertRaises(RuntimeError):
            self.task.switch_strategy_soul('default')
        self.assertIsNone(getattr(self.task, '_active_strategy_soul', None))
        self.task.enter_activity.assert_not_called()
        self.task.return_from_records.assert_not_called()

    def test_return_from_switch_reidentifies_boss_before_battle(self):
        self.config.meta_demon_config.md_use_strategy = True
        self.config.md_default_strategy.md_preset_group_team_default_1 = '3,1'
        self.config.md_default_strategy.md_preset_group_team_tsukuyomi = '3,2'
        self.task.device = SimpleNamespace(image=None)
        self.task.screenshot = Mock()
        visible = (self.task.I_FIND_DEMON, self.task.I_BOSS_CONVENE, self.task.I_BATTLE_DEMON)
        self.task.appear = lambda rule: any(rule is item for item in visible)
        self.task.click = Mock()
        self.task.is_star56 = Mock(return_value=True)
        self.task.current_exhaustion = Mock(side_effect=[0, 0, 101])
        self.task.O_MD_FULL_NAME = SimpleNamespace(ocr_single=Mock(side_effect=['月读', '大天狗']))
        self.task.switch_strategy_soul = Mock(side_effect=[True, False])
        self.task.battle_boss = Mock()
        self.task.set_next_run = Mock()
        with self.assertRaises(TaskEnd):
            self.task.run_demons()
        self.task.battle_boss.assert_called_once_with(3, 1)
        self.assertEqual([c.args[0] for c in self.task.switch_strategy_soul.call_args_list],
                         ['tsukuyomi', 'default'])


class MetaDemonPursuitTests(unittest.TestCase):
    def setUp(self):
        self.task = ScriptTask.__new__(ScriptTask)
        self.now = 100.0
        self.six_star = True
        self.enabled = False
        self.unknown = False
        self.ignored_clicks = 0
        self.clicks = []
        self.task.screenshot = Mock()
        self.task.appear = self.appear
        self.task.click = self.click
        self.task.recognize_boss_name = Mock(return_value='大天狗')
        self.task.is_star56 = Mock(return_value=True)

    def appear(self, rule):
        if rule is self.task.I_BATTLE_DEMON:
            return True
        if rule is self.task.I_STAR6_POS_1:
            return self.six_star
        if rule is self.task.I_PURSUIT_ON:
            return self.enabled and not self.unknown
        if rule is self.task.I_PURSUIT_OFF:
            return not self.enabled and not self.unknown
        return False

    def click(self, rule, **kwargs):
        self.clicks.append(rule)
        if self.ignored_clicks:
            self.ignored_clicks -= 1
        else:
            self.enabled = not self.enabled

    def advance(self, duration):
        self.now += duration

    def sync(self):
        with patch('module.base.timer.time.time', side_effect=lambda: self.now), \
                patch('tasks.MetaDemon.script_task.sleep', side_effect=self.advance):
            self.task.set_strong_pursuit()

    def test_six_star_enables_then_non_six_star_disables(self):
        self.sync()
        self.assertTrue(self.enabled)
        self.six_star = False
        self.sync()
        self.assertFalse(self.enabled)
        self.assertEqual(self.clicks, [self.task.I_PURSUIT_OFF, self.task.I_PURSUIT_ON])

    def test_correct_state_does_not_toggle(self):
        for six_star in (True, False):
            self.six_star = self.enabled = six_star
            self.sync()
        self.assertEqual(self.clicks, [])

    def test_all_special_names_enable_five_star_pursuit(self):
        self.six_star = False
        for name in ('月读', '雪御前', '酒吞童子', '鬼王酒吞童子', '修罗鬼童丸', '鬼童丸'):
            with self.subTest(name=name):
                self.enabled = False
                self.task.recognize_boss_name.return_value = name
                self.sync()
                self.assertTrue(self.enabled)

    def test_low_star_special_name_does_not_enable_pursuit(self):
        self.six_star = False
        self.task.is_star56.return_value = False
        self.task.recognize_boss_name.return_value = '月读'
        self.sync()
        self.assertFalse(self.enabled)
        self.assertEqual(self.clicks, [])

    def test_special_then_ordinary_five_star_disables_pursuit(self):
        self.six_star = False
        self.task.recognize_boss_name.side_effect = [' 月\n读 ', '大天狗']
        self.sync()
        self.assertTrue(self.enabled)
        self.sync()
        self.assertFalse(self.enabled)

    def test_unrecognized_boss_prevents_challenge(self):
        self.task.recognize_boss_name.side_effect = GameStuckError('name not confirmed')
        self.task.ui_click_until_disappear = Mock()
        with self.assertRaises(GameStuckError):
            self.task.battle_boss()
        self.task.ui_click_until_disappear.assert_not_called()

    def test_ignored_click_retries_until_confirmed(self):
        self.ignored_clicks = 1
        self.sync()
        self.assertTrue(self.enabled)
        self.assertEqual(len(self.clicks), 2)
        self.assertGreaterEqual(self.task.screenshot.call_count, 3)

    def test_unrecognized_switch_never_blindly_clicks(self):
        self.unknown = True
        with self.assertRaises(GameStuckError):
            self.sync()
        self.assertEqual(self.clicks, [])

    def test_unconfirmed_pursuit_prevents_challenge(self):
        self.task.set_strong_pursuit = Mock(side_effect=GameStuckError('not confirmed'))
        self.task.ui_click_until_disappear = Mock()
        with self.assertRaises(GameStuckError):
            self.task.battle_boss()
        self.task.ui_click_until_disappear.assert_not_called()

    def test_transient_correct_state_is_not_accepted(self):
        frames = 0

        def screenshot():
            nonlocal frames
            frames += 1
            # 点击后的首帧短暂显示成功，随后恢复关闭；必须继续重试。
            self.enabled = frames == 4 or frames >= 10

        self.task.screenshot.side_effect = screenshot
        self.sync()
        self.assertGreaterEqual(frames, 12)
        self.assertGreaterEqual(len(self.clicks), 2)

    def test_unstable_star_detection_never_releases_challenge(self):
        def screenshot():
            self.six_star = not self.six_star

        self.task.screenshot.side_effect = screenshot
        with self.assertRaises(GameStuckError):
            self.sync()
        self.assertEqual(self.clicks, [])


class MetaDemonSummonTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.task = ScriptTask.__new__(ScriptTask)
        self.task.device = SimpleNamespace(image=None)
        self.task.screenshot = Mock()
        self.task.appear = lambda rule: rule is self.task.I_BATTLE_DEMON
        self.task.O_MD_FULL_NAME = SimpleNamespace(ocr_single=Mock())
        self.task.is_star56 = Mock(return_value=False)
        self.task.set_strong_pursuit = Mock()
        self.task.config = SimpleNamespace(notifier=SimpleNamespace(push=Mock()))

    def advance(self, duration):
        self.now += duration

    def summon(self):
        with patch('module.base.timer.time.time', side_effect=lambda: self.now), \
                patch('tasks.MetaDemon.script_task.sleep', side_effect=self.advance):
            return self.task.find_demon()

    def test_low_star_also_recognizes_name_then_confirms_pursuit(self):
        self.task.O_MD_FULL_NAME.ocr_single.side_effect = ['', '吸血姬', '', '吸血姬', '吸血姬']
        self.assertTrue(self.summon())
        self.assertEqual(self.task.O_MD_FULL_NAME.ocr_single.call_count, 5)
        self.task.set_strong_pursuit.assert_called_once()
        self.task.config.notifier.push.assert_not_called()

    def test_unrecognized_name_stops_before_pursuit_or_notification(self):
        self.task.O_MD_FULL_NAME.ocr_single.return_value = ''
        with self.assertRaises(GameStuckError):
            self.summon()
        self.task.set_strong_pursuit.assert_not_called()
        self.task.config.notifier.push.assert_not_called()

    def test_failed_pursuit_stops_summon_before_next_step(self):
        self.task.O_MD_FULL_NAME.ocr_single.return_value = '蚀月吸血姬'
        self.task.is_star56.return_value = True
        self.task.set_strong_pursuit.side_effect = GameStuckError('not confirmed')
        with self.assertRaises(GameStuckError):
            self.summon()
        self.task.is_star56.assert_not_called()
        self.task.config.notifier.push.assert_not_called()

    def test_high_star_notification_uses_confirmed_name(self):
        self.task.O_MD_FULL_NAME.ocr_single.return_value = '蚀月\n吸血姬'
        self.task.is_star56.return_value = True
        self.assertTrue(self.summon())
        self.task.config.notifier.push.assert_called_once_with(
            content='召唤到高星鬼王: 蚀月吸血姬', title='超鬼王')

    def test_summon_timeout_stops_before_name_recognition(self):
        self.task.appear = Mock(return_value=False)
        self.task.appear_then_click = Mock(return_value=False)
        with self.assertRaises(GameStuckError):
            self.summon()
        self.task.O_MD_FULL_NAME.ocr_single.assert_not_called()
        self.task.set_strong_pursuit.assert_not_called()


class MetaDemonPrepareTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.click_times = []
        self.task = ScriptTask.__new__(ScriptTask)
        self.task.current_count = 1
        self.task.screenshot = Mock()
        self.task.is_in_real_battle = lambda _: len(self.click_times) >= 2
        self.task.is_in_prepare = Mock(return_value=True)
        self.task.check_and_open_buff = Mock()
        self.task.switch_preset_team = Mock(side_effect=lambda *args: self.advance(8))
        self.task.appear_then_click = self.click

    def advance(self, duration):
        self.now += duration

    def click(self, rule, **kwargs):
        if rule is self.task.I_PREPARE_HIGHLIGHT:
            self.click_times.append(self.now)
            return True
        return False

    def test_slow_preset_resets_timeout_and_failed_ready_click_retries(self):
        config = GeneralBattleConfig(preset_enable=True, lock_team_enable=False)
        with patch('module.base.timer.time.time', side_effect=lambda: self.now), \
                patch('tasks.MetaDemon.script_task.sleep', side_effect=self.advance):
            self.assertTrue(self.task.battle_before(None, config, timeout=5))
        self.assertGreaterEqual(self.click_times[0], 109.0)
        self.assertEqual(len(self.click_times), 2)
        self.task.switch_preset_team.assert_called_once()
        # 首次点击无效时仍留在战前循环，直到第二次点击后进入真实战斗。
        self.assertGreater(self.task.screenshot.call_count, 2)

    def test_prepare_timeout_raises_instead_of_waiting_for_battle_end(self):
        self.task.is_in_real_battle = Mock(return_value=False)
        with patch('module.base.timer.time.time', side_effect=lambda: self.now), \
                patch('tasks.MetaDemon.script_task.sleep', side_effect=self.advance):
            with self.assertRaises(GameStuckError):
                self.task.battle_before(None, GeneralBattleConfig(lock_team_enable=False), timeout=1)

    def test_same_preset_skips_switch_and_changed_preset_switches_back(self):
        with patch('module.base.timer.time.time', side_effect=lambda: self.now), \
                patch('tasks.MetaDemon.script_task.sleep', side_effect=self.advance):
            for team in (1, 1, 2, 2, 1):
                self.click_times.clear()
                self.task.battle_before(None, GeneralBattleConfig(
                    preset_enable=True, preset_group=2, preset_team=team, lock_team_enable=False))
        self.assertEqual([call.args for call in self.task.switch_preset_team.call_args_list],
                         [(True, 2, 1), (True, 2, 2), (True, 2, 1)])
        self.assertEqual(self.task._active_preset_team, (2, 1))

    def test_failed_preset_is_not_cached(self):
        self.task._active_preset_team = (1, 1)
        self.task.switch_preset_team.side_effect = RuntimeError('preset failed')
        with self.assertRaises(RuntimeError):
            self.task.battle_before(None, GeneralBattleConfig(
                preset_enable=True, preset_group=1, preset_team=2, lock_team_enable=False))
        self.assertIsNone(self.task._active_preset_team)

    def test_prepare_timeout_does_not_cache_pending_preset(self):
        self.task.is_in_real_battle = Mock(return_value=False)
        with patch('module.base.timer.time.time', side_effect=lambda: self.now), \
                patch('tasks.MetaDemon.script_task.sleep', side_effect=self.advance):
            with self.assertRaises(GameStuckError):
                self.task.battle_before(None, GeneralBattleConfig(
                    preset_enable=True, lock_team_enable=False), timeout=1)
        self.assertIsNone(self.task._active_preset_team)

    def test_return_waits_until_activity_is_visible(self):
        frames = iter([False, False, True])
        self.task.appear = lambda rule: next(frames) if rule is self.task.I_FIND_DEMON else False
        self.task.appear_then_click = Mock()
        self.task.return_from_records()
        self.assertEqual(self.task.appear_then_click.call_count, 2)


if __name__ == '__main__':
    unittest.main()
