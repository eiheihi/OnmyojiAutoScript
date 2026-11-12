import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from module.exception import TaskEnd, GameStuckError
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.MetaDemon.config import DefaultStrategy, MetaDemon, NamedStrategy
from module.config.config_model import ConfigModel
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
        self.assertEqual(config.get_group_team(), [3, 2])
        self.assertEqual(config.meta_demon_config.md_strategy_count, 3)
        self.assertNotIn('md_default_strategy', config.model_dump())
        self.assertEqual(MetaDemon.model_validate(config.model_dump()), config)


class ExtensibleStrategyTests(unittest.TestCase):
    def test_legacy_presets_and_souls_migrate_together(self):
        config = MetaDemon.model_validate({
            'md_default_strategy': {
                'md_preset_group_team_default_1': '2,1',
                'md_preset_group_team_tsukuyomi': '3,2',
                'md_preset_group_team_shuten': '4,3',
                'md_preset_group_team_kidomaru': '5,4',
            },
            'md_soul_default': {'enable': True, 'switch_group_team': '1,2'},
            'md_soul_tsukuyomi': {'enable_switch_by_name': True, 'group_name': '月读组', 'team_name': '输出'},
            'md_soul_shuten': {'enable': True, 'switch_group_team': '2,3'},
            'md_soul_kidomaru': {'enable': True, 'switch_group_team': '3,4'},
        })
        for name, team in [('月读', [3, 2]), ('雪御前', [3, 2]), ('酒吞童子', [4, 3]), ('修罗鬼童丸', [5, 4])]:
            self.assertEqual(config.get_group_team(name, True), team)
        self.assertEqual(config.md_default_group.switch_group_team, '1,2')
        self.assertEqual(config.md_strategy_list[0].group_name, '月读组')
        self.assertTrue(config.md_strategy_list[0].enable_switch_by_name)
        self.assertEqual(config.md_strategy_list[1].switch_group_team, '2,3')
        self.assertEqual(config.md_strategy_list[2].switch_group_team, '3,4')
        self.assertEqual(MetaDemon.model_validate(config.model_dump()), config)

    def test_chinese_names_and_separators(self):
        group = NamedStrategy(md_boss_names='月读，雪御前、酒吞童子；鬼童丸\n大天狗')
        for name in ('月读', '雪御前', '酒吞童子', '鬼童丸', '大天狗'):
            self.assertTrue(group.matches(name))
        self.assertFalse(group.matches('童丸'))

    def test_fresh_config_has_only_default_group(self):
        config = MetaDemon()
        self.assertFalse(NamedStrategy().md_strong_pursuit)
        self.assertEqual(config.meta_demon_config.md_strategy_count, 0)
        self.assertEqual(config.get_strategy_key('boss', True), 'default')
        self.assertEqual(config.get_group_team(), [1, 1])

    def test_custom_names_priority_and_default(self):
        config = MetaDemon(meta_demon_config={'md_strategy_count': 5})
        config.ensure_groups()
        config.md_default_group.md_preset_group_team = '2,1'
        config.md_strategy_list[0].md_boss_names = ' Alpha, Beta ; Gamma'
        config.md_strategy_list[0].md_preset_group_team = '3,2'
        config.md_strategy_list[4].md_boss_names = 'Alpha,Delta'
        config.md_strategy_list[4].md_preset_group_team = '4,3'
        for name in ('Alpha', ' B e t a ', 'Gamma'):
            self.assertEqual(config.get_group_team(name, True), [3, 2])
        self.assertEqual(config.get_group_team('Delta', True), [4, 3])
        for name in ('', None, 'Alph', 'Other'):
            self.assertEqual(config.get_group_team(name, True), [2, 1])
        self.assertEqual(config.get_group_team('Alpha', False), [2, 1])
        self.assertEqual(MetaDemon.model_validate(config.model_dump()), config)

    def test_count_hides_but_preserves_groups(self):
        config = MetaDemon(meta_demon_config={'md_strategy_count': 4})
        config.ensure_groups()
        config.md_strategy_list[3].md_boss_names = 'Saved'
        config.meta_demon_config.md_strategy_count = 1
        self.assertNotIn('md_strategy_list_4', config.model_dump(context={'hide': True}))
        config = MetaDemon.model_validate(config.model_dump())
        self.assertEqual(config.get_strategy_key('Saved', True), 'default')
        config.meta_demon_config.md_strategy_count = 4
        self.assertEqual(config.get_strategy_key('Saved', True), 'md_strategy_list_4')

    def test_gui_reads_and_saves_new_group_and_roundtrips(self):
        model = ConfigModel()
        with patch.object(ConfigModel, 'save') as save:
            self.assertTrue(model.script_set_arg('MetaDemon', 'meta_demon_config', 'md_strategy_count', 5))
            args = model.script_task('MetaDemon')
            self.assertIn('md_default_group', args)
            self.assertIn('md_strategy_list_5', args)
            self.assertNotIn('md_strong_pursuit', [arg['name'] for arg in args['md_default_group']])
            self.assertIn('md_strong_pursuit', [arg['name'] for arg in args['md_strategy_list_5']])
            self.assertNotIn('md_soul_tsukuyomi', args)
            for field, value in [('md_boss_names', 'NewBoss'), ('md_preset_group_team', '6,5'),
                                 ('enable', True), ('switch_group_team', '3,4'), ('md_strong_pursuit', True)]:
                self.assertTrue(model.script_set_arg('MetaDemon', 'md_strategy_list_5', field, value))
            self.assertTrue(save.called)
        restored = MetaDemon.model_validate(model.meta_demon.model_dump())
        self.assertEqual(restored.get_group_team('NewBoss', True), [6, 5])
        self.assertEqual(restored.get_strategy('md_strategy_list_5').switch_group_team, '3,4')
        self.assertTrue(restored.get_strategy('md_strategy_list_5').enable)
        self.assertTrue(restored.get_strategy('md_strategy_list_5').md_strong_pursuit)

    def test_custom_group_switches_its_own_soul(self):
        config = MetaDemon(meta_demon_config={'md_strategy_count': 5})
        config.ensure_groups()
        config.md_strategy_list[4].enable = True
        config.md_strategy_list[4].switch_group_team = '4,2'
        task = ScriptTask.__new__(ScriptTask)
        task.config = SimpleNamespace(meta_demon=config)
        task.ui_click = Mock()
        task.return_from_records = Mock()
        task.run_switch_soul = Mock()
        self.assertTrue(task.switch_strategy_soul('md_strategy_list_5'))
        task.run_switch_soul.assert_called_once_with((4, 2))
        self.assertFalse(task.switch_strategy_soul('md_strategy_list_5'))


class MetaDemonSoulTests(unittest.TestCase):
    def setUp(self):
        self.config = MetaDemon.model_validate({'md_default_strategy': {}})
        self.config.md_default_group.enable = True
        self.config.md_default_group.switch_group_team = '1,1'
        self.config.md_strategy_list[0].enable = True
        self.config.md_strategy_list[0].switch_group_team = '2,3'
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
        self.assertTrue(self.task.switch_strategy_soul('md_strategy_list_1'))
        self.assertFalse(self.task.switch_strategy_soul('md_strategy_list_1'))
        self.assertTrue(self.task.switch_strategy_soul('default'))
        self.assertEqual([c.args[0] for c in self.task.run_switch_soul.call_args_list],
                         [(1, 1), (2, 3), (1, 1)])
        self.assertEqual(self.task.return_from_records.call_count, 3)
        self.task.goto_page.assert_not_called()
        self.task.enter_activity.assert_not_called()
        self.assertIs(self.task.ui_click.call_args.args[0], self.task.C_MD_RECORDS)

    def test_name_switch_takes_precedence(self):
        soul = self.config.md_strategy_list[0]
        soul.enable_switch_by_name = True
        soul.group_name = ' group '
        soul.team_name = ' team '
        self.assertTrue(self.task.switch_strategy_soul('md_strategy_list_1'))
        self.task.run_switch_soul_by_name.assert_called_once_with('group', 'team')
        self.task.run_switch_soul.assert_not_called()

    def test_disabled_soul_stays_in_activity(self):
        self.assertFalse(self.task.switch_strategy_soul('md_strategy_list_2'))
        self.task.ui_click.assert_not_called()

    def test_invalid_soul_fails_before_leaving_activity(self):
        self.config.md_strategy_list[0].switch_group_team = '1,5'
        with self.assertRaises(ValueError):
            self.task.switch_strategy_soul('md_strategy_list_1')
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
        self.config.md_default_group.md_preset_group_team = '3,1'
        self.config.md_strategy_list[0].md_preset_group_team = '3,2'
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
                         ['md_strategy_list_1', 'default'])


class MetaDemonPursuitTests(unittest.TestCase):
    def setUp(self):
        self.task = ScriptTask.__new__(ScriptTask)
        self.config = MetaDemon.model_validate({'md_default_strategy': {}})
        self.task.config = SimpleNamespace(meta_demon=self.config)
        self.now = 100.0
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

    def test_high_star_enables_then_low_star_disables(self):
        self.sync()
        self.assertTrue(self.enabled)
        self.task.is_star56.return_value = False
        self.sync()
        self.assertFalse(self.enabled)
        self.assertEqual(self.clicks, [self.task.I_PURSUIT_OFF, self.task.I_PURSUIT_ON])

    def test_correct_state_does_not_toggle(self):
        for high_star in (True, False):
            self.enabled = high_star
            self.task.is_star56.return_value = high_star
            self.sync()
        self.assertEqual(self.clicks, [])

    def test_all_special_names_enable_five_star_pursuit(self):
        for name in ('月读', '雪御前', '酒吞童子', '鬼王酒吞童子', '修罗鬼童丸', '鬼童丸'):
            with self.subTest(name=name):
                self.enabled = False
                self.task.recognize_boss_name.return_value = name
                self.sync()
                self.assertTrue(self.enabled)

    def test_custom_switch_off_disables_high_star(self):
        self.task.recognize_boss_name.return_value = '月读'
        self.config.md_strategy_list[0].md_strong_pursuit = False
        self.enabled = True
        self.sync()
        self.assertFalse(self.enabled)

    def test_arbitrary_custom_group_switch_controls_high_star(self):
        self.config.md_strategy_list[0].md_boss_names = '自定义鬼王'
        self.task.recognize_boss_name.return_value = '自定义鬼王'
        for enable in (True, False):
            with self.subTest(enable=enable):
                self.config.md_strategy_list[0].md_strong_pursuit = enable
                self.sync()
                self.assertEqual(self.enabled, enable)

    def test_default_group_enables_high_star(self):
        self.config.meta_demon_config.md_strategy_count = 0
        self.task.recognize_boss_name.return_value = '月读'
        self.sync()
        self.assertTrue(self.enabled)
        self.sync()
        self.assertTrue(self.enabled)

    def test_pursuit_is_independent_of_preset_switch(self):
        self.config.meta_demon_config.md_use_strategy = False
        self.task.recognize_boss_name.return_value = '月读'
        self.sync()
        self.assertTrue(self.enabled)

    def test_low_star_special_name_does_not_enable_pursuit(self):
        self.task.is_star56.return_value = False
        self.task.recognize_boss_name.return_value = '月读'
        self.sync()
        self.assertFalse(self.enabled)
        self.assertEqual(self.clicks, [])

    def test_special_then_ordinary_five_star_keeps_pursuit(self):
        self.task.recognize_boss_name.side_effect = [' 月\n读 ', '大天狗']
        self.sync()
        self.assertTrue(self.enabled)
        self.sync()
        self.assertTrue(self.enabled)

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
            self.task.is_star56.return_value = not self.task.is_star56.return_value

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

    def test_dream_gift_finishes_task_before_recognition(self):
        self.task.appear = lambda rule: rule is self.task.I_MD_DREAM_GIFT
        self.task.ui_click_until_smt_disappear = Mock()
        self.task.ui_click = Mock()
        self.task.set_next_run = Mock()
        with self.assertRaises(TaskEnd):
            self.summon()
        self.task.ui_click_until_smt_disappear.assert_called_once_with(
            self.task.C_MD_GIFT_CLOSE, self.task.I_MD_DREAM_GIFT, interval=1)
        self.task.set_next_run.assert_called_once_with(task='MetaDemon', success=True)
        self.task.O_MD_FULL_NAME.ocr_single.assert_not_called()
        self.task.set_strong_pursuit.assert_not_called()
        self.task.config.notifier.push.assert_not_called()

    def test_delayed_dream_gift_finishes_during_name_recognition(self):
        self.task.appear = lambda rule: rule is (
            self.task.I_MD_DREAM_GIFT if self.task.screenshot.call_count >= 2
            else self.task.I_BATTLE_DEMON)
        self.task.ui_click_until_smt_disappear = Mock()
        self.task.ui_click = Mock()
        self.task.set_next_run = Mock()
        with self.assertRaises(TaskEnd):
            self.summon()
        self.task.set_next_run.assert_called_once_with(task='MetaDemon', success=True)
        self.task.O_MD_FULL_NAME.ocr_single.assert_not_called()
        self.task.set_strong_pursuit.assert_not_called()

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
