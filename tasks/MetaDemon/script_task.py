# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from time import sleep
from random import uniform


from module.base.timer import Timer
from module.atom.click import RuleClick
from module.logger import logger
from module.exception import TaskEnd, GameStuckError


from tasks.Component.RightActivity.right_activity import RightActivity
from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tasks.GameUi.game_ui import GameUi
from tasks.MetaDemon.config import DefaultStrategy, Strategy
from tasks.MetaDemon.assets import MetaDemonAssets



class Star56(GameUi, MetaDemonAssets):

    def is_star56(self):
        if not self.appear(self.I_STAR56_POS_1):
            return True
        return False



class ScriptTask(RightActivity, GeneralBattle, SwitchSoul, Star56):
    # 活动页右下方的式神录入口，基于1280x720活动截图。
    C_MD_RECORDS = RuleClick(roi_front=(1040,628,38,32), roi_back=(1040,628,38,32), name='md_records')

    def run(self):
        self._active_strategy_soul = None
        self._active_preset_team = None
        self.enter_activity()
        soul = self.config.meta_demon.switch_soul
        if soul.enable or soul.enable_switch_by_name:
            self.ui_click(self.C_MD_RECORDS, stop=self.I_CHECK_RECORDS, interval=1.5)
            if soul.enable_switch_by_name:
                self.run_switch_soul_by_name(soul.group_name, soul.team_name)
            else:
                self.run_switch_soul(soul.switch_group_team)
            self.return_from_records()
        if self.config.meta_demon.meta_demon_config.meta_crafting_card:
            self.crafting()

        self.run_demons()

    def enter_activity(self):
        self.enter(self.I_RIGHT_ENTER)
        while 1:
            self.screenshot()
            if self.appear(self.I_FIND_DEMON) or self.appear(self.I_BATTLE_DEMON):
                break

            if self.ui_reward_appear_click():
                continue
            if self.appear_then_click(self.I_UI_BACK_RED, interval=1.5):
                continue
            if self.appear_then_click(self.I_ENTER_ENSURE, interval=1):
                continue
            if self.appear_then_click(self.I_ENTER2, interval=1):
                continue

    def run_demons(self):
        boss_timer = Timer(50)
        boss_timer.start()
        while 1:
            battle_processing = False
            is_hard_boss = False  # 五星或者六星
            self.screenshot()
            if not (self.appear(self.I_FIND_DEMON) or self.appear(self.I_BATTLE_DEMON)):
                continue

            # 先看自己有没有鬼王要打
            if (not self.appear(self.I_BOSS_EMPTY) and
                    (self.appear(self.I_BOSS_CONVENE) or self.appear(self.I_BOOS_PUBLIC))):
                logger.info('Try to battle boss from self')
                self.click(self.I_BOSS_EMPTY, interval=1.5)
                battle_processing = True
                if self.is_star56():
                    is_hard_boss = True
            # 看别人的是否给我共享鬼王
            if not battle_processing:
                if not self.appear(self.I_BOSS_EMPTY_1) and self.ocr_appear(self.O_BOSS_EMPTY_1):
                    logger.info('Try to battle boss 1 from others')
                    self.click(self.I_BOSS_EMPTY_1, interval=1.5)
                    self.ui_click(self.I_BOSS_EMPTY_1, stop=self.I_BATTLE_DEMON, interval=1.5)
                    battle_processing = True
                    is_hard_boss = True
                elif not self.appear(self.I_BOSS_EMPTY_2):
                    logger.info('Try to battle boss 2 from others')
                    self.click(self.I_BOSS_EMPTY_2, interval=1.5)
                    self.ui_click(self.I_BOSS_EMPTY_1, stop=self.I_BATTLE_DEMON, interval=1.5)
                    battle_processing = True
                    is_hard_boss = True
            # 是否喝茶 疲劳满了就不打了
            current_exhaustion = self.current_exhaustion()
            if current_exhaustion > 100:
                if self.config.meta_demon.meta_demon_config.auto_tea:
                    logger.info('Exhaustion is full, buy tea')
                    boss_timer.reset()
                    self.buy_tea()
                else:
                    logger.info('Exhaustion is full, exit')
                    break
            # 超时结束
            if boss_timer.reached():
                logger.info('Time out, exit')
                break
            if battle_processing and self.appear(self.I_BATTLE_DEMON):
                target_group_team = [None, None]
                if self.config.meta_demon.meta_demon_config.md_use_strategy:
                    detect_name = ''
                    if is_hard_boss:
                        detect_name = self.O_MD_FULL_NAME.ocr_single(self.device.image) or ''
                        logger.info(f'detect_full_name: {detect_name}')
                    target_group_team = self.config.meta_demon.md_default_strategy.get_group_team(
                        detect_name, is_hard_boss)
                    strategy_key = self.config.meta_demon.md_default_strategy.get_strategy_key(
                        detect_name, is_hard_boss)
                    if self.switch_strategy_soul(strategy_key):
                        # 离开期间目标可能消失，返回后重新选择和识别，不能直接攻击旧目标。
                        boss_timer.reset()
                        continue
                logger.info(f'preset group team: {target_group_team}')
                self.battle_boss(target_group_team[0], target_group_team[1])
                boss_timer.reset()
                continue

            # 自己召唤鬼王
            if current_exhaustion < 90 and self.find_demon():
                boss_timer.reset()
                continue

        # 退出
        self.ui_click(self.I_UI_BACK_YELLOW, self.I_CHECK_MAIN, interval=1.4)
        logger.info('Exit MetaDemon')
        self.set_next_run(task="MetaDemon", success=True)
        raise TaskEnd

    def switch_strategy_soul(self, strategy_key: str) -> bool:
        soul = getattr(self.config.meta_demon, f'md_soul_{strategy_key}')
        if soul.enable_switch_by_name:
            group_name, team_name = soul.group_name.strip(), soul.team_name.strip()
            if not group_name or not team_name:
                raise ValueError(f'{strategy_key}: soul group/team name must not be empty')
            target = ('name', group_name, team_name)
        elif soul.enable:
            group, team = Strategy.parse_group_team(soul.switch_group_team)
            if team > 4:
                raise ValueError('Switch soul team must be in [1-4]')
            target = ('number', group, team)
        else:
            return False
        if getattr(self, '_active_strategy_soul', None) == target:
            return False

        logger.info(f'Switch MetaDemon soul for {strategy_key}: {target}')
        self.ui_click(self.C_MD_RECORDS, stop=self.I_CHECK_RECORDS, interval=1.5)
        if target[0] == 'name':
            self.run_switch_soul_by_name(target[1], target[2])
        else:
            self.run_switch_soul((target[1], target[2]))
        self.return_from_records()
        self._active_strategy_soul = target
        return True

    def return_from_records(self):
        # 御魂预设、式神录逐层返回，直到重新看到活动的召唤或挑战按钮。
        timer = Timer(30).start()
        while not timer.reached():
            self.screenshot()
            if self.appear(self.I_FIND_DEMON) or self.appear(self.I_BATTLE_DEMON):
                return
            self.appear_then_click(self.I_UI_BACK_YELLOW, interval=1.5)
        raise GameStuckError('MetaDemon: failed to return from shikigami records')

    def battle_before(self, buff, config: GeneralBattleConfig, timeout: float = 30) -> bool:
        timer = Timer(timeout).start()
        configured = False
        pending_preset = None
        while not timer.reached():
            self.screenshot()
            if self.is_in_real_battle(False):
                if pending_preset is not None:
                    self._active_preset_team = pending_preset
                return True
            if self.appear_then_click(self.I_DISABLE_7DAYS_DIFF_SOUL, interval=0.8):
                continue
            if self.appear_then_click(self.I_CONFIRM_CLOSE_DIFF_SOUL, interval=0.8):
                continue
            if self.is_in_prepare(False):
                if not config.lock_team_enable:
                    if self.current_count == 1 and not configured:
                        target_preset = (config.preset_group, config.preset_team)
                        switch_preset = config.preset_enable and target_preset != getattr(
                            self, '_active_preset_team', None)
                        if switch_preset:
                            # 切换失败或准备超时后，不复用此前的队伍缓存。
                            self._active_preset_team = None
                            self.switch_preset_team(True, *target_preset)
                            pending_preset = target_preset
                        self.check_and_open_buff(buff)
                        configured = True
                        # 预设关闭后仍有上阵动画；等待后重新截图，不能复用切换前的准备状态。
                        if switch_preset:
                            sleep(1)
                        timer.reset()
                        continue
                    self.appear_then_click(self.I_PREPARE_HIGHLIGHT, interval=1.2)
            sleep(0.2)
        # 通用战斗会忽略False返回值，直接抛出异常避免卡入战斗等待。
        raise GameStuckError('MetaDemon: prepare timed out before entering battle')

    def current_exhaustion(self) -> int:
        self.screenshot()
        cu, res, total = self.O_MD_EXHAUSTION.ocr(self.device.image)
        return int(cu)

    def buy_tea(self):
        pass

    def crafting(self):
        """
        把一星合成二星
        @return:
        """
        logger.info('Star crafting 1 star to 2 star')
        self.ui_click(self.I_CRAFTING_1, self.I_CRAFTING_START, interval=1.5)
        timer = Timer(3).start()
        count = 0
        while 1:
            self.screenshot()
            if self.ui_reward_appear_click():
                timer.reset()
                continue
            if timer.reached() or count > 3:
                break
            if not self.ocr_appear(self.O_CRAFTING_CARD_1):
                break
            if self.appear(self.I_CRAFTING_EMPTY) or self.appear(self.I_CRAFTING_EMPTY_NEW):
                if self.appear_then_click(self.I_CRAFTING_CARD_STAR_1, interval=1):
                    continue
            else:
                self.appear_then_click(self.I_CRAFTING_START, interval=3)
                count += 1
                timer.reset()
                continue
        logger.info('Finish star crafting')
        self.ui_click_until_disappear(self.I_UI_BACK_RED, interval=1)
        sleep(0.5)

    def find_demon(self) -> bool:
        """
        召唤鬼王
        @return:
        """
        logger.info('Find demon')
        delay = uniform(1, 20)
        logger.info(f'Wait {delay:.1f}s before summoning next demon')
        sleep(delay)
        timer = Timer(30).start()
        while not timer.reached():
            self.screenshot()
            if self.appear(self.I_BATTLE_DEMON) and not self.appear(self.I_BOSS_EMPTY):
                break
            if self.appear_then_click(self.I_FIND_DEMON, interval=3.5):
                continue
            sleep(0.3)
        else:
            raise GameStuckError('MetaDemon: summon timed out before boss details appeared')
        detect_full_name = self.recognize_boss_name()
        logger.info(f'召唤鬼王识别完成: {detect_full_name}')
        # 召唤完成后立即校正，挑战前仍会再次检查，避免期间目标或状态发生变化。
        self.set_strong_pursuit(detect_full_name)
        if self.is_star56():
            logger.info('Star 5 or 6 demon found')
            logger.info(f'召唤到高星鬼王: {detect_full_name}')
            self.config.notifier.push(content=f'召唤到高星鬼王: {detect_full_name}', title='超鬼王')
        return True

    def recognize_boss_name(self) -> str:
        """每次召唤均识别名字，连续两次一致才继续，失败则阻止后续操作。"""
        timer = Timer(15).start()
        previous = ''
        sleep(1)  # 等待召唤展示动画，不能直接读取召唤按钮消失时的过渡帧。
        while not timer.reached():
            self.screenshot()
            name = ''
            if self.appear(self.I_BATTLE_DEMON) and not self.appear(self.I_BOSS_EMPTY):
                name = ''.join((self.O_MD_FULL_NAME.ocr_single(self.device.image) or '').split())
            if name and name == previous:
                return name
            previous = name
            sleep(0.4)
        raise GameStuckError('MetaDemon: failed to confirm summoned boss name')

    def battle_boss(self, group: int = None, team: int = None) -> bool:
        logger.info('Battle boss')
        self.set_strong_pursuit()
        self.ui_click_until_disappear(self.I_BATTLE_DEMON, interval=1.8)
        battle_config = GeneralBattleConfig()
        battle_config.lock_team_enable = False
        if group is None and team is None:
            battle_config.preset_enable = False
            success = self.run_general_battle(battle_config)
            return True if success else False
        # 使用选定的预设阵容
        else:
            battle_config.preset_enable = True
            battle_config.preset_group = group
            battle_config.preset_team = team
            tmp_battle_count = self.current_count
            self.current_count = 0
            success = self.run_general_battle(battle_config)
            self.current_count = tmp_battle_count + 1
            return True if success else False

    def set_strong_pursuit(self, detect_name: str = None):
        """六星及特殊名单内的五星鬼王开启强追，确认开关后才继续。"""
        # 挑战前重新识别当前目标，不依赖阵容切换开关，也不复用上一次鬼王的名字。
        if detect_name is None:
            detect_name = self.recognize_boss_name()
        special_boss = DefaultStrategy.get_strategy_key(detect_name, True) != 'default'
        timer = Timer(15).start()
        previous = None
        stable_count = 0
        sleep(1)  # 详情页及强追按钮可能先于召唤动画结束出现。
        while not timer.reached():
            self.screenshot()
            if not self.appear(self.I_BATTLE_DEMON):
                previous = None
                stable_count = 0
                sleep(0.3)
                continue
            six_star = self.appear(self.I_STAR6_POS_1)
            enable = six_star or special_boss
            is_on = self.appear(self.I_PURSUIT_ON)
            is_off = self.appear(self.I_PURSUIT_OFF)
            state = (enable, is_on, is_off)
            stable_count = stable_count + 1 if state == previous else 1
            if state != previous:
                logger.info(f'Strong pursuit detection: boss={detect_name}, special={special_boss}, '
                            f'six_star={six_star}, target={enable}, on={is_on}, off={is_off}, '
                            f'star_template_score={self.I_STAR6_POS_1.last_score:.3f}')
            previous = state
            # 星级与开关均连续三帧一致才操作；点击后重新累计三帧确认，不能点击即放行。
            if stable_count >= 3 and is_on != is_off:
                if is_on == enable:
                    logger.info(f'Strong pursuit confirmed: {enable}')
                    return
                logger.info(f'Set strong pursuit: {enable}')
                # 只点击已识别的相反状态，随后重新截图确认，避免盲点反复开关。
                self.click(self.I_PURSUIT_OFF if enable else self.I_PURSUIT_ON, interval=1.2)
                previous = None
                stable_count = 0
                sleep(0.8)
            sleep(0.3)
        raise GameStuckError('MetaDemon: failed to confirm strong pursuit state')

    def battle_wait(self, random_click_swipt_enable: bool) -> bool:
        # 重写
        self.device.stuck_record_add('BATTLE_STATUS_S')
        self.device.click_record_clear()
        logger.info("Start battle process")
        self.boss_mark_reset()
        while 1:
            self.screenshot()
            # if self.appear_then_click(self.I_WIN, interval=1):
            #     continue
            if self.appear(self.I_WIN):
                logger.info('Win battle')
                self.ui_click_until_disappear(self.I_WIN)
                return True

            if self.appear(self.I_MD_BATTLE_FAILURE):
                logger.warning('False battle')
                self.ui_click_until_disappear(self.I_MD_BATTLE_FAILURE)
                return False
            if self.boss_mark():
                continue


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device

    c = Config('体服')
    d = Device(c)
    t = ScriptTask(c, d)

    t.run()
