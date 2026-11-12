# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey

import re

from pydantic import Field, field_validator, model_validator, model_serializer

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
    md_strategy_count: int = Field(default=0, ge=0, description='md_strategy_count_help')

    model_config = {'validate_assignment': True}

    @field_validator('auto_tea', mode='after')
    @classmethod
    def to_false(cls, v):
        return False


class PresetSoulStrategy(SwitchSoulConfig):
    md_preset_group_team: str = Field(default='1,1', description='md_preset_group_team_help')

    @field_validator('md_preset_group_team')
    @classmethod
    def validate_preset(cls, value):
        Strategy.parse_group_team(value)
        return value

    model_config = {'validate_assignment': True}


class NamedStrategy(PresetSoulStrategy):
    md_boss_names: str = Field(default='', description='md_boss_names_help')
    md_strong_pursuit: bool = Field(default=False, description='md_strong_pursuit_help')

    def matches(self, name):
        names = re.split(r'[,，、;；\n]+', self.md_boss_names)
        return bool(name) and name in {''.join(item.split()) for item in names}


class MetaDemon(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    switch_soul: SwitchSoulConfig = Field(default_factory=SwitchSoulConfig)
    meta_demon_config: MetaDemonConfig = Field(default_factory=MetaDemonConfig)
    md_default_group: PresetSoulStrategy = Field(default_factory=PresetSoulStrategy)
    md_strategy_list: list[NamedStrategy] = Field(default_factory=list)

    @model_validator(mode='before')
    @classmethod
    def migrate_groups(cls, value):
        if not isinstance(value, dict):
            return value
        data = dict(value)
        settings = dict(data.get('meta_demon_config', {}))
        groups = list(data.get('md_strategy_list') or [])
        # Existing GUI stores repeatable groups as numbered top-level objects.
        numbered = sorted((int(key.removeprefix('md_strategy_list_')), item)
                          for key, item in data.items()
                          if re.fullmatch(r'md_strategy_list_\d+', key))
        if numbered:
            groups = [item for _, item in numbered]
        old = data.get('md_default_strategy', {})
        if 'md_default_group' not in data:
            data['md_default_group'] = {
                **data.get('md_soul_default', {}),
                'md_preset_group_team': old.get('md_preset_group_team_default_1', '1,1'),
            }
        if not groups and ('md_default_strategy' in data or any(
                f'md_soul_{key}' in data for key in ('tsukuyomi', 'shuten', 'kidomaru'))):
            for key, names in (('tsukuyomi', '月读、雪御前'),
                               ('shuten', '酒吞童子、鬼王酒吞童子'),
                               ('kidomaru', '修罗鬼童丸、鬼童丸')):
                groups.append({**data.get(f'md_soul_{key}', {}), 'md_boss_names': names,
                               'md_strong_pursuit': True,
                               'md_preset_group_team': old.get(f'md_preset_group_team_{key}', '1,1')})
            settings['md_strategy_count'] = len(groups)
        settings.setdefault('md_strategy_count', len(groups))
        data['meta_demon_config'] = settings
        data['md_strategy_list'] = groups
        return data

    def ensure_groups(self):
        count = self.meta_demon_config.md_strategy_count
        while len(self.md_strategy_list) < count:
            self.md_strategy_list.append(NamedStrategy())

    @model_serializer(mode='wrap')
    def serialize_groups(self, handler, info):
        self.ensure_groups()
        data = handler(self)
        groups = data.pop('md_strategy_list')
        # Keep hidden groups on disk so reducing and restoring the count loses no settings.
        if info.context and info.context.get('hide'):
            groups = groups[:self.meta_demon_config.md_strategy_count]
        for index, group in enumerate(groups, 1):
            data[f'md_strategy_list_{index}'] = group
        return data

    def get_strategy_key(self, detect_name='', is_hard_boss=False):
        self.ensure_groups()
        name = ''.join((detect_name or '').split())
        if is_hard_boss:
            for index, group in enumerate(self.md_strategy_list[:self.meta_demon_config.md_strategy_count], 1):
                if group.matches(name):
                    return f'md_strategy_list_{index}'
        return 'default'

    def get_strategy(self, key):
        if key == 'default':
            return self.md_default_group
        self.ensure_groups()
        return self.md_strategy_list[int(key.removeprefix('md_strategy_list_')) - 1]

    def get_group_team(self, detect_name='', is_hard_boss=False):
        return Strategy.parse_group_team(self.get_strategy(
            self.get_strategy_key(detect_name, is_hard_boss)).md_preset_group_team)
