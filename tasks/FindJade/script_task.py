from contextlib import contextmanager
from datetime import datetime, timedelta

from module.exception import TaskEnd
from module.logger import logger
from tasks.Component.SwitchAccount.switch_account import SwitchAccount
from tasks.DailyTrifles.script_task import ScriptTask as DailyTriflesTask
from tasks.FindJade.assets import FindJadeAssets
from tasks.FindJade.config import AccountInfo, FindJade
from tasks.GameUi.game_ui import GameUi


class ScriptTask(GameUi, FindJadeAssets):
    fade_conf: FindJade = None

    def run(self):
        self.fade_conf = self.config.find_jade

        for accountInfo in self.fade_conf.sup_account_list:
            logger.info("start %s-%s ", accountInfo.character, accountInfo.svr)
            if not self.is_need_login(accountInfo):
                logger.warning("%s Skipped last Login Time:%s", accountInfo.character, accountInfo.last_complete_time)
                continue

            with self._temporary_running_task(''):
                suc = SwitchAccount(self.config, self.device, accountInfo).switchAccount()
            if not suc:
                logger.warning("switch to %s-%s Failed", accountInfo.character, accountInfo.svr)
                continue

            logger.info("%s-%s login suc, run DailyTrifles before FindJade",
                        accountInfo.character, accountInfo.svr)
            self._run_daily_trifles_after_login(accountInfo)
            logger.info("%s-%s skip WantedQuests stage", accountInfo.character, accountInfo.svr)
            self.fade_conf.update_account_login_history(accountInfo)
            self.save_config()

        self.next_run("FindJade", success=True)
        raise TaskEnd("FindJade")

    def _run_daily_trifles_after_login(self, account_info: AccountInfo):
        if not self.config.daily_trifles.scheduler.enable:
            logger.info("DailyTrifles disabled")
            return

        try:
            with self._temporary_running_task('DailyTrifles'):
                DailyTriflesTask(config=self.config, device=self.device).run()
        except TaskEnd:
            logger.info("%s-%s DailyTrifles finished", account_info.character, account_info.svr)

    @contextmanager
    def _temporary_running_task(self, task_name: str):
        previous = getattr(self.config.model, 'running_task', '')
        object.__setattr__(self.config.model, 'running_task', task_name)
        try:
            yield
        finally:
            object.__setattr__(self.config.model, 'running_task', previous)

    def is_need_login(self, item: AccountInfo):
        lastTime = item.last_complete_time
        now = datetime.now()
        if now - lastTime > timedelta(hours=13):
            return True
        if (lastTime.hour >= 18 or lastTime.hour < 5) and (18 > now.hour >= 5):
            return True
        if (5 <= lastTime.hour < 18) and now.hour >= 18:
            return True
        return False

    def save_config(self):
        self.config.save()

    def next_run(self, task: str, finish: bool = False,
                 success: bool = None, server: bool = True, target: datetime = None) -> None:
        now = datetime.now()
        if success:
            if 5 <= now.hour < 18:
                self.set_next_run(task, target=now.replace(hour=18, minute=5))
            elif now.hour < 5:
                self.set_next_run(task, target=now.replace(hour=5, minute=5))
            else:
                self.set_next_run(task, target=now.replace(hour=18, minute=5) + timedelta(days=1))
        else:
            self.set_next_run(task, target=now + timedelta(minutes=10))


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device

    c = Config('oas1')
    d = Device(c)
    t = ScriptTask(c, d)

    t.run()
