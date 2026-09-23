"""Typed protocol and deterministic, reliable in-process message transport."""

from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol

from .dcop import Assignment, Factor, identifier


class ProtocolError(ValueError):
    pass


class Kind(str, Enum):
    EXPLORE = 'dfs_explore'
    RETURN = 'dfs_return'
    SEEN = 'dfs_seen'
    UTIL = 'util'
    VALUE = 'value'


@dataclass(frozen=True)
class Explore:
    path: tuple[str, ...]

    def __post_init__(self):
        object.__setattr__(self, 'path', tuple(self.path))
        if not self.path or len(set(self.path)) != len(self.path):
            raise ProtocolError('DFS path must be nonempty and unique')
        for name in self.path:
            identifier(name)


@dataclass(frozen=True)
class Return:
    separator: tuple[str, ...]

    def __post_init__(self):
        object.__setattr__(self, 'separator', tuple(self.separator))
        if tuple(sorted(set(self.separator))) != self.separator:
            raise ProtocolError('Separator must be sorted and unique')
        for name in self.separator:
            identifier(name)


@dataclass(frozen=True)
class Seen:
    pass


@dataclass(frozen=True)
class Message:
    run_id: str
    sender: str
    recipient: str
    sequence: int
    kind: Kind
    payload: Explore | Return | Seen | Factor | Assignment

    def __post_init__(self):
        for name in (self.run_id, self.sender, self.recipient):
            identifier(name)
        if self.sender == self.recipient:
            raise ProtocolError('Self-messages are not permitted')
        if type(self.sequence) is not int or self.sequence < 0:
            raise ProtocolError('Sequence must be a nonnegative integer')
        expected = {Kind.EXPLORE: Explore, Kind.RETURN: Return, Kind.SEEN: Seen,
                    Kind.UTIL: Factor, Kind.VALUE: Assignment}
        if not isinstance(self.kind, Kind) or not isinstance(self.payload, expected[self.kind]):
            raise ProtocolError('Message kind and payload disagree')
        if self.kind == Kind.EXPLORE and self.payload.path[-1] != self.sender:
            raise ProtocolError('DFS path must end at sender')


class MessagePort(Protocol):
    def send(self, message: Message) -> None: ...


class QueueTransport:
    """FIFO delivery, no loss/retries; trace contains delivered messages only.

    The adapter routes messages. It neither computes the tree nor exposes agent state.
    Agents receive only its send port, not a registry of peers.
    """

    def __init__(self, run_id: str):
        identifier(run_id)
        self.run_id = run_id
        self._receivers: dict[str, Callable[[Message], None]] = {}
        self._queue = deque()
        self._seen = set()
        self._trace = []

    def register(self, name: str, receive: Callable[[Message], None]):
        identifier(name)
        if name in self._receivers:
            raise ProtocolError('Duplicate endpoint')
        self._receivers[name] = receive

    def send(self, message: Message):
        if message.run_id != self.run_id:
            raise ProtocolError('Cross-run message')
        if message.sender not in self._receivers or message.recipient not in self._receivers:
            raise ProtocolError('Unknown endpoint')
        key = (message.sender, message.sequence)
        if key in self._seen:
            raise ProtocolError('Duplicate message')
        self._seen.add(key)
        self._queue.append(message)

    @property
    def trace(self):
        return tuple(self._trace)

    def drain(self):
        while self._queue:
            message = self._queue.popleft()
            self._receivers[message.recipient](message)
            self._trace.append(message)


@dataclass(frozen=True)
class SendPort:
    """Narrow transport capability; no receive registry or trace on the agent interface."""

    send: Callable[[Message], None]
