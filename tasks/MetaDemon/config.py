# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey

from pydantic import Field, field_validator

from module.logger import logger
from tasks.Component.config_scheduler import Scheduler
from tasks.Component.SwitchSoul.switch_soul_config import SwitchSoulConfig
from tasks.Component.config_base import ConfigBase


class DefaultStrategy(ConfigBase):
    md_preset_group_team_default_1: str = Field(default='1,1', description='md_preset_group_team_default_1_help')
    md_preset_group_team_tsukuyomi: str = Field(default='1,1', description='md_preset_group_team_tsukuyomi_help')
    md_preset_group_team_shuten: str = Field(default='1,1', description='md_preset_group_team_shuten_help')
    md_preset_group_team_kidomaru: str = Field(default='1,1', description='md_preset_group_team_kidomaru_help')

    @staticmethod
    def get_strategy_key(detect_name: str = '', is_hard_boss: bool = False) -> str:
        if is_hard_boss:
            name = ''.join((detect_name or '').split())
            if name in ('月读', '雪御前'):
                return 'tsukuyomi'
            elif name in ('酒吞童子', '鬼王酒吞童子'):
                return 'shuten'
            elif name in ('修罗鬼童丸', '鬼童丸'):
                return 'kidomaru'
        return 'default'

    def get_group_team(self, detect_name: str = '', is_hard_boss: bool = False) -> list[int]:
        key = self.get_strategy_key(detect_name, is_hard_boss)
        field = 'md_preset_group_team_default_1' if key == 'default' else f'md_preset_group_team_{key}'
        team = getattr(self, field)
        return Strategy.parse_group_team(team)


class Strategy(ConfigBase):
    @classmethod
    def parse_group_team(cls, team: str) -> list[int]:
        team = team.replace('，', ',').replace(' ', '')
        team = ''.join([c for c in team if c.isdigit() or c == ','])
        try:
            result = [int(i) for i in team.split(',')]
            if len(result) != 2:
                raise Exception('group team length is not 2')
            if result[0] < 0 and result[1] < 0:
                raise Exception('group team is not valid')
            # group 不能小于1 和大于 7
            if result[0] < 1 or result[0] > 7:
                raise Exception('group is not valid')
            # team 不能小于1 和大于 5
            if result[1] < 1 or result[1] > 5:
                raise Exception('team is not valid')
            return result
        except Exception as e:
            logger.error(f'group team string: {team}')
            logger.error(f'parse_team error: {e}')
            raise e


class MetaDemonConfig(ConfigBase):
    meta_crafting_card: bool = Field(default=True, description='craft_essence_help')
    auto_tea: bool = Field(default=False, description='auto_tea_help')
    # extreme_notify: bool = Field(default=False, description='extreme_notify_help')
    md_use_strategy: bool = Field(default=False, description='md_use_strategy_help')

    @field_validator('auto_tea', mode='after')
    @classmethod
    def to_false(cls, v):
        return False


class MetaDemon(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    switch_soul: SwitchSoulConfig = Field(default_factory=SwitchSoulConfig)
    meta_demon_config: MetaDemonConfig = Field(default_factory=MetaDemonConfig)
    md_default_strategy: DefaultStrategy = Field(default_factory=DefaultStrategy)
    md_soul_default: SwitchSoulConfig = Field(default_factory=SwitchSoulConfig)
    md_soul_tsukuyomi: SwitchSoulConfig = Field(default_factory=SwitchSoulConfig)
    md_soul_shuten: SwitchSoulConfig = Field(default_factory=SwitchSoulConfig)
    md_soul_kidomaru: SwitchSoulConfig = Field(default_factory=SwitchSoulConfig)
