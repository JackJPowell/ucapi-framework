"""
Entity subclasses with built-in state management.

Provides concrete entity implementations that manage their own state using
property-based accessors and update methods.

:copyright: (c) 2025 by Jack Powell.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

from .media_player import MediaPlayerEntity
from .light import LightEntity
from .cover import CoverEntity
from .button import ButtonEntity
from .climate import ClimateEntity
from .ir_emitter import IREmitterEntity
from .remote import RemoteEntity
from .select import SelectEntity
from .sensor import SensorEntity
from .switch import SwitchEntity
from .voice_assistant import VoiceAssistantEntity

__all__ = [
    "MediaPlayerEntity",
    "LightEntity",
    "CoverEntity",
    "ButtonEntity",
    "ClimateEntity",
    "IREmitterEntity",
    "RemoteEntity",
    "SelectEntity",
    "SensorEntity",
    "SwitchEntity",
    "VoiceAssistantEntity",
]
