# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from datetime import datetime, timedelta
from pydantic import BaseModel, Field

from tasks.Component.config_scheduler import Scheduler
from tasks.Component.config_base import ConfigBase, DateTime, dynamic_hide
from enum import Enum


class SummonType(str, Enum):
    default = '普通召唤'
    recall = '今忆召唤'


class DoneRecord(ConfigBase):
    courtyard_affairs_dt: DateTime = Field(default=datetime.fromisoformat("2023-01-01 00:00:00"))


class DailyTriflesConfig(BaseModel):
    courtyard_affairs: bool = Field(default=True)
    one_summon: bool = Field(title='One Summon', default=False)
    # 召唤类型
    summon_type: SummonType = Field(default=SummonType.default, description='召唤类型')
    # 是否绘制神秘图案
    draw_mystery_pattern: bool = Field(title='Draw Mystery Pattern', default=False, description='是否绘制神秘图案')
    guild_wish: bool = Field(title='Guild Wish', default=False)
    friend_love: bool = Field(title='Friend Love', default=False)
    luck_msg: bool = Field(title='Luck Msg', default=False)
    store_sign: bool = Field(title='Store Sign', default=False, description='store_sign_help')
    # 每天购买体力数量
    buy_sushi_count: int = Field(title='Buy Sushi Count', default=-1)

    hide_fields = dynamic_hide('draw_mystery_pattern')


class DailyTrifles(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    trifles_config: DailyTriflesConfig = Field(default_factory=DailyTriflesConfig)
    done_record: DoneRecord = Field(default_factory=DoneRecord)

    hide_fields = dynamic_hide('done_record')

    def today_is_done(self, mode: str) -> bool:
        done_dt = getattr(self.done_record, f'{mode}_dt', None)
        if done_dt is None:
            return False
        return done_dt.date() == datetime.today().date()
