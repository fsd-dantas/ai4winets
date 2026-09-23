"""A finite, deterministic reference world: FIFO byte-service queues and obligations.

This is the logical reference model of docs/ECoRA/v1-scope.md, not an LTE emulator and
not ns-3. It represents transport as deterministic byte-service FIFO queues with explicit
propagation and finite limits, so that contracts, coordination and replay can be exercised
before a network simulator exists. It has no radio, no protocol conformance, no PHY or MAC
behaviour, and no calibrated value.

SCADA is a transaction, as v1-scope defines it. The central application sends a request
down the site's selected leg, the site answers after its processing delay, and the
response comes back up. The obligation is the transaction: it completes when the response
arrives centrally, and its deadline runs from the request's generation across both
directions. A request or a response lost on the way loses the transaction. AMI readings
are one-way from the site.

Every leg and the egress have two directions, each its own FIFO queue at the same rate,
because a request and a response do not wait behind each other. A disturbance changes both
directions of a leg together. An LTE leg is interpreted here through its declared logical
capacity and its declared rate table, which maps extra loss and cell load to a rate. The
leg keeps both of its current conditions: a radio loss changes one, a cell load the other,
and the rate follows from the pair. Lookup takes the largest declared load not above the
current one, then within it the largest declared loss not above the current one, so between
measured points the rate is the more favourable neighbour's. The table is this model's
interpretation of the simulator, measured where its `calibration` says so.

Declared simplifications, each of which bounds what a run of this model can support:

- The UDP envelope and gateway processing delay are not represented; the simulator counts
  both, so byte and delay figures from the two worlds are not directly comparable.
- Service already in progress when a disturbance changes a link rate completes at its
  scheduled time; the new rate applies to subsequent services only. A release interval
  already being counted behaves the same way when the pacing profile changes.
- Pacing is a release gate at the gateway, not a service rate. A held reading waits
  outside the queue, so it does not occupy the server ahead of SCADA traffic.
- A packet is served whole. There is no fragmentation, no interleaving and no preemption.
- Propagation is a fixed per-link delay. There is no jitter, loss model or reordering
  beyond what queueing produces.
- Events at equal timestamps are ordered by a monotonic sequence number, so a run is
  reproducible without depending on dictionary or heap tie-breaking.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import heapq

from .contracts import Record, require

SERVICES = ("scada", "ami")
PACING_BPS = {"normal": 64000, "restricted": 16000, "minimum": 4096}
# Path probes, the v1 register's values and the simulator's: every 0.2 s on each leg, a
# 32-byte datagram echoed at the far end of the leg, lost if not answered within 0.15 s,
# and evidence for 0.5 s after its answer. Probes are traffic: they wait in the leg's
# queues behind whatever is there, and they consume its service.
PROBE_PERIOD_S = 0.2
PROBE_BYTES = 32
PROBE_TIMEOUT_S = 0.15
PROBE_VALIDITY_S = 0.5
PROBE_START_S = 0.2
# Delivery summaries, the v1 register's delivery_summary_delay_s: the centre reports what
# it received to each site, and the report takes this long to arrive.
DELIVERY_SUMMARY_DELAY_S = 0.010


@dataclass(frozen=True)
class Link:
    """One directed byte-service FIFO queue with a finite limit."""

    link_id: str
    capacity_bps: float
    delay_s: float
    queue_limit_bytes: int


@dataclass
class _Queue:
    link: Link
    rate_bps: float
    pending: deque = field(default_factory=deque)
    occupied_bytes: int = 0
    busy: bool = False
    served_bytes: int = 0
    dropped: int = 0
    # Instrumentation, kept by the queue itself so it is independent of any ledger: per
    # service, what arrived, what began transmission, what was dropped, and how long each
    # waited; and the byte occupancy integrated over time.
    by_service: dict = field(default_factory=dict)
    arrived_at: dict = field(default_factory=dict)
    area_byte_s: float = 0.0
    changed_s: float = 0.0
    peak_bytes: int = 0

    def service_stats(self, service):
        return self.by_service.setdefault(service, {
            "arrivals": 0, "departures": 0, "drops": 0, "bytes_arrived": 0,
            "delay_total_s": 0.0, "delay_max_s": 0.0})

    def occupy(self, delta, now):
        self.area_byte_s += self.occupied_bytes * (now - self.changed_s)
        self.changed_s = now
        self.occupied_bytes += delta
        self.peak_bytes = max(self.peak_bytes, self.occupied_bytes)

    def report(self, now):
        area = self.area_byte_s + self.occupied_bytes * (now - self.changed_s)
        services = {}
        for service, stats in sorted(self.by_service.items()):
            departed = stats["departures"]
            services[service] = {
                "arrivals": stats["arrivals"], "departures": departed, "drops": stats["drops"],
                "bytes_arrived": stats["bytes_arrived"],
                "delay_mean_s": stats["delay_total_s"] / departed if departed else None,
                "delay_max_s": stats["delay_max_s"] if departed else None}
        return {"capacity_bps": self.link.capacity_bps, "rate_bps": self.rate_bps,
                "queue_limit_bytes": self.link.queue_limit_bytes,
                "occupancy_mean_bytes": area / now if now > 0 else 0.0,
                "occupancy_peak_bytes": self.peak_bytes, "held_bytes": self.occupied_bytes,
                "by_service": services}


@dataclass(frozen=True)
class Packet:
    """One datagram. `route` is the queues it crosses, fixed when it is released."""

    packet_id: str
    service: str
    site_id: str
    size_bytes: int
    generated_s: float
    deadline_s: float
    route: tuple
    kind: str = "reading"
    obligation_id: str = ""


DIRECTIONS = ("up", "down")
EGRESS = ("egress", "egress")


class FiniteModel:
    """Discrete-event reference world. Deterministic: no random draw is taken."""

    def __init__(self, *, sites, links, egress, scada_period_s, ami_period_s,
                 scada_bytes, ami_bytes, scada_deadline_s, ami_deadline_s,
                 initial_path="lte", initial_pacing="normal", disturbances=(),
                 scada_request_bytes=128, scada_processing_delay_s=0.001, rate_tables=None,
                 leg_specs=None):
        require(sites, "the model needs at least one site")
        require(set(links) >= {"lte", "alternative"}, "both legs must be declared")
        self.sites = tuple(sites)
        self.links = dict(links)
        self.egress = egress
        self.periods = {"scada": scada_period_s, "ami": ami_period_s}
        # For SCADA this is the response; the request has its own size.
        self.sizes = {"scada": scada_bytes, "ami": ami_bytes}
        self.request_bytes = scada_request_bytes
        self.processing_delay_s = scada_processing_delay_s
        self.deadlines = {"scada": scada_deadline_s, "ami": ami_deadline_s}
        # Per leg, (extra_loss_db, competing_ues, capacity_bps). A leg without one cannot
        # take a radio impairment or a cell load, because nothing says what either would mean.
        self.rate_tables = {leg: tuple(sorted(tuple(entry) for entry in table))
                            for leg, table in (rate_tables or {}).items()}
        self._conditions = {}
        # What each disturbance did, as the queues read back afterwards. The harness's
        # evidence that an impairment or restoration took effect; no controller port reads it.
        self._impairments = []
        self.leg_specs = dict(leg_specs or {})
        self.path = {site: initial_path for site in self.sites}
        self.pacing = {site: initial_pacing for site in self.sites}
        self.path_version = {site: 0 for site in self.sites}
        self.pacing_version = {site: 0 for site in self.sites}
        self.now = 0.0
        self._sequence = 0
        self._calendar = []
        self._queues = {}
        for site in self.sites:
            for leg, link in self.links.items():
                for direction in DIRECTIONS:
                    self._queues[(site, leg, direction)] = _Queue(link, link.capacity_bps)
        for direction in DIRECTIONS:
            self._queues[(*EGRESS, direction)] = _Queue(egress, egress.capacity_bps)
        self._obligations = {}
        self._ami_pending = {site: deque() for site in self.sites}
        self._ami_releasing = {site: False for site in self.sites}
        self.generated, self.delivered, self.dropped = [], [], []
        self._counter = 0
        for service in SERVICES:
            self._schedule(0.0, "generate", {"service": service, "site": self.sites[0]}
                           if len(self.sites) == 1 else {"service": service, "site": self.sites[0]})
            for site in self.sites[1:]:
                self._schedule(0.0, "generate", {"service": service, "site": site})
        # Kept, not only scheduled: a model asked to describe itself has to be able to
        # report the disturbances it will apply, or the description understates the world.
        self.disturbances = tuple(dict(d) for d in disturbances)
        self._probes = {}
        for site in self.sites:
            for leg in self.links:
                self._probes[(site, leg)] = {"sent": {}, "completed_s": None, "rtt_s": None,
                                             "answered": 0, "timed_out": 0}
                self._schedule(PROBE_START_S, "probe", {"site": site, "leg": leg})
        for disturbance in self.disturbances:
            self._schedule(disturbance["at_s"], "disturb", disturbance)

    # -- event calendar -------------------------------------------------------

    def _schedule(self, time_s, kind, data):
        require(time_s >= self.now, "an event cannot be scheduled into the past")
        self._sequence += 1
        heapq.heappush(self._calendar, (time_s, self._sequence, kind, data))

    def advance_to(self, time_s):
        """Run every event up to and including time_s, in deterministic order."""
        require(time_s >= self.now, "the model clock cannot move backwards")
        while self._calendar and self._calendar[0][0] <= time_s:
            at, _, kind, data = heapq.heappop(self._calendar)
            self.now = at
            getattr(self, f"_on_{kind}")(data)
        self.now = time_s
        return self

    def _uplink(self, site):
        """The route up from a site, over the leg selected at the moment of release."""
        return ((site, self.path[site], "up"), (*EGRESS, "up"))

    def _on_generate(self, data):
        service, site = data["service"], data["site"]
        self._counter += 1
        identity = f"packet:{service}:{site}:{self._counter}"
        deadline = self.now + self.deadlines[service]
        if service == "scada":
            # The central application sends the request over the site's selected leg,
            # chosen now: a request already released keeps its leg if the site switches.
            packet = Packet(identity, service, site, self.request_bytes, self.now, deadline,
                            ((*EGRESS, "down"), (site, self.path[site], "down")),
                            "request", identity)
            self._obligations[identity] = packet
            self.generated.append(packet)
            self._arrive(packet, 0)
        else:
            packet = Packet(identity, service, site, self.sizes[service], self.now, deadline,
                            (), "reading", identity)
            self._obligations[identity] = packet
            self.generated.append(packet)
            # Pacing governs release from the gateway, not the rate a released packet is
            # served at. Slowing the service instead would leave a paced reading at the
            # head of a shared queue holding SCADA up behind it, which is the opposite of
            # what the lever is for.
            self._ami_pending[site].append(packet)
            if not self._ami_releasing[site]:
                self._start_release(site)
        self._schedule(self.now + self.periods[service], "generate", data)

    def _on_respond(self, data):
        """The site answers a request it received, over its leg selected now."""
        request = data["packet"]
        response = Packet(f"{request.packet_id}:response", "scada", request.site_id,
                          self.sizes["scada"], request.generated_s, request.deadline_s,
                          self._uplink(request.site_id), "response", request.obligation_id)
        self._arrive(response, 0)

    def _start_release(self, site):
        """Admit the next held reading after its profile's interval has elapsed."""
        pending = self._ami_pending[site]
        if not pending:
            self._ami_releasing[site] = False
            return
        self._ami_releasing[site] = True
        rate = PACING_BPS[self.pacing[site]]
        self._schedule(self.now + (pending[0].size_bytes * 8) / rate, "release", {"site": site})

    def _on_release(self, data):
        site = data["site"]
        reading = self._ami_pending[site].popleft()
        # The leg is chosen at release, not at generation: a held reading goes out on
        # whatever the site selects when the gate opens.
        self._arrive(Packet(reading.packet_id, reading.service, site, reading.size_bytes,
                            reading.generated_s, reading.deadline_s, self._uplink(site),
                            "reading", reading.obligation_id), 0)
        self._ami_releasing[site] = False
        self._start_release(site)

    def lookup(self, leg, loss_db, competing_ues):
        """The rate a leg's table gives for this loss and load."""
        table = self.rate_tables.get(leg)
        require(table, f"leg {leg} declares no rate table to interpret a radio condition")
        level = max(c for _, c, _ in table if c <= competing_ues)
        return max((entry for entry in table if entry[1] == level and entry[0] <= loss_db),
                   key=lambda entry: entry[0])[2]

    def rate_for(self, disturbance):
        """The service rate a disturbance leaves its leg at, given the leg's other condition.

        A rate change sets a point-to-point leg directly. A radio loss or a cell load changes
        one of the LTE leg's two conditions and keeps the other.
        """
        kind = disturbance.get("kind", "rate")
        if kind == "rate":
            return disturbance["rate_bps"]
        key = (disturbance["site"], disturbance["leg"])
        conditions = dict(self._conditions.get(key, {"extra_loss_db": 0, "competing_ues": 0}))
        field = "extra_loss_db" if kind == "radio_loss" else "competing_ues"
        conditions[field] = disturbance[field]
        return self.lookup(disturbance["leg"], conditions["extra_loss_db"],
                           conditions["competing_ues"])

    def _on_disturb(self, data):
        """Change a leg's rate in both directions. In-flight service is unaffected."""
        rate = self.rate_for(data)
        kind = data.get("kind", "rate")
        if kind != "rate":
            key = (data["site"], data["leg"])
            conditions = self._conditions.setdefault(key, {"extra_loss_db": 0, "competing_ues": 0})
            field = "extra_loss_db" if kind == "radio_loss" else "competing_ues"
            conditions[field] = data[field]
        for direction in DIRECTIONS:
            key = (data["site"], data["leg"], direction)
            queue = self._queues[key]
            was_idle = queue.rate_bps <= 0
            queue.rate_bps = rate
            # A leg taken to zero stops serving and holds its queue. Restoring it has to
            # wake that queue, or the backlog would sit with nothing to drain it.
            if was_idle and queue.rate_bps > 0 and queue.pending and not queue.busy:
                self._start_service(key)
        if kind == "rate":
            served = {self._queues[(data["site"], data["leg"], d)].rate_bps for d in DIRECTIONS}
            condition = {"rate_bps": served.pop() if len(served) == 1 else None}
        else:
            condition = dict(self._conditions[(data["site"], data["leg"])])
        self._impairments.append({**data, "applied_at_s": self.now, "condition": condition})

    def impairments(self):
        """Every disturbance applied so far, when, and the leg condition it left.

        Harness evidence, held apart from controller authority: the action catalog cannot
        reach a leg's condition, and no observation or truth projection exports this ledger.
        """
        return [dict(entry, condition=dict(entry["condition"])) for entry in self._impairments]

    def _arrive(self, packet, hop):
        key = packet.route[hop]
        queue = self._queues[key]
        stats = queue.service_stats(packet.service)
        stats["arrivals"] += 1
        stats["bytes_arrived"] += packet.size_bytes
        if queue.occupied_bytes + packet.size_bytes > queue.link.queue_limit_bytes:
            queue.dropped += 1
            stats["drops"] += 1
            # A lost probe shows up as its timeout, never as an obligation lost.
            if packet.kind not in ("probe", "probe_echo"):
                self.dropped.append((self._obligations[packet.obligation_id], self.now,
                                     "queue_overflow"))
            return
        queue.occupy(packet.size_bytes, self.now)
        queue.arrived_at[packet.packet_id] = self.now
        queue.pending.append((packet, hop))
        if not queue.busy:
            self._start_service(key)

    def _start_service(self, key):
        queue = self._queues[key]
        if not queue.pending:
            queue.busy = False
            return
        packet, hop = queue.pending[0]
        rate = queue.rate_bps
        if rate <= 0:
            # No service to give. The packet waits; it is not dropped and not delivered.
            queue.busy = False
            return
        queue.busy = True
        # Queueing delay ends where transmission starts, as it does at an ns-3 device.
        stats = queue.service_stats(packet.service)
        waited = self.now - queue.arrived_at.pop(packet.packet_id)
        stats["departures"] += 1
        stats["delay_total_s"] += waited
        stats["delay_max_s"] = max(stats["delay_max_s"], waited)
        self._schedule(self.now + (packet.size_bytes * 8) / rate, "serviced",
                       {"key": key, "packet_id": packet.packet_id})

    def _on_serviced(self, data):
        queue = self._queues[data["key"]]
        packet, hop = queue.pending.popleft()
        queue.occupy(-packet.size_bytes, self.now)
        queue.served_bytes += packet.size_bytes
        arrival = self.now + queue.link.delay_s
        if hop + 1 < len(packet.route):
            self._schedule(arrival, "hop", {"packet": packet, "hop": hop + 1})
        elif packet.kind == "probe":
            self._schedule(arrival, "echo", {"packet": packet})
        elif packet.kind == "probe_echo":
            self._schedule(arrival, "answered", {"packet": packet})
        elif packet.kind == "request":
            self._schedule(arrival + self.processing_delay_s, "respond", {"packet": packet})
        else:
            self._schedule(arrival, "deliver", {"packet": packet})
        queue.busy = False
        self._start_service(data["key"])

    def _on_hop(self, data):
        self._arrive(data["packet"], data["hop"])

    def _on_probe(self, data):
        """Send one probe up the leg, and schedule the next."""
        site, leg = data["site"], data["leg"]
        self._counter += 1
        identity = f"probe:{site}:{leg}:{self._counter}"
        self._probes[(site, leg)]["sent"][identity] = self.now
        self._arrive(Packet(identity, "probe", site, PROBE_BYTES, self.now,
                            self.now + PROBE_TIMEOUT_S, ((site, leg, "up"),), "probe"), 0)
        self._schedule(self.now + PROBE_PERIOD_S, "probe", data)

    def _on_echo(self, data):
        """The far end of the leg answers over the same leg."""
        probe = data["packet"]
        leg = probe.route[0][1]
        self._arrive(Packet(probe.packet_id, "probe", probe.site_id, PROBE_BYTES,
                            probe.generated_s, probe.deadline_s,
                            ((probe.site_id, leg, "down"),), "probe_echo"), 0)

    def _on_answered(self, data):
        """An answer within the timeout is evidence; a later one is a lost probe."""
        echo = data["packet"]
        record = self._probes[(echo.site_id, echo.route[0][1])]
        sent = record["sent"].pop(echo.packet_id, None)
        if sent is None:
            return
        round_trip = self.now - sent
        if round_trip <= PROBE_TIMEOUT_S:
            record.update(completed_s=self.now, rtt_s=round_trip)
            record["answered"] += 1
        else:
            record["timed_out"] += 1

    def _on_deliver(self, data):
        # Delivery completes the obligation: a reading, or a transaction whose response
        # arrived. Exactly at the deadline is on time.
        obligation = self._obligations[data["packet"].obligation_id]
        self.delivered.append((obligation, self.now, self.now <= obligation.deadline_s))

    # -- actuation ------------------------------------------------------------

    def apply(self, command):
        """Apply an admitted ActionCommand. Returns (applied, reason)."""
        data = command.data if isinstance(command, Record) else command
        operator, target = data["operator"], data["target"]
        if operator == "no_op":
            return False, "no_op"
        if target not in self.sites:
            return False, "unknown_target"
        if operator in ("select_path", "set_ami_pacing"):
            # Compare-and-swap on the actuator's version: a write names the state it was
            # decided against, and a write decided against an older state is refused.
            expected = data.get("expected_state_version")
            current = (self.path_version if operator == "select_path" else self.pacing_version)[target]
            if expected is None:
                return False, "missing_version"
            if expected != current:
                return False, "stale_version"
        if operator == "select_path":
            path = data["arguments"]["path"]
            if path not in self.links:
                return False, "unknown_path"
            # Packets already queued keep their leg; there is no migration or duplication.
            self.path[target] = path
            self.path_version[target] += 1
            return True, None
        if operator == "set_ami_pacing":
            profile = data["arguments"]["profile"]
            if profile not in PACING_BPS:
                return False, "unknown_profile"
            self.pacing[target] = profile
            self.pacing_version[target] += 1
            return True, None
        return False, "unsupported_operator"

    def actuator_state(self):
        """The gateway actuators' readback: selected path, pacing and their versions.

        What a receipt may cite as the resulting state. It is what the actuators report
        about themselves, the same as their path and pacing observations, not model truth.
        """
        return {"selected_path": dict(self.path), "pacing": dict(self.pacing),
                "path_version": dict(self.path_version),
                "pacing_version": dict(self.pacing_version)}

    # -- observation ----------------------------------------------------------

    def probe_evidence(self, site, leg):
        """The latest acknowledged probe on this leg, if still valid: (sent_s, completed_s, rtt_s).

        Viability is established by a probe that came back, never by the configured link
        parameters. A probe waits behind the leg's own traffic, so a backlogged leg can fail
        to answer in time even while it still carries data, and an answer remains evidence
        for its validity after the leg has changed. Both are what a real probe does.
        """
        record = self._probes[(site, leg)]
        completed = record["completed_s"]
        if completed is None or self.now - completed > PROBE_VALIDITY_S:
            return None
        return completed - record["rtt_s"], completed, record["rtt_s"]

    def probe(self, site, leg):
        """The latest valid probe round trip on this leg, or None when there is none."""
        evidence = self.probe_evidence(site, leg)
        return None if evidence is None else evidence[2]

    @staticmethod
    def observation_id(site, metric, at_s):
        """The canonical identity of an exported signal.

        The exporter and an actuator receipt citing applied evidence derive the identity
        here rather than each formatting its own string, so a receipt cannot reference an
        observation the run will never export.
        """
        return f"observation:{site}:{metric}:{at_s}"

    def observations(self, *, capability_ids, window_s=1.0):
        """Export the declared observable signals. Truth predicates are not included."""
        start = max(0.0, self.now - window_s)
        window = {"start_s": start, "end_s": self.now}
        exported = []
        for site in self.sites:
            # The local queue an agent sees is its uplink on the selected leg.
            key = (site, self.path[site], "up")
            capability = capability_ids.get((site, "queue_occupancy"))
            if capability:
                exported.append(self._observation(
                    self.observation_id(site, "queue_occupancy", self.now), site, "ami",
                    "queue_occupancy", "byte", self._queues[key].occupied_bytes, capability, window))
            capability = capability_ids.get((site, "path_state"))
            if capability:
                exported.append(self._observation(
                    self.observation_id(site, "path_state", self.now), site, "shared",
                    "path_state", "id", self.path[site], capability, window))
            capability = capability_ids.get((site, "pacing_profile"))
            if capability:
                exported.append(self._observation(
                    self.observation_id(site, "pacing_profile", self.now), site, "ami",
                    "pacing_profile", "id", self.pacing[site], capability, window))
            # Each actuator's version, its own subject: what a write must name.
            for actuator, versions in (("selected_path", self.path_version),
                                       ("pacing_profile", self.pacing_version)):
                capability = capability_ids.get((f"{site}/{actuator}", "actuator_version"))
                if capability:
                    exported.append(self._observation(
                        self.observation_id(f"{site}/{actuator}", "actuator_version", self.now),
                        f"{site}/{actuator}", "shared" if actuator == "selected_path" else "ami",
                        "actuator_version", "count", versions[site], capability, window))
            capability = capability_ids.get((site, "scada_response"))
            if capability:
                exported.append(self._scada_response(site, capability, window_s))
            # A probe per leg, each its own subject so each needs its own permission:
            # being allowed to probe one leg is not permission to probe the other.
            for leg in self.links:
                capability = capability_ids.get((f"{site}/{leg}", "path_probe"))
                if not capability:
                    continue
                evidence = self.probe_evidence(site, leg)
                observation = self._observation(
                    self.observation_id(f"{site}/{leg}", "path_probe", self.now),
                    f"{site}/{leg}", "shared", "path_probe", "s",
                    None if evidence is None else evidence[2], capability, window)
                observation["sampling_policy"] = "latest_acknowledged_probe"
                if evidence is None:
                    observation.update({"quality": "missing", "missing_reason": {
                        "code": "probe_timeout",
                        "detail": "No probe on this leg was acknowledged within its validity."}})
                else:
                    # The evidence is the probe's own round trip, observed when it answered.
                    sent, completed, _ = evidence
                    observation.update(event_time_s=completed, available_at_s=completed,
                                       window={"start_s": sent, "end_s": completed})
                exported.append(observation)
        return exported

    def _scada_response(self, site, capability, window_s):
        """The delivery summary as an observation: mean response of what completed, or none."""
        start, end, times = self.delivery_summary(site, window_s)
        observation = self._observation(
            self.observation_id(site, "scada_response", self.now), site, "scada",
            "scada_response", "s", sum(times) / len(times) if times else None, capability,
            {"start_s": start, "end_s": end})
        observation.update(
            event_time_s=end, sampling_policy="delivery_summary_mean",
            assumptions=[f"Mean response time of {len(times)} SCADA transactions the centre "
                         f"completed in the window, reported {DELIVERY_SUMMARY_DELAY_S} s later."])
        if not times:
            # No completion is not a fast response. It is no evidence about response time.
            observation.update(quality="missing", missing_reason={
                "code": "no_completion",
                "detail": "No SCADA transaction completed in the summarised window."})
        return observation

    def current_scada_response(self, site, window_s=0.5):
        """Truth, not evidence: the mean response over the last window ending now.

        What the site's summary will say once it arrives. Only a privileged reference may
        read it; the undelayed value is exactly what no controller has.
        """
        times = [at - obligation.generated_s for obligation, at, _ in self.delivered
                 if obligation.service == "scada" and obligation.site_id == site
                 and self.now - window_s < at <= self.now]
        return sum(times) / len(times) if times else None

    def delivery_summary(self, site, window_s):
        """SCADA transactions the centre completed for this site in the summarised window.

        The summary describes the window ending one summary delay ago, because that is the
        newest a site can know: the centre's report is still on its way for anything later.
        Returns (window_start, window_end, response times of the completions in it).
        """
        end = max(0.0, self.now - DELIVERY_SUMMARY_DELAY_S)
        start = max(0.0, end - window_s)
        times = [at - obligation.generated_s for obligation, at, _ in self.delivered
                 if obligation.service == "scada" and obligation.site_id == site
                 and start < at <= end]
        return start, end, times

    def _observation(self, observation_id, site, service, metric, unit, value, capability, window):
        return {"observation_id": observation_id, "subject": site, "service": service,
                "metric": metric, "unit": unit, "value": value, "quality": "observed",
                "missing_reason": None, "event_time_s": self.now, "available_at_s": self.now,
                "window": window, "source": "finite.reference.model",
                "sampling_policy": "instantaneous", "valid_min": None, "valid_max": None,
                "assumptions": ["Finite reference model; no radio, protocol or calibration."],
                "evidence_kind": "measured", "capability_id": capability,
                "source_observation_ids": [], "formula": None, "privileged_source_refs": []}

    def truth(self):
        """Current model truth, for privileged references only. Never ordinary input."""
        return {"time_s": self.now,
                "selected_path": dict(self.path), "pacing": dict(self.pacing),
                "queue_bytes": {f"{site}/{leg}": q.occupied_bytes
                                for (site, leg, direction), q in self._queues.items()
                                if site != "egress" and direction == "up"},
                "queue_bytes_down": {f"{site}/{leg}": q.occupied_bytes
                                     for (site, leg, direction), q in self._queues.items()
                                     if site != "egress" and direction == "down"},
                "egress_bytes": self._queues[(*EGRESS, "up")].occupied_bytes,
                "egress_bytes_down": self._queues[(*EGRESS, "down")].occupied_bytes,
                "held_ami": {site: len(pending) for site, pending in self._ami_pending.items()},
                "generated": len(self.generated), "delivered": len(self.delivered),
                "dropped": len(self.dropped)}

    def queues(self):
        """Every queue's instrumentation, named `egress/<direction>` or `<site>/<leg>/<direction>`.

        Evaluator evidence, like the cohorts: it describes where traffic waited, and no
        controller reads it.
        """
        return {("egress/" + direction if site == "egress" else f"{site}/{leg}/{direction}"):
                queue.report(self.now)
                for (site, leg, direction), queue in sorted(self._queues.items())}

    def cohorts(self, cohort_specs):
        """Measured counts for the study's frozen cohort specifications."""
        result = []
        for spec in cohort_specs:
            start, end = spec["generation_window"]["start_s"], spec["generation_window"]["end_s"]
            cohort = [p for p in self.generated
                      if p.service == spec["service"] and start <= p.generated_s <= end]
            identities = {p.packet_id for p in cohort}
            on_time = sum(1 for p, _, ok in self.delivered if p.packet_id in identities and ok)
            late = sum(1 for p, _, ok in self.delivered if p.packet_id in identities and not ok)
            lost = sum(1 for p, _, _ in self.dropped if p.packet_id in identities)
            # Censoring is a fact about the run, not a blanket disclaimer. A cohort is
            # right-censored when the clock stopped before an outstanding obligation's
            # deadline had elapsed: the outcome is unknown rather than a loss. Marking
            # every cohort censored told a reader nothing, and marking none would count
            # an undecided obligation as failed.
            outstanding = [p for p in cohort
                           if p.packet_id not in {d.packet_id for d, _, _ in self.delivered}
                           and p.packet_id not in {d.packet_id for d, _, _ in self.dropped}]
            censored = any(p.deadline_s > self.now for p in outstanding)
            result.append({**spec, "generated": len(cohort), "delivered_on_time": on_time,
                           "delivered_late": late, "lost": lost,
                           "pending": len(cohort) - on_time - late - lost,
                           "duplicate_deliveries": 0, "censored": censored})
        return result
