# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from time import sleep
from datetime import datetime

from module.logger import logger
from module.exception import TaskEnd, GameStuckError
from module.base.timer import Timer

from tasks.Orochi.script_task import ScriptTask as OrochiScriptTask
from tasks.Orochi.config import Layer
from tasks.Orochi.page import page_orochi
from tasks.GameUi.page import page_shikigami_records
from tasks.Exploration.page import page_gameplay
from tasks.TrueOrochi.assets import TrueOrochiAssets


class ScriptTask(OrochiScriptTask, TrueOrochiAssets):

    def run(self):
        conf = self.config.true_orochi.true_orochi_config
        true_orochi_soul_switched = False

        self.goto_page(page_gameplay)
        if not self.appear(self.I_ST_MODULE):
            logger.warning('True orochi module absent, no attempts left this week')
            self.check_times(True)
            raise TaskEnd('TrueOrochi')

        self.goto_page(page_orochi)
        sleep(0.5)
        battle = self.check_true_orochi(True)
        if not battle:
            logger.warning('Not find true orochi')
            logger.warning('Try to battle orochi for ten times')

            if not conf.find_true_orochi:
                logger.info('Not find_true_orochi_help')
                self.check_times(False)
                raise TaskEnd('TrueOrochi')

            self.switch_orochi_ten_soul()
            self.goto_page(page_orochi)
            self.check_layer(Layer.TEN)
            self.check_lock(False)
            count_orochi_ten = 0
            while 1:
                self.screenshot()
                if self.appear_then_click(self.I_PET_PRESENT, action=self.C_WIN_3, interval=1):
                    continue
                if not self.appear(self.I_OROCHI_FIRE):
                    continue
                if self.check_true_orochi(False):
                    logger.info('Find true orochi')
                    self.switch_true_orochi_soul()
                    true_orochi_soul_switched = True
                    self.goto_page(page_orochi)
                    battle = True
                    break
                if count_orochi_ten >= 10:
                    logger.warning('Not find true orochi')
                    battle = False
                    break
                if self.appear(self.I_OROCHI_FIRE):
                    self.ui_click_until_disappear(self.I_OROCHI_FIRE)
                    self.run_general_battle()
                    count_orochi_ten += 1
                    continue

        if not battle:
            self.check_times(battle)
            raise TaskEnd('TrueOrochi')

        if not true_orochi_soul_switched:
            self.switch_true_orochi_soul()
            self.goto_page(page_orochi)
        self.run_true_orochi_battle()
        self.check_times(True)

        self.goto_page(page_orochi)
        sleep(0.5)
        if self.check_true_orochi(True):
            battle = True
            logger.info('Find another true orochi entry, continue')
            self.run_true_orochi_battle()
            self.check_times(battle)

        raise TaskEnd('TrueOrochi')

    def run_true_orochi_battle(self):
        """Run one true orochi battle."""
        logger.hr('True Orochi Battle')
        while 1:
            self.screenshot()
            if self.appear(self.I_ST_CREATE_ROOM):
                break
            if self.appear_then_click(self.I_UI_CONFIRM, interval=1):
                continue
            if self.appear_then_click(self.I_ST_FIRE, interval=4):
                continue
            if self.appear_then_click(self.I_FIND_TS, interval=1):
                continue
        self.ensure_private()
        while 1:
            self.screenshot()
            if self.appear(self.I_ST_FIRE_PREPARE):
                break
            if self.appear_then_click(self.I_FIRE, interval=3, threshold=0.7):
                continue
            if self.appear_then_click(self.I_UI_CONFIRM, interval=1):
                continue
            if self.appear_then_click(self.I_ST_CREATE_ROOM, interval=1):
                continue

        logger.info('Battle prepare')
        self.ui_click(self.I_ST_FIRE_PREPARE, self.I_BUFF)
        while 1:
            self.screenshot()
            if not self.appear(self.I_BUFF):
                break
            if self.appear_then_click(self.I_ST_AUTO_FALSE, interval=1.8):
                continue

        self.device.stuck_record_add('BATTLE_STATUS_S')
        self.device.click_record_clear()
        logger.info('Start battle process')
        check_timer = Timer(280)
        check_timer.start()
        check_count = 0
        while 1:
            self.screenshot()
            if self.appear(self.I_GREED_GHOST):
                sleep(0.7)
                self.screenshot()
                if not self.appear(self.I_GREED_GHOST):
                    continue
                while 1:
                    self.screenshot()
                    if not self.appear(self.I_GREED_GHOST):
                        break
                    if self.appear_then_click(self.I_GREED_GHOST, interval=1):
                        continue
                    if self.appear_then_click(self.I_ST_FRAME, interval=1):
                        continue
                break
            if self.appear_then_click(self.I_ST_FRAME, interval=1):
                continue
            if check_timer.reached():
                if check_count > 3:
                    raise GameStuckError
                check_count += 1
                logger.warning('Battle timeout')
                check_timer.reset()
                self.device.stuck_record_clear()
                self.device.stuck_record_add('BATTLE_STATUS_S')
            sleep(0.5)

        logger.info('Battle process end')

    def switch_true_orochi_soul(self):
        switch_soul = self.config.true_orochi.switch_soul
        if switch_soul.enable:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul(switch_soul.switch_group_team)
        if switch_soul.enable_switch_by_name:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul_by_name(switch_soul.group_name, switch_soul.team_name)

    def switch_orochi_ten_soul(self):
        switch_soul = self.config.orochi.switch_soul
        if not switch_soul.auto_switch_soul:
            return
        logger.info('Switch soul for orochi layer ten')
        self.goto_page(page_shikigami_records)
        self.run_switch_soul(switch_soul.ten_switch)

    def check_true_orochi(self, screenshot=False) -> bool:
        if screenshot:
            self.screenshot()
        return self.appear(self.I_FIND_TS)

    def check_times(self, battle: bool):
        interval = self.config.true_orochi.scheduler.success_interval if battle \
            else self.config.true_orochi.scheduler.failure_interval
        self.set_next_run(task='TrueOrochi', target=datetime.now() + interval)

    def run_true_orochi(self) -> bool:
        pass


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device

    c = Config('oas1')
    d = Device(c)
    t = ScriptTask(c, d)
    t.screenshot()

    t.run()
