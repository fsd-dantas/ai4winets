// The ECoRA simulator process: one scenario, one ns-3 world, driven one request at a time.
//
// It speaks the protocol in system/simulator-adapter.md over standard input and output:
// each frame is a four-byte big-endian length followed by that many bytes of UTF-8 JSON.
// It never writes anything else to standard output and never initiates a message.
//
// Implemented here: configure, advance, cohorts. The requests that belong to later work
// (observe, apply, truth, fork) are refused with a reason rather than approximated, because
// a refusal is a result and an approximation would be a claim.
//
// What configure builds, from the scenario and nothing else:
//
//   central application --egress (point-to-point, DropTail)-- central gateway
//   central gateway --internal wired link-- PGW / EPC -- eNB ~~ LTE radio ~~ site gateway (UE)
//   central gateway --alternative leg (point-to-point, DropTail, RateErrorModel)-- site gateway
//
// SCADA is a transaction: the central application sends a request to the site over the
// site's selected leg, the site answers after its processing delay over the leg selected
// then, and the transaction completes when the response reaches the application. AMI
// readings are generated at the site and released through a pacing gate onto the selected
// leg. Every datagram carries a 32-byte envelope with its obligation's identity, and every
// obligation is kept in a ledger that the cohorts request scores.

#include "build-id.h"
#include "json.hpp"
#include "lte-leg.h"

#include "ns3/applications-module.h"
#include "ns3/core-module.h"
#include "ns3/internet-module.h"
#include "ns3/lte-module.h"
#include "ns3/mobility-module.h"
#include "ns3/network-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/traffic-control-module.h"

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <deque>
#include <functional>
#include <iostream>
#include <memory>
#include <map>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

using namespace ns3;
using json = nlohmann::json;

namespace
{

// Declared constants. The pacing profiles are the same table the finite world uses; the
// configure response reports them so the adapter can check the two agree.
const std::map<std::string, double> PACING_BPS = {{"normal", 64000},
                                                  {"restricted", 16000},
                                                  {"minimum", 4096}};
const uint32_t ENVELOPE_BYTES = 32;
const uint16_t SITE_PORT = 5000;
const uint16_t CENTRAL_PORT = 6000;
// Path probes, from the v1 parameter register: each site probes each leg every 0.2 s with a
// 32-byte datagram that the central gateway echoes back over the same leg. A probe not
// answered within 0.15 s is lost, and an acknowledgement is evidence for 0.5 s. Probes are
// real traffic: they use each leg in both directions and consume its service.
const uint16_t PROBE_PORT = 5100;
const double PROBE_PERIOD_S = 0.2;
const uint32_t PROBE_BYTES = 32;
const double PROBE_TIMEOUT_S = 0.15;
const double PROBE_VALIDITY_S = 0.5;
const double PROBE_START_S = 0.2;
// Delivery summaries, the v1 register's delivery_summary_delay_s: the centre reports what it
// received to each site, and the report takes this long to arrive.
const double DELIVERY_SUMMARY_DELAY_S = 0.010;
const char* INTERNAL_RATE = "100Mbps";
const double INTERNAL_DELAY_S = 0.001;

// A refusal carries a code and a reason, and is returned rather than thrown past main.
struct Refusal : std::runtime_error
{
    std::string code;

    Refusal(std::string c, const std::string& detail)
        : std::runtime_error(detail),
          code(std::move(c))
    {
    }
};

void
Require(bool condition, const std::string& code, const std::string& detail)
{
    if (!condition)
    {
        throw Refusal(code, detail);
    }
}

// -- obligation identity carried with every datagram ------------------------------------

enum Kind : uint8_t
{
    REQUEST = 1,
    RESPONSE = 2,
    READING = 3,
    PROBE = 4
};

class ObligationTag : public Tag
{
  public:
    uint64_t id = 0;
    uint8_t kind = 0;

    static TypeId GetTypeId()
    {
        static TypeId tid = TypeId("ns3::EcoraObligationTag")
                                .SetParent<Tag>()
                                .AddConstructor<ObligationTag>();
        return tid;
    }

    TypeId GetInstanceTypeId() const override
    {
        return GetTypeId();
    }

    uint32_t GetSerializedSize() const override
    {
        return 9;
    }

    void Serialize(TagBuffer buffer) const override
    {
        buffer.WriteU64(id);
        buffer.WriteU8(kind);
    }

    void Deserialize(TagBuffer buffer) override
    {
        id = buffer.ReadU64();
        kind = buffer.ReadU8();
    }

    void Print(std::ostream& os) const override
    {
        os << "obligation=" << id << " kind=" << int(kind);
    }
};

// Independent instrumentation of one device queue: per service, what arrived, what began
// transmission, what was dropped and how long each waited, and the byte occupancy over time.
// It reads the queue's own traces and the identity on each datagram, and nothing else.
class QueueProbe
{
  public:
    using Classify = std::function<std::string(Ptr<const Packet>)>;

    QueueProbe(Ptr<Queue<Packet>> queue, uint64_t capacityBps, Classify classify)
        : m_queue(queue),
          m_capacityBps(capacityBps),
          m_classify(std::move(classify))
    {
        queue->TraceConnectWithoutContext("Enqueue", MakeCallback(&QueueProbe::Enqueued, this));
        queue->TraceConnectWithoutContext("Dequeue", MakeCallback(&QueueProbe::Dequeued, this));
        queue->TraceConnectWithoutContext("Drop", MakeCallback(&QueueProbe::Dropped, this));
    }

    json Report() const
    {
        double now = Simulator::Now().GetSeconds();
        double area = m_area + m_bytes * (now - m_changed);
        json services = json::object();
        for (const auto& [service, s] : m_services)
        {
            services[service] = {{"arrivals", s.arrivals},
                                 {"departures", s.departures},
                                 {"drops", s.drops},
                                 {"bytes_arrived", s.bytes},
                                 {"delay_mean_s", s.departures ? json(s.delay / s.departures) : json()},
                                 {"delay_max_s", s.departures ? json(s.delayMax) : json()}};
        }
        QueueSizeValue limit;
        m_queue->GetAttribute("MaxSize", limit);
        return {{"instrumented", true},
                {"capacity_bps", m_capacityBps},
                {"queue_limit_bytes", limit.Get().GetValue()},
                {"occupancy_mean_bytes", now > 0 ? area / now : 0.0},
                {"occupancy_peak_bytes", m_peak},
                {"held_bytes", m_bytes},
                {"by_service", services}};
    }

  private:
    struct Stats
    {
        uint64_t arrivals = 0, departures = 0, drops = 0, bytes = 0;
        double delay = 0, delayMax = 0;
    };

    void Occupy(int64_t delta)
    {
        double now = Simulator::Now().GetSeconds();
        m_area += m_bytes * (now - m_changed);
        m_changed = now;
        m_bytes += delta;
        m_peak = std::max(m_peak, m_bytes);
    }

    void Enqueued(Ptr<const Packet> packet)
    {
        Stats& s = m_services[m_classify(packet)];
        ++s.arrivals;
        s.bytes += packet->GetSize();
        m_entered[packet->GetUid()] = Simulator::Now().GetSeconds();
        Occupy(packet->GetSize());
    }

    void Dequeued(Ptr<const Packet> packet)
    {
        Stats& s = m_services[m_classify(packet)];
        auto entered = m_entered.find(packet->GetUid());
        if (entered != m_entered.end())
        {
            double waited = Simulator::Now().GetSeconds() - entered->second;
            ++s.departures;
            s.delay += waited;
            s.delayMax = std::max(s.delayMax, waited);
            m_entered.erase(entered);
        }
        Occupy(-int64_t(packet->GetSize()));
    }

    void Dropped(Ptr<const Packet> packet)
    {
        // A tail drop never entered the queue: it counts as an arrival and a drop.
        Stats& s = m_services[m_classify(packet)];
        auto entered = m_entered.find(packet->GetUid());
        if (entered != m_entered.end())
        {
            m_entered.erase(entered);
            Occupy(-int64_t(packet->GetSize()));
        }
        else
        {
            ++s.arrivals;
            s.bytes += packet->GetSize();
        }
        ++s.drops;
    }

    Ptr<Queue<Packet>> m_queue;
    uint64_t m_capacityBps;
    Classify m_classify;
    std::map<std::string, Stats> m_services;
    std::map<uint64_t, double> m_entered;
    int64_t m_bytes = 0;
    int64_t m_peak = 0;
    double m_area = 0;
    double m_changed = 0;
};

struct Obligation
{
    uint64_t id;
    std::string service;
    std::string site;
    double generated_s;
    double deadline_s;
    std::optional<double> delivered_s;
    std::optional<std::string> dropped;
};

struct Site
{
    std::string name;
    uint32_t index = 0;
    Ptr<Node> gateway;
    Ptr<NetDevice> lteDevice;
    Ptr<PointToPointNetDevice> altGateway; // the site end of the alternative leg
    Ptr<PointToPointNetDevice> altCentral; // the central end
    Ptr<RateErrorModel> altGatewayLoss;
    Ptr<RateErrorModel> altCentralLoss;
    Ptr<MobilityModel> mobility;
    Ipv4Address lteAddress;
    Ipv4Address altAddress;
    Ptr<Socket> receive;
    Ptr<Socket> sendLte;
    Ptr<Socket> sendAlt;
    std::string path;
    std::string pacing;
    uint64_t pathVersion = 0;
    uint64_t pacingVersion = 0;
    std::deque<uint64_t> held;
    bool releasing = false;
    double extraLossDb = 0;

    // Path probes, per leg: the socket, what is outstanding, and the latest acknowledgement.
    struct Probe
    {
        Ptr<Socket> socket;
        Address echo;
        std::map<uint64_t, double> outstanding;
        double sentS = -1;
        double completedS = -1;
        double rttS = -1;
        uint64_t sent = 0, answered = 0, timedOut = 0;
    };

    std::map<std::string, Probe> probes;

    // The UE's RLC transmission buffer, derived from the flows into and out of it: SDUs the
    // PDCP handed down, SDUs the RLC dropped, and PDUs the RLC handed to the MAC less
    // their fixed header. ns-3 keeps the buffer size private, so this is the observable
    // equivalent of what a UE reports in its buffer status.
    uint64_t rlcAcceptedBytes = 0;
    uint64_t rlcDroppedBytes = 0;
    uint64_t rlcTransmittedBytes = 0;
    uint64_t rlcPdus = 0;
};

// -- the world ---------------------------------------------------------------------------

class World
{
  public:
    json Configure(const json& request);
    json Advance(const json& request);
    json Cohorts(const json& request);
    json Observe(const json& request);
    json Apply(const json& request);
    json ActuatorState() const;

  private:
    void BuildLte(const json& leg);
    void BuildAlternative(const json& leg);
    void BuildEgress(const json& leg);
    void Route();
    void Schedule();
    json Resolved() const;

    void GenerateScada(Site* site);
    void GenerateAmi(Site* site);
    void StartRelease(Site* site);
    void Release(Site* site);
    void Send(Ptr<Socket> socket, Address to, uint64_t id, Kind kind, uint32_t payload);
    void ReceiveAtSite(Ptr<Socket> socket);
    void ReceiveCentrally(Ptr<Socket> socket);
    void Disturb(const json& disturbance);
    void BuildBackground();
    void CompetitorTick(uint32_t index);
    void Dropped(Ptr<const Packet> packet, const std::string& where);
    void WatchBearers();
    Ptr<Socket> SiteSocket(Site* site, const std::string& path) const;
    Address SiteAddress(const Site* site, const std::string& path) const;

    bool m_configured = false;
    json m_scenario;
    json m_scada;
    json m_ami;
    std::string m_initialPath;
    std::string m_initialPacing;
    uint32_t m_rngRun = 1;

    std::vector<Site> m_sites;
    Ptr<Node> m_application;
    Ptr<Node> m_centralGateway;
    Ptr<Node> m_enb;
    Ptr<LteHelper> m_lte;
    Ptr<PointToPointEpcHelper> m_epc;
    Ptr<MatrixPropagationLossModel> m_radioLoss;
    Ptr<NetDevice> m_enbDevice;
    Ipv4Address m_applicationAddress;
    Ptr<Socket> m_applicationReceive;
    Ptr<Socket> m_applicationSend;
    Ptr<PointToPointNetDevice> m_egressCentral;
    Ptr<PointToPointNetDevice> m_egressApplication;

    std::map<uint64_t, Obligation> m_ledger;
    std::vector<uint64_t> m_order;
    uint64_t m_next = 1;
    uint64_t m_untracedDrops = 0;
    uint64_t m_duplicates = 0;
    std::set<void*> m_watchedRlc;
    std::vector<json> m_disturbanceLog;

    // Cell congestion. Competitors are built at configure, as many as the largest load any
    // disturbance declares, and are idle until a cell_load disturbance activates them.
    // Their traffic goes to a background sink beside the EPC, so it contends for the radio
    // and never for the study's egress.
    std::string m_competitorSite;
    uint32_t m_competitorsBuilt = 0;
    std::vector<Ptr<Node>> m_competitorNodes;
    std::vector<Ptr<Socket>> m_competitorSockets;
    std::vector<bool> m_competitorActive;
    std::vector<bool> m_competitorRunning;
    uint32_t m_competingNow = 0;
    Ptr<Node> m_backgroundSink;
    Ptr<Socket> m_backgroundReceive;
    Ipv4Address m_backgroundAddress;
    uint64_t m_backgroundDrops = 0;

    void Instrument();
    std::vector<std::pair<std::string, std::unique_ptr<QueueProbe>>> m_probes;

    void StartProbes();
    void SendProbe(Site* site, std::string leg);
    void ProbeAnswered(Ptr<Socket> socket);
    void EchoProbe(Ptr<Socket> socket);
    json Observation(const Site& site,
                     const std::string& subject,
                     const std::string& metric,
                     const std::string& capability,
                     double windowS) const;
    Ptr<Socket> m_probeEcho;
    uint64_t m_probeSequence = 0;
    uint64_t m_probeDrops = 0;
    std::set<void*> m_watchedFlows;
};

double
Now()
{
    return Simulator::Now().GetSeconds();
}

Time
At(double seconds)
{
    // Whole nanoseconds, so a period added n times lands exactly where n periods do.
    return NanoSeconds(static_cast<int64_t>(std::llround(seconds * 1e9)));
}

std::string
Rate(double bps)
{
    return std::to_string(static_cast<uint64_t>(std::llround(bps))) + "bps";
}

const json&
LegById(const json& topology, const std::string& id)
{
    for (const auto& leg : topology.at("legs"))
    {
        if (leg.at("leg_id") == id)
        {
            return leg;
        }
    }
    throw Refusal("unbuildable_scenario", "the scenario declares no leg " + id);
}

json
World::Configure(const json& request)
{
    Require(!m_configured, "already_configured", "a world is configured once per process");
    m_scenario = request.at("scenario");
    m_rngRun = request.value("rng_run", 1u);
    const json& topology = m_scenario.at("topology");

    // What this world can build. Anything else is refused here, not discovered mid-run.
    const json& lte = LegById(topology, "lte");
    const json& alternative = LegById(topology, "alternative");
    Require(lte.at("kind") == "lte", "unbuildable_scenario", "the lte leg must be an LTE leg");
    Require(alternative.at("kind") == "point_to_point",
            "unbuildable_scenario",
            "the alternative leg must be a point-to-point leg");
    Require(topology.at("legs").size() == 2,
            "unbuildable_scenario",
            "v1 builds exactly the lte and alternative legs");
    for (const auto& flow : m_scenario.at("flows"))
    {
        if (flow.at("service") == "scada")
        {
            Require(flow.at("pattern") == "request_response",
                    "unbuildable_scenario",
                    "SCADA is a request/response transaction");
            m_scada = flow;
        }
        else
        {
            Require(flow.at("pattern") == "periodic",
                    "unbuildable_scenario",
                    "AMI is a periodic reading");
            m_ami = flow;
        }
    }
    Require(!m_scada.is_null() && !m_ami.is_null(),
            "unbuildable_scenario",
            "a flow for each service is required");
    m_initialPath = topology.at("initial_path");
    m_initialPacing = topology.at("initial_pacing");
    Require(PACING_BPS.count(m_initialPacing),
            "unbuildable_scenario",
            "unknown pacing profile " + m_initialPacing);

    // Congestion is declared per disturbance; the competitors it needs are built up front.
    for (const auto& disturbance : m_scenario.at("disturbances"))
    {
        if (disturbance.at("kind") != "cell_load")
        {
            continue;
        }
        uint32_t wanted = disturbance.at("competing_ues");
        Require(wanted <= ecora::MAX_COMPETITORS,
                "unbuildable_scenario",
                "cell load beyond the model's valid range of " +
                    std::to_string(ecora::MAX_COMPETITORS) + " competing UEs");
        std::string site = disturbance.at("site");
        Require(m_competitorSite.empty() || m_competitorSite == site,
                "unbuildable_scenario",
                "v1 loads the cell at one site's position");
        m_competitorSite = site;
        m_competitorsBuilt = std::max(m_competitorsBuilt, wanted);
    }

    RngSeedManager::SetSeed(1);
    RngSeedManager::SetRun(m_rngRun);

    m_application = CreateObject<Node>();
    m_centralGateway = CreateObject<Node>();
    uint32_t index = 0;
    for (const auto& name : topology.at("sites"))
    {
        Site site;
        site.name = name;
        site.index = index++;
        site.gateway = CreateObject<Node>();
        site.path = m_initialPath;
        site.pacing = m_initialPacing;
        m_sites.push_back(site);
    }

    BuildLte(lte);
    BuildAlternative(alternative);
    BuildEgress(topology.at("egress"));
    BuildBackground();
    Route();
    Instrument();
    StartProbes();
    Schedule();
    m_configured = true;
    return Resolved();
}

void
World::BuildLte(const json& leg)
{
    NodeContainer gateways;
    std::vector<std::string> names;
    for (auto& site : m_sites)
    {
        gateways.Add(site.gateway);
        names.push_back(site.name);
    }
    // Competitors follow the sites in the UE order, at the loaded site's position.
    for (uint32_t i = 0; i < m_competitorsBuilt; ++i)
    {
        Ptr<Node> competitor = CreateObject<Node>();
        m_competitorNodes.push_back(competitor);
        gateways.Add(competitor);
        names.push_back(m_competitorSite);
    }
    ecora::LteLeg built = ecora::BuildLteLeg(leg, gateways, names);
    m_lte = built.lte;
    m_epc = built.epc;
    m_enb = built.enb;
    m_enbDevice = built.enbDevice;
    m_radioLoss = built.radioLoss;
    for (uint32_t i = 0; i < m_sites.size(); ++i)
    {
        m_sites[i].mobility = built.siteMobility[i];
        m_sites[i].lteDevice = built.ueDevices.Get(i);
        m_sites[i].lteAddress = built.ueAddresses.GetAddress(i);
    }
}

void
World::BuildAlternative(const json& leg)
{
    InternetStackHelper internet;
    internet.Install(m_centralGateway);
    internet.Install(m_application);
    PointToPointHelper link;
    link.SetDeviceAttribute("DataRate", StringValue(Rate(leg.at("capacity_bps"))));
    link.SetChannelAttribute("Delay", TimeValue(At(leg.at("delay_s"))));
    link.SetQueue("ns3::DropTailQueue",
                  "MaxSize",
                  StringValue(std::to_string(leg.at("queue_limit_bytes").get<uint64_t>()) + "B"));
    TrafficControlHelper traffic;
    Ipv4AddressHelper addresses;
    for (auto& site : m_sites)
    {
        NetDeviceContainer devices = link.Install(site.gateway, m_centralGateway);
        site.altGateway = DynamicCast<PointToPointNetDevice>(devices.Get(0));
        site.altCentral = DynamicCast<PointToPointNetDevice>(devices.Get(1));
        for (auto* end : {&site.altGatewayLoss, &site.altCentralLoss})
        {
            *end = CreateObject<RateErrorModel>();
            (*end)->SetUnit(RateErrorModel::ERROR_UNIT_PACKET);
            (*end)->SetRate(0);
        }
        site.altGateway->SetReceiveErrorModel(site.altGatewayLoss);
        site.altCentral->SetReceiveErrorModel(site.altCentralLoss);
        std::string subnet = "10.10." + std::to_string(site.index) + ".0";
        addresses.SetBase(subnet.c_str(), "255.255.255.252");
        Ipv4InterfaceContainer assigned = addresses.Assign(devices);
        site.altAddress = assigned.GetAddress(0);
        // No queue discipline: the leg's queue is the declared DropTail FIFO and nothing
        // else. ns-3 installs a default one when the address is assigned, so it is removed
        // after assignment, not before.
        traffic.Uninstall(devices);
    }
}

void
World::BuildEgress(const json& leg)
{
    PointToPointHelper link;
    link.SetDeviceAttribute("DataRate", StringValue(Rate(leg.at("capacity_bps"))));
    link.SetChannelAttribute("Delay", TimeValue(At(leg.at("delay_s"))));
    link.SetQueue("ns3::DropTailQueue",
                  "MaxSize",
                  StringValue(std::to_string(leg.at("queue_limit_bytes").get<uint64_t>()) + "B"));
    NetDeviceContainer devices = link.Install(m_centralGateway, m_application);
    m_egressCentral = DynamicCast<PointToPointNetDevice>(devices.Get(0));
    m_egressApplication = DynamicCast<PointToPointNetDevice>(devices.Get(1));
    Ipv4AddressHelper addresses;
    addresses.SetBase("10.2.0.0", "255.255.255.252");
    Ipv4InterfaceContainer assigned = addresses.Assign(devices);
    m_applicationAddress = assigned.GetAddress(1);
    TrafficControlHelper().Uninstall(devices);

    // The EPC's gateway reaches the central gateway over an internal wired link: model
    // support, not a leg of the study.
    PointToPointHelper internal;
    internal.SetDeviceAttribute("DataRate", StringValue(INTERNAL_RATE));
    internal.SetChannelAttribute("Delay", TimeValue(At(INTERNAL_DELAY_S)));
    NetDeviceContainer core = internal.Install(m_epc->GetPgwNode(), m_centralGateway);
    addresses.SetBase("10.1.0.0", "255.255.255.252");
    addresses.Assign(core);
}

void
World::BuildBackground()
{
    if (m_competitorsBuilt == 0)
    {
        return;
    }
    m_backgroundSink = CreateObject<Node>();
    InternetStackHelper().Install(m_backgroundSink);
    PointToPointHelper link;
    link.SetDeviceAttribute("DataRate", StringValue(INTERNAL_RATE));
    link.SetChannelAttribute("Delay", TimeValue(At(INTERNAL_DELAY_S)));
    NetDeviceContainer devices = link.Install(m_epc->GetPgwNode(), m_backgroundSink);
    Ipv4AddressHelper addresses;
    addresses.SetBase("10.3.0.0", "255.255.255.252");
    Ipv4InterfaceContainer assigned = addresses.Assign(devices);
    m_backgroundAddress = assigned.GetAddress(1);
    Ipv4StaticRoutingHelper helper;
    helper.GetStaticRouting(m_backgroundSink->GetObject<Ipv4>())
        ->AddNetworkRouteTo("7.0.0.0", "255.0.0.0", assigned.GetAddress(0), 1);
    // A listening socket that discards, so arriving load raises no ICMP back down the cell.
    m_backgroundReceive = Socket::CreateSocket(m_backgroundSink, UdpSocketFactory::GetTypeId());
    m_backgroundReceive->Bind(InetSocketAddress(Ipv4Address::GetAny(), 7000));
    m_backgroundReceive->SetRecvCallback(MakeCallback(+[](Ptr<Socket> socket) {
        while (socket->Recv())
        {
        }
    }));
    for (Ptr<Node> competitor : m_competitorNodes)
    {
        helper.GetStaticRouting(competitor->GetObject<Ipv4>())
            ->SetDefaultRoute(m_epc->GetUeDefaultGatewayAddress(), 1);
        Ptr<Socket> socket = Socket::CreateSocket(competitor, UdpSocketFactory::GetTypeId());
        socket->Bind();
        m_competitorSockets.push_back(socket);
        m_competitorActive.push_back(false);
        m_competitorRunning.push_back(false);
    }
}

void
World::CompetitorTick(uint32_t index)
{
    if (!m_competitorActive[index])
    {
        m_competitorRunning[index] = false;
        return;
    }
    Ptr<Packet> packet = Create<Packet>(ecora::COMPETITOR_PAYLOAD_BYTES);
    // Identity 0 marks background load: its drops are counted apart and never attributed
    // to an obligation or to the untraced count.
    ObligationTag tag;
    packet->AddPacketTag(tag);
    m_competitorSockets[index]->SendTo(packet, 0, InetSocketAddress(m_backgroundAddress, 7000));
    Simulator::Schedule(Seconds(8.0 * ecora::COMPETITOR_PAYLOAD_BYTES / ecora::COMPETITOR_OFFERED_BPS),
                        &World::CompetitorTick,
                        this,
                        index);
}

void
World::Route()
{
    Ipv4StaticRoutingHelper helper;
    auto ipv4 = [](Ptr<Node> node) { return node->GetObject<Ipv4>(); };
    auto routing = [&](Ptr<Node> node) { return helper.GetStaticRouting(ipv4(node)); };

    Ptr<Ipv4> central = ipv4(m_centralGateway);
    Ptr<Ipv4> pgw = ipv4(m_epc->GetPgwNode());
    uint32_t centralToPgw = central->GetInterfaceForPrefix("10.1.0.0", "255.255.255.252");
    uint32_t centralToApp = central->GetInterfaceForPrefix("10.2.0.0", "255.255.255.252");
    uint32_t pgwToCentral = pgw->GetInterfaceForPrefix("10.1.0.0", "255.255.255.252");
    Ipv4Address pgwAddress = pgw->GetAddress(pgwToCentral, 0).GetLocal();
    Ipv4Address centralCore = central->GetAddress(centralToPgw, 0).GetLocal();
    Ipv4Address centralEgress = central->GetAddress(centralToApp, 0).GetLocal();

    // Application: everything through the central gateway.
    routing(m_application)->SetDefaultRoute(centralEgress, 1);
    // Central gateway: UEs through the EPC; the alternative subnets are directly attached.
    routing(m_centralGateway)->AddNetworkRouteTo("7.0.0.0", "255.0.0.0", pgwAddress, centralToPgw);
    // PGW: the application's subnet through the central gateway.
    routing(m_epc->GetPgwNode())
        ->AddNetworkRouteTo("10.2.0.0", "255.255.255.252", centralCore, pgwToCentral);

    for (auto& site : m_sites)
    {
        Ptr<Ipv4> gateway = ipv4(site.gateway);
        uint32_t lteInterface = gateway->GetInterfaceForDevice(site.lteDevice);
        uint32_t altInterface = gateway->GetInterfaceForDevice(site.altGateway);
        Ipv4Address altCentral =
            central->GetAddress(central->GetInterfaceForDevice(site.altCentral), 0).GetLocal();
        // One route to the application per leg. A socket bound to a leg's device may only
        // use that leg's route, which is how the gateway chooses the leg per datagram.
        routing(site.gateway)
            ->AddNetworkRouteTo("10.2.0.0",
                                "255.255.255.252",
                                m_epc->GetUeDefaultGatewayAddress(),
                                lteInterface);
        routing(site.gateway)->AddNetworkRouteTo("10.2.0.0", "255.255.255.252", altCentral, altInterface);

        TypeId udp = UdpSocketFactory::GetTypeId();
        site.receive = Socket::CreateSocket(site.gateway, udp);
        site.receive->Bind(InetSocketAddress(Ipv4Address::GetAny(), SITE_PORT));
        site.receive->SetRecvCallback(MakeCallback(&World::ReceiveAtSite, this));
        site.sendLte = Socket::CreateSocket(site.gateway, udp);
        site.sendLte->Bind();
        site.sendLte->BindToNetDevice(site.lteDevice);
        site.sendAlt = Socket::CreateSocket(site.gateway, udp);
        site.sendAlt->Bind();
        site.sendAlt->BindToNetDevice(site.altGateway);
    }
    TypeId udp = UdpSocketFactory::GetTypeId();
    m_applicationReceive = Socket::CreateSocket(m_application, udp);
    m_applicationReceive->Bind(InetSocketAddress(Ipv4Address::GetAny(), CENTRAL_PORT));
    m_applicationReceive->SetRecvCallback(MakeCallback(&World::ReceiveCentrally, this));
    m_applicationSend = Socket::CreateSocket(m_application, udp);
    m_applicationSend->Bind();

    // Drop evidence, wherever a datagram can be discarded with its identity still on it.
    for (const char* source : {"MacTxDrop", "PhyTxDrop", "PhyRxDrop"})
    {
        std::string where = std::string("point-to-point ") + source;
        Config::ConnectWithoutContextFailSafe(
            std::string("/NodeList/*/DeviceList/*/$ns3::PointToPointNetDevice/") + source,
            MakeBoundCallback(+[](World* world, std::string at, Ptr<const Packet> packet) {
                world->Dropped(packet, at);
            }, this, where));
    }
    Config::ConnectWithoutContextFailSafe(
        "/NodeList/*/$ns3::Ipv4L3Protocol/Drop",
        MakeBoundCallback(+[](World* world,
                              const Ipv4Header&,
                              Ptr<const Packet> packet,
                              Ipv4L3Protocol::DropReason,
                              Ptr<Ipv4>,
                              uint32_t) { world->Dropped(packet, "ipv4"); },
                          this));
    // RLC entities exist only once a bearer does, so drop tracing is attached as each
    // data radio bearer is created.
    Config::ConnectWithoutContextFailSafe(
        "/NodeList/*/DeviceList/*/LteUeRrc/DrbCreated",
        MakeBoundCallback(+[](World* world, uint64_t, uint16_t, uint16_t, uint8_t) {
            Simulator::ScheduleNow(&World::WatchBearers, world);
        }, this));
}

void
World::Instrument()
{
    // A datagram's class comes from the identity it carries: the obligation's service.
    auto classify = [this](Ptr<const Packet> packet) -> std::string {
        ObligationTag tag;
        if (!packet->PeekPacketTag(tag))
        {
            return "untagged";
        }
        if (tag.id == 0)
        {
            return "background";
        }
        if (tag.kind == PROBE)
        {
            return "probe";
        }
        auto found = m_ledger.find(tag.id);
        return found == m_ledger.end() ? "unknown" : found->second.service;
    };
    auto probe = [&](const std::string& name, Ptr<PointToPointNetDevice> device) {
        DataRateValue rate;
        device->GetAttribute("DataRate", rate);
        m_probes.emplace_back(name,
                              std::make_unique<QueueProbe>(device->GetQueue(),
                                                           rate.Get().GetBitRate(),
                                                           classify));
    };
    // Toward the application is up, as it is for the legs.
    probe("egress/up", m_egressCentral);
    probe("egress/down", m_egressApplication);
    for (auto& site : m_sites)
    {
        probe(site.name + "/alternative/up", site.altGateway);
        probe(site.name + "/alternative/down", site.altCentral);
    }
}

void
World::StartProbes()
{
    Ipv4StaticRoutingHelper helper;
    Ptr<Ipv4> central = m_centralGateway->GetObject<Ipv4>();
    Ipv4Address centralCore =
        central->GetAddress(central->GetInterfaceForPrefix("10.1.0.0", "255.255.255.252"), 0)
            .GetLocal();
    // The central gateway echoes each probe to its sender, so the answer returns over the
    // leg it arrived on: the sender's address belongs to that leg.
    m_probeEcho = Socket::CreateSocket(m_centralGateway, UdpSocketFactory::GetTypeId());
    m_probeEcho->Bind(InetSocketAddress(Ipv4Address::GetAny(), PROBE_PORT));
    m_probeEcho->SetRecvCallback(MakeCallback(&World::EchoProbe, this));
    for (auto& site : m_sites)
    {
        Ptr<Ipv4> gateway = site.gateway->GetObject<Ipv4>();
        uint32_t lteInterface = gateway->GetInterfaceForDevice(site.lteDevice);
        // The central gateway's core address is reached over the LTE leg.
        helper.GetStaticRouting(gateway)->AddNetworkRouteTo(
            "10.1.0.0", "255.255.255.252", m_epc->GetUeDefaultGatewayAddress(), lteInterface);
        Ipv4Address altCentral =
            central->GetAddress(central->GetInterfaceForDevice(site.altCentral), 0).GetLocal();
        for (const auto& [leg, device, echo] :
             {std::tuple<std::string, Ptr<NetDevice>, Ipv4Address>{"lte", site.lteDevice, centralCore},
              std::tuple<std::string, Ptr<NetDevice>, Ipv4Address>{"alternative",
                                                                   site.altGateway,
                                                                   altCentral}})
        {
            Site::Probe& probe = site.probes[leg];
            probe.socket = Socket::CreateSocket(site.gateway, UdpSocketFactory::GetTypeId());
            probe.socket->Bind();
            probe.socket->BindToNetDevice(device);
            probe.socket->SetRecvCallback(MakeCallback(&World::ProbeAnswered, this));
            probe.echo = InetSocketAddress(echo, PROBE_PORT);
            Simulator::Schedule(Seconds(PROBE_START_S), &World::SendProbe, this, &site, leg);
        }
    }
}

void
World::SendProbe(Site* site, std::string leg)
{
    Site::Probe& probe = site->probes[leg];
    uint64_t sequence = ++m_probeSequence;
    uint8_t body[PROBE_BYTES] = {'P', 'R', 'O', 'B'};
    for (int i = 0; i < 8; ++i)
    {
        body[8 + i] = static_cast<uint8_t>(sequence >> (56 - 8 * i));
    }
    Ptr<Packet> packet = Create<Packet>(body, PROBE_BYTES);
    ObligationTag tag;
    tag.id = sequence;
    tag.kind = PROBE;
    packet->AddPacketTag(tag);
    probe.outstanding[sequence] = Now();
    probe.sentS = Now();
    ++probe.sent;
    probe.socket->SendTo(packet, 0, probe.echo);
    Simulator::Schedule(Seconds(PROBE_PERIOD_S), &World::SendProbe, this, site, leg);
}

void
World::EchoProbe(Ptr<Socket> socket)
{
    Address from;
    Ptr<Packet> packet;
    while ((packet = socket->RecvFrom(from)))
    {
        socket->SendTo(packet, 0, from);
    }
}

void
World::ProbeAnswered(Ptr<Socket> socket)
{
    Ptr<Packet> packet;
    while ((packet = socket->Recv()))
    {
        uint8_t body[PROBE_BYTES];
        if (packet->GetSize() < PROBE_BYTES)
        {
            continue;
        }
        packet->CopyData(body, PROBE_BYTES);
        uint64_t sequence = 0;
        for (int i = 0; i < 8; ++i)
        {
            sequence = (sequence << 8) | body[8 + i];
        }
        for (auto& site : m_sites)
        {
            for (auto& [leg, probe] : site.probes)
            {
                if (probe.socket != socket)
                {
                    continue;
                }
                auto sent = probe.outstanding.find(sequence);
                if (sent == probe.outstanding.end())
                {
                    continue;
                }
                double rtt = Now() - sent->second;
                // An answer after the timeout is a lost probe, not a slow one: the timeout
                // is part of the probe's definition, as it is in the finite world.
                if (rtt <= PROBE_TIMEOUT_S)
                {
                    probe.completedS = Now();
                    probe.rttS = rtt;
                    ++probe.answered;
                }
                else
                {
                    ++probe.timedOut;
                }
                probe.outstanding.erase(sent);
            }
        }
    }
}

json
World::Observation(const Site& site,
                   const std::string& subject,
                   const std::string& metric,
                   const std::string& capability,
                   double windowS) const
{
    double now = Now();
    json observation = {{"subject", subject},
                        {"metric", metric},
                        {"quality", "observed"},
                        {"missing_reason", nullptr},
                        {"event_time_s", now},
                        {"available_at_s", now},
                        {"window", {{"start_s", std::max(0.0, now - windowS)}, {"end_s", now}}},
                        {"source", "ns3.simulator"},
                        {"sampling_policy", "instantaneous"},
                        {"valid_min", nullptr},
                        {"valid_max", nullptr},
                        {"evidence_kind", "measured"},
                        {"capability_id", capability},
                        {"source_observation_ids", json::array()},
                        {"formula", nullptr},
                        {"privileged_source_refs", json::array()}};
    if (metric == "path_state" || metric == "pacing_profile")
    {
        observation["service"] = metric == "path_state" ? "shared" : "ami";
        observation["unit"] = "id";
        observation["value"] = metric == "path_state" ? site.path : site.pacing;
        observation["assumptions"] = {"Gateway actuator readback in the ns-3 model."};
    }
    else if (metric == "queue_occupancy")
    {
        observation["service"] = "ami";
        observation["unit"] = "byte";
        if (site.path == "alternative")
        {
            observation["value"] = site.altGateway->GetQueue()->GetNBytes();
            observation["assumptions"] = {
                "Bytes held by the alternative leg's device queue, excluding the datagram "
                "on the wire."};
        }
        else
        {
            int64_t held = int64_t(site.rlcAcceptedBytes) - int64_t(site.rlcDroppedBytes) -
                           (int64_t(site.rlcTransmittedBytes) - 2 * int64_t(site.rlcPdus));
            observation["value"] = std::max<int64_t>(0, held);
            observation["evidence_kind"] = "derived";
            observation["formula"] = "SDU bytes into RLC - SDU bytes dropped by RLC - "
                                     "(PDU bytes to MAC - 2 bytes per PDU header)";
            observation["assumptions"] = {
                "The UE's RLC transmission buffer, derived from the flows into and out of it; "
                "ns-3 keeps the buffer size private. Understates by 1.5 bytes per additional "
                "SDU segment boundary in a PDU."};
        }
    }
    else if (metric == "actuator_version")
    {
        // The actuator's own version, readback: what a write must name to be accepted.
        bool path = subject.size() >= 14 && subject.compare(subject.size() - 14, 14, "/selected_path") == 0;
        observation["service"] = path ? "shared" : "ami";
        observation["unit"] = "count";
        observation["value"] = path ? site.pathVersion : site.pacingVersion;
        observation["assumptions"] = {"Gateway actuator version readback in the ns-3 model."};
    }
    else if (metric == "scada_response")
    {
        // The window ending one summary delay ago: the newest the centre's report can be.
        double end = std::max(0.0, now - DELIVERY_SUMMARY_DELAY_S);
        double start = std::max(0.0, end - windowS);
        double total = 0;
        uint64_t count = 0;
        for (const auto& [id, obligation] : m_ledger)
        {
            if (obligation.service == "scada" && obligation.site == site.name &&
                obligation.delivered_s && *obligation.delivered_s > start &&
                *obligation.delivered_s <= end)
            {
                total += *obligation.delivered_s - obligation.generated_s;
                ++count;
            }
        }
        observation["service"] = "scada";
        observation["unit"] = "s";
        observation["event_time_s"] = end;
        observation["window"] = {{"start_s", start}, {"end_s", end}};
        observation["sampling_policy"] = "delivery_summary_mean";
        observation["assumptions"] = {
            "Mean response time of " + std::to_string(count) +
            " SCADA transactions the centre completed in the window, reported " +
            std::to_string(DELIVERY_SUMMARY_DELAY_S) + " s later."};
        if (count)
        {
            observation["value"] = total / count;
        }
        else
        {
            observation["value"] = nullptr;
            observation["quality"] = "missing";
            observation["missing_reason"] = {
                {"code", "no_completion"},
                {"detail", "No SCADA transaction completed in the summarised window."}};
        }
    }
    else if (metric == "path_probe")
    {
        std::string leg = subject.substr(subject.find('/') + 1);
        const Site::Probe& probe = site.probes.at(leg);
        observation["service"] = "shared";
        observation["unit"] = "s";
        observation["sampling_policy"] = "latest_acknowledged_probe";
        observation["assumptions"] = {
            "Round trip of a 32-byte probe echoed by the central gateway over this leg; "
            "evidence for 0.5 s after its acknowledgement."};
        if (probe.completedS >= 0 && now - probe.completedS <= PROBE_VALIDITY_S)
        {
            double sent = probe.completedS - probe.rttS;
            observation["value"] = probe.rttS;
            observation["event_time_s"] = probe.completedS;
            observation["available_at_s"] = probe.completedS;
            observation["window"] = {{"start_s", sent}, {"end_s", probe.completedS}};
        }
        else
        {
            observation["value"] = nullptr;
            observation["quality"] = "missing";
            observation["missing_reason"] = {
                {"code", "probe_timeout"},
                {"detail", "No probe on this leg was acknowledged within its validity."}};
        }
    }
    else
    {
        throw Refusal("unsupported_signal", "this simulator does not export " + metric);
    }
    return observation;
}

json
World::ActuatorState() const
{
    // The gateway actuators' own readback: what a controller can see, not simulator truth.
    json paths = json::object(), pacing = json::object(), versions = json::object(),
         pacingVersions = json::object();
    for (const auto& site : m_sites)
    {
        paths[site.name] = site.path;
        pacing[site.name] = site.pacing;
        versions[site.name] = site.pathVersion;
        pacingVersions[site.name] = site.pacingVersion;
    }
    return {{"selected_path", paths},
            {"pacing", pacing},
            {"path_version", versions},
            {"pacing_version", pacingVersions}};
}

json
World::Apply(const json& request)
{
    Require(m_configured, "not_configured", "configure before applying");
    const json& command = request.at("command");
    std::string operatorName = command.at("operator");
    std::string target = command.at("target");
    // The same catalog, checks and reasons as the finite world, so an arm's commands are
    // applied or refused alike in either world. A refusal here is the actuator's answer
    // and is reported as a result, not raised: the command was well formed and was heard.
    auto answer = [this](bool applied, const char* reason) {
        return json{{"applied", applied},
                    {"reason", reason ? json(reason) : json()},
                    {"applied_at_s", applied ? json(Now()) : json()},
                    {"actuator_state", ActuatorState()}};
    };
    if (operatorName == "no_op")
    {
        return answer(false, "no_op");
    }
    Site* site = nullptr;
    for (auto& candidate : m_sites)
    {
        if (candidate.name == target)
        {
            site = &candidate;
        }
    }
    if (!site)
    {
        return answer(false, "unknown_target");
    }
    if (operatorName == "select_path" || operatorName == "set_ami_pacing")
    {
        // Compare-and-swap on the actuator's version, as the finite world does: a write
        // names the state it was decided against, and one decided against an older state
        // is refused.
        uint64_t current = operatorName == "select_path" ? site->pathVersion : site->pacingVersion;
        if (!command.contains("expected_state_version") || command.at("expected_state_version").is_null())
        {
            return answer(false, "missing_version");
        }
        if (command.at("expected_state_version").get<uint64_t>() != current)
        {
            return answer(false, "stale_version");
        }
    }
    const json& arguments = command.at("arguments");
    if (operatorName == "select_path")
    {
        std::string path = arguments.at("path");
        if (!site->probes.count(path))
        {
            return answer(false, "unknown_path");
        }
        // Newly released datagrams take the new leg; those already sent keep theirs.
        site->path = path;
        ++site->pathVersion;
        return answer(true, nullptr);
    }
    if (operatorName == "set_ami_pacing")
    {
        std::string profile = arguments.at("profile");
        if (!PACING_BPS.count(profile))
        {
            return answer(false, "unknown_profile");
        }
        // A release interval already being counted completes at its old rate, as it does
        // in the finite world; the next one uses the new profile.
        site->pacing = profile;
        ++site->pacingVersion;
        return answer(true, nullptr);
    }
    return answer(false, "unsupported_operator");
}

json
World::Observe(const json& request)
{
    Require(m_configured, "not_configured", "configure before observing");
    double windowS = request.at("window_s");
    json observations = json::array();
    // Only what a grant names is exported. A grant for a subject the world does not hold
    // is refused rather than answered with nothing.
    for (const auto& grant : request.at("grants"))
    {
        std::string subject = grant.at("subject");
        std::string siteName = subject.substr(0, subject.find('/'));
        const Site* site = nullptr;
        for (const auto& candidate : m_sites)
        {
            if (candidate.name == siteName)
            {
                site = &candidate;
            }
        }
        Require(site != nullptr, "unknown_subject", "no site " + siteName + " in this world");
        if (subject.find('/') != std::string::npos)
        {
            // Below a site a subject is one of its legs or one of its actuators.
            std::string part = subject.substr(subject.find('/') + 1);
            Require(site->probes.count(part) || part == "selected_path" || part == "pacing_profile",
                    "unknown_subject",
                    "no leg or actuator " + part + " at " + siteName);
        }
        observations.push_back(
            Observation(*site, subject, grant.at("metric"), grant.at("capability_id"), windowS));
    }
    return {{"observations", observations}};
}

void
World::WatchBearers()
{
    // Per site, the flows into and out of the UE's own data-bearer RLC, for the derived
    // local queue. Competitors' bearers and the eNB's are not a site's queue.
    for (auto& site : m_sites)
    {
        std::string base = "/NodeList/" + std::to_string(site.gateway->GetId()) +
                           "/DeviceList/*/LteUeRrc/DataRadioBearerMap/*/";
        Config::MatchContainer pdcps = Config::LookupMatches(base + "LtePdcp");
        for (uint32_t i = 0; i < pdcps.GetN(); ++i)
        {
            if (m_watchedFlows.insert(PeekPointer(pdcps.Get(i))).second)
            {
                pdcps.Get(i)->TraceConnectWithoutContext(
                    "TxPDU",
                    MakeBoundCallback(+[](Site* s, uint16_t, uint8_t, uint32_t size) {
                        s->rlcAcceptedBytes += size;
                    }, &site));
            }
        }
        Config::MatchContainer rlcs = Config::LookupMatches(base + "LteRlc");
        for (uint32_t i = 0; i < rlcs.GetN(); ++i)
        {
            if (m_watchedFlows.insert(PeekPointer(rlcs.Get(i))).second)
            {
                rlcs.Get(i)->TraceConnectWithoutContext(
                    "TxPDU",
                    MakeBoundCallback(+[](Site* s, uint16_t, uint8_t, uint32_t size) {
                        s->rlcTransmittedBytes += size;
                        ++s->rlcPdus;
                    }, &site));
                rlcs.Get(i)->TraceConnectWithoutContext(
                    "TxDrop",
                    MakeBoundCallback(+[](Site* s, Ptr<const Packet> packet) {
                        s->rlcDroppedBytes += packet->GetSize();
                    }, &site));
            }
        }
    }
    for (const char* path : {"/NodeList/*/DeviceList/*/LteUeRrc/DataRadioBearerMap/*/LteRlc",
                             "/NodeList/*/DeviceList/*/LteEnbRrc/UeMap/*/DataRadioBearerMap/*/LteRlc"})
    {
        Config::MatchContainer found = Config::LookupMatches(path);
        for (uint32_t i = 0; i < found.GetN(); ++i)
        {
            Ptr<Object> rlc = found.Get(i);
            if (m_watchedRlc.insert(PeekPointer(rlc)).second)
            {
                rlc->TraceConnectWithoutContext(
                    "TxDrop",
                    MakeBoundCallback(+[](World* world, Ptr<const Packet> packet) {
                        world->Dropped(packet, "lte rlc");
                    }, this));
            }
        }
    }
}

void
World::Schedule()
{
    // m_sites is complete before any event holds a pointer into it, and never grows.
    for (auto& site : m_sites)
    {
        Simulator::Schedule(Seconds(0), &World::GenerateScada, this, &site);
        Simulator::Schedule(Seconds(0), &World::GenerateAmi, this, &site);
    }
    for (const auto& disturbance : m_scenario.at("disturbances"))
    {
        Simulator::Schedule(At(disturbance.at("at_s")), &World::Disturb, this, disturbance);
    }
}

Ptr<Socket>
World::SiteSocket(Site* site, const std::string& path) const
{
    return path == "lte" ? site->sendLte : site->sendAlt;
}

Address
World::SiteAddress(const Site* site, const std::string& path) const
{
    return InetSocketAddress(path == "lte" ? site->lteAddress : site->altAddress, SITE_PORT);
}

void
World::Send(Ptr<Socket> socket, Address to, uint64_t id, Kind kind, uint32_t payload)
{
    // The envelope: magic, version, kind, then the obligation identity. Its bytes are
    // counted on the wire, in addition to the declared payload.
    uint8_t envelope[ENVELOPE_BYTES] = {'E', 'C', 'R', 'A', 1, kind};
    for (int i = 0; i < 8; ++i)
    {
        envelope[8 + i] = static_cast<uint8_t>(id >> (56 - 8 * i));
    }
    Ptr<Packet> packet = Create<Packet>(envelope, ENVELOPE_BYTES);
    packet->AddAtEnd(Create<Packet>(payload));
    ObligationTag tag;
    tag.id = id;
    tag.kind = kind;
    packet->AddPacketTag(tag);
    socket->SendTo(packet, 0, to);
}

bool
ReadEnvelope(Ptr<Packet> packet, uint64_t& id, uint8_t& kind)
{
    uint8_t envelope[ENVELOPE_BYTES];
    if (packet->GetSize() < ENVELOPE_BYTES)
    {
        return false;
    }
    packet->CopyData(envelope, ENVELOPE_BYTES);
    if (envelope[0] != 'E' || envelope[1] != 'C' || envelope[2] != 'R' || envelope[3] != 'A')
    {
        return false;
    }
    kind = envelope[5];
    id = 0;
    for (int i = 0; i < 8; ++i)
    {
        id = (id << 8) | envelope[8 + i];
    }
    return true;
}

void
World::GenerateScada(Site* site)
{
    uint64_t id = m_next++;
    double deadline = m_scada.at("deadline_s");
    m_ledger[id] = Obligation{id, "scada", site->name, Now(), Now() + deadline, {}, {}};
    m_order.push_back(id);
    // The central adapter sends over the site's leg selected now; a request already sent
    // keeps its leg if the site switches.
    Send(m_applicationSend,
         SiteAddress(site, site->path),
         id,
         REQUEST,
         m_scada.at("payload_bytes"));
    Simulator::Schedule(At(m_scada.at("generation").at("period_s")),
                        &World::GenerateScada,
                        this,
                        site);
}

void
World::GenerateAmi(Site* site)
{
    uint64_t id = m_next++;
    double deadline = m_ami.at("deadline_s");
    m_ledger[id] = Obligation{id, "ami", site->name, Now(), Now() + deadline, {}, {}};
    m_order.push_back(id);
    site->held.push_back(id);
    if (!site->releasing)
    {
        StartRelease(site);
    }
    Simulator::Schedule(At(m_ami.at("generation").at("period_s")),
                        &World::GenerateAmi,
                        this,
                        site);
}

void
World::StartRelease(Site* site)
{
    // The same release gate as the finite world: one held reading at a time, after the
    // interval its size takes at the current profile.
    if (site->held.empty())
    {
        site->releasing = false;
        return;
    }
    site->releasing = true;
    double bits = 8.0 * m_ami.at("payload_bytes").get<double>();
    Simulator::Schedule(Seconds(bits / PACING_BPS.at(site->pacing)), &World::Release, this, site);
}

void
World::Release(Site* site)
{
    uint64_t id = site->held.front();
    site->held.pop_front();
    Send(SiteSocket(site, site->path),
         InetSocketAddress(m_applicationAddress, CENTRAL_PORT),
         id,
         READING,
         m_ami.at("payload_bytes"));
    site->releasing = false;
    StartRelease(site);
}

void
World::ReceiveAtSite(Ptr<Socket> socket)
{
    Ptr<Packet> packet;
    while ((packet = socket->Recv()))
    {
        uint64_t id;
        uint8_t kind;
        if (!ReadEnvelope(packet, id, kind) || kind != REQUEST || !m_ledger.count(id))
        {
            continue;
        }
        Site* site = nullptr;
        for (auto& candidate : m_sites)
        {
            if (candidate.gateway == socket->GetNode())
            {
                site = &candidate;
            }
        }
        // Answer after the processing delay, over the leg selected at that moment.
        Simulator::Schedule(At(m_scada.at("processing_delay_s")), [this, site, id]() {
            Send(SiteSocket(site, site->path),
                 InetSocketAddress(m_applicationAddress, CENTRAL_PORT),
                 id,
                 RESPONSE,
                 m_scada.at("response_bytes"));
        });
    }
}

void
World::ReceiveCentrally(Ptr<Socket> socket)
{
    Ptr<Packet> packet;
    while ((packet = socket->Recv()))
    {
        uint64_t id;
        uint8_t kind;
        if (!ReadEnvelope(packet, id, kind) || !m_ledger.count(id) || kind == REQUEST)
        {
            continue;
        }
        Obligation& obligation = m_ledger[id];
        if (obligation.delivered_s)
        {
            // Duplicates add no success, and are counted rather than ignored.
            ++m_duplicates;
            continue;
        }
        obligation.delivered_s = Now();
    }
}

void
World::Dropped(Ptr<const Packet> packet, const std::string& where)
{
    ObligationTag tag;
    if (packet->PeekPacketTag(tag) && tag.id == 0)
    {
        ++m_backgroundDrops;
        return;
    }
    if (packet->PeekPacketTag(tag) && tag.kind == PROBE)
    {
        // A lost probe is evidence about the leg, reported through its timeout, and never
        // an obligation lost.
        ++m_probeDrops;
        return;
    }
    if (!packet->PeekPacketTag(tag) || !m_ledger.count(tag.id))
    {
        // Something was discarded whose obligation cannot be named from the packet. It is
        // counted, and it is not attributed to anything.
        ++m_untracedDrops;
        return;
    }
    Obligation& obligation = m_ledger[tag.id];
    if (!obligation.delivered_s && !obligation.dropped)
    {
        obligation.dropped = where;
    }
}

void
World::Disturb(const json& disturbance)
{
    Site* site = nullptr;
    std::string target = disturbance.at("site");
    for (auto& candidate : m_sites)
    {
        if (candidate.name == target)
        {
            site = &candidate;
        }
    }
    std::string kind = disturbance.at("kind");
    if (kind == "cell_load")
    {
        m_competingNow = disturbance.at("competing_ues");
        for (uint32_t i = 0; i < m_competitorsBuilt; ++i)
        {
            m_competitorActive[i] = i < m_competingNow;
            if (m_competitorActive[i] && !m_competitorRunning[i])
            {
                m_competitorRunning[i] = true;
                Simulator::ScheduleNow(&World::CompetitorTick, this, i);
            }
        }
    }
    else if (kind == "radio_loss")
    {
        site->extraLossDb = disturbance.at("extra_loss_db");
        m_radioLoss->SetLoss(site->mobility, m_enb->GetObject<MobilityModel>(), site->extraLossDb, true);
    }
    else
    {
        double rate = disturbance.at("rate_bps");
        // A point-to-point device cannot run at zero. A leg taken to zero loses every
        // datagram at both receivers instead, which is the declared mapping.
        double loss = rate > 0 ? 0.0 : 1.0;
        site->altGatewayLoss->SetRate(loss);
        site->altCentralLoss->SetRate(loss);
        if (rate > 0)
        {
            site->altGateway->SetDataRate(DataRate(Rate(rate)));
            site->altCentral->SetDataRate(DataRate(Rate(rate)));
        }
    }
    json applied = disturbance;
    applied["applied_at_s"] = Now();
    m_disturbanceLog.push_back(applied);
}

json
World::Resolved() const
{
    // Read back from the objects built, not echoed from the request, so a setting the
    // simulator did not take shows up as a disagreement.
    Ptr<LteEnbNetDevice> enb = DynamicCast<LteEnbNetDevice>(m_enbDevice);
    UintegerValue dlBw, ulBw, dlEarfcn, ulEarfcn;
    enb->GetAttribute("DlBandwidth", dlBw);
    enb->GetAttribute("UlBandwidth", ulBw);
    enb->GetAttribute("DlEarfcn", dlEarfcn);
    enb->GetAttribute("UlEarfcn", ulEarfcn);
    // The loss models are read from the channels they were installed on, not from the
    // helper's settings: PathlossModel is write-only there, and the channel is what the
    // radio actually traverses.
    auto lossChain = [](Ptr<SpectrumChannel> channel) {
        json chain = json::array();
        if (Ptr<SpectrumPropagationLossModel> spectrum = channel->GetSpectrumPropagationLossModel())
        {
            chain.push_back(spectrum->GetInstanceTypeId().GetName());
        }
        for (Ptr<PropagationLossModel> model = channel->GetPropagationLossModel(); model;
             model = model->GetNext())
        {
            chain.push_back(model->GetInstanceTypeId().GetName());
        }
        return chain;
    };
    // Read as text: ns-3 serialises any attribute into a StringValue, whatever its type.
    StringValue rlcMapping;
    enb->GetRrc()->GetAttribute("EpsBearerToRlcMapping", rlcMapping);
    // The RLC entities do not exist until a bearer does; the value they will take is the
    // attribute's initial value, which the configured default has replaced.
    TypeId::AttributeInformation rlcBufferInfo;
    LteRlcUm::GetTypeId().LookupAttributeByName("MaxTxBufferSize", &rlcBufferInfo);
    std::string rlcBuffer = rlcBufferInfo.initialValue->SerializeToString(rlcBufferInfo.checker);
    DoubleValue enbTx, enbNf;
    enb->GetPhy()->GetAttribute("TxPower", enbTx);
    enb->GetPhy()->GetAttribute("NoiseFigure", enbNf);

    json sites = json::array();
    for (const auto& site : m_sites)
    {
        Ptr<LteUeNetDevice> ue = DynamicCast<LteUeNetDevice>(site.lteDevice);
        DoubleValue ueTx, ueNf;
        ue->GetPhy()->GetAttribute("TxPower", ueTx);
        ue->GetPhy()->GetAttribute("NoiseFigure", ueNf);
        DataRateValue altRate;
        site.altGateway->GetAttribute("DataRate", altRate);
        TimeValue altDelay;
        site.altGateway->GetChannel()->GetAttribute("Delay", altDelay);
        QueueSizeValue altQueue;
        site.altGateway->GetQueue()->GetAttribute("MaxSize", altQueue);
        Vector at = site.mobility->GetPosition();
        Vector enbAt = m_enb->GetObject<MobilityModel>()->GetPosition();
        sites.push_back({{"site", site.name},
                         {"position_m", {at.x, at.y, at.z}},
                         {"distance_to_enb_m", CalculateDistance(at, enbAt)},
                         {"ue_tx_dbm", ueTx.Get()},
                         {"ue_noise_figure_db", ueNf.Get()},
                         {"lte_address", [&] {
                              std::ostringstream s;
                              site.lteAddress.Print(s);
                              return s.str();
                          }()},
                         {"alternative",
                          {{"capacity_bps", altRate.Get().GetBitRate()},
                           {"delay_s", altDelay.Get().GetSeconds()},
                           {"queue_limit", [&] {
                                std::ostringstream s;
                                s << altQueue.Get();
                                return s.str();
                            }()},
                           {"error_model", "ns3::RateErrorModel packet unit, rate 0"}}},
                         {"initial_path", site.path},
                         {"initial_pacing", site.pacing}});
    }
    DataRateValue egressRate;
    m_egressCentral->GetAttribute("DataRate", egressRate);
    TimeValue egressDelay;
    m_egressCentral->GetChannel()->GetAttribute("Delay", egressDelay);
    QueueSizeValue egressQueue;
    m_egressCentral->GetQueue()->GetAttribute("MaxSize", egressQueue);
    std::ostringstream egressLimit;
    egressLimit << egressQueue.Get();

    json pacing;
    for (const auto& [name, bps] : PACING_BPS)
    {
        pacing[name] = bps;
    }
    return {{"world", "ns-3"},
            {"release", "3.48"},
            {"rng", {{"seed", RngSeedManager::GetSeed()}, {"run", RngSeedManager::GetRun()}}},
            {"lte",
             {{"dl_bandwidth_rb", dlBw.Get()},
              {"ul_bandwidth_rb", ulBw.Get()},
              {"dl_earfcn", dlEarfcn.Get()},
              {"ul_earfcn", ulEarfcn.Get()},
              {"dl_frequency_hz", LteSpectrumValueHelper::GetDownlinkCarrierFrequency(dlEarfcn.Get())},
              {"ul_frequency_hz", LteSpectrumValueHelper::GetUplinkCarrierFrequency(ulEarfcn.Get())},
              {"downlink_loss_models", lossChain(m_lte->GetDownlinkSpectrumChannel())},
              {"uplink_loss_models", lossChain(m_lte->GetUplinkSpectrumChannel())},
              {"scheduler", m_lte->GetSchedulerType()},
              {"rlc_mapping", rlcMapping.Get()},
              {"rlc_um_max_tx_buffer_bytes", std::stoull(rlcBuffer)},
              {"enb_tx_dbm", enbTx.Get()},
              {"enb_noise_figure_db", enbNf.Get()},
              {"radio_impairment", "ns3::MatrixPropagationLossModel, per site, 0 dB until disturbed"},
              {"logical", "not_applicable"}}},
            {"sites", sites},
            {"egress",
             {{"capacity_bps", egressRate.Get().GetBitRate()},
              {"delay_s", egressDelay.Get().GetSeconds()},
              {"queue_limit", egressLimit.str()},
              {"queue_discipline", "none"}}},
            {"internal_link", {{"rate", INTERNAL_RATE}, {"delay_s", INTERNAL_DELAY_S}}},
            {"flows",
             {{"scada",
               {{"pattern", "request_response"},
                {"request_bytes", m_scada.at("payload_bytes")},
                {"response_bytes", m_scada.at("response_bytes")},
                {"processing_delay_s", m_scada.at("processing_delay_s")},
                {"period_s", m_scada.at("generation").at("period_s")},
                {"deadline_s", m_scada.at("deadline_s")}}},
              {"ami",
               {{"pattern", "periodic"},
                {"payload_bytes", m_ami.at("payload_bytes")},
                {"period_s", m_ami.at("generation").at("period_s")},
                {"deadline_s", m_ami.at("deadline_s")}}}}},
            {"envelope_bytes", ENVELOPE_BYTES},
            {"pacing_bps", pacing},
            {"rate_zero_mapping", "receive error rate 1.0 at both ends of the leg"},
            {"cell_load",
             {{"competitors_built", m_competitorsBuilt},
              {"site", m_competitorSite},
              {"offered_bps_each", ecora::COMPETITOR_OFFERED_BPS},
              {"payload_bytes", ecora::COMPETITOR_PAYLOAD_BYTES},
              {"max_competitors", ecora::MAX_COMPETITORS},
              {"direction", "up"},
              {"traffic_sink", "background node beside the EPC; never the study's egress"}}},
            {"disturbances_scheduled", m_scenario.at("disturbances").size()},
            {"unsupported_requests", {"truth", "fork"}},
            {"probes",
             {{"period_s", PROBE_PERIOD_S},
              {"payload_bytes", PROBE_BYTES},
              {"timeout_s", PROBE_TIMEOUT_S},
              {"validity_s", PROBE_VALIDITY_S},
              {"echo", "central gateway, over the probed leg"}}}};
}

json
World::Advance(const json& request)
{
    Require(m_configured, "not_configured", "configure before advancing");
    double target = request.at("time_s");
    // Monotonic: a clock asked to go back is refused, never clamped.
    Require(target >= Now(), "clock_backwards", "the simulator clock cannot move backwards");
    Simulator::Stop(At(target) - Simulator::Now());
    Simulator::Run();
    WatchBearers();
    return {{"time_s", Now()}};
}

json
World::Cohorts(const json& request)
{
    Require(m_configured, "not_configured", "configure before asking for cohorts");
    json result = json::array();
    for (const auto& spec : request.at("cohort_specs"))
    {
        double start = spec.at("generation_window").at("start_s");
        double end = spec.at("generation_window").at("end_s");
        std::string service = spec.at("service");
        uint64_t generated = 0, onTime = 0, late = 0, lost = 0, pending = 0;
        bool censored = false;
        for (uint64_t id : m_order)
        {
            const Obligation& o = m_ledger.at(id);
            if (o.service != service || o.generated_s < start || o.generated_s > end)
            {
                continue;
            }
            ++generated;
            if (o.delivered_s)
            {
                // Exactly at the deadline is on time.
                (*o.delivered_s <= o.deadline_s ? onTime : late)++;
            }
            else if (o.dropped)
            {
                ++lost;
            }
            else
            {
                ++pending;
                censored = censored || o.deadline_s > Now();
            }
        }
        json cohort = spec;
        cohort["generated"] = generated;
        cohort["delivered_on_time"] = onTime;
        cohort["delivered_late"] = late;
        cohort["lost"] = lost;
        cohort["pending"] = pending;
        cohort["duplicate_deliveries"] = 0;
        cohort["censored"] = censored;
        result.push_back(cohort);
    }
    json queues = json::object();
    for (const auto& [name, probe] : m_probes)
    {
        queues[name] = probe->Report();
    }
    for (const auto& site : m_sites)
    {
        // The LTE leg's queue is the RLC transmission buffer inside the stack, which
        // exposes no enqueue or dequeue trace. It is reported as not instrumented rather
        // than estimated.
        for (const char* direction : {"up", "down"})
        {
            queues[site.name + "/lte/" + direction] = {
                {"instrumented", false},
                {"reason", "the RLC transmission buffer exposes no queue trace"}};
        }
    }
    return {{"cohorts", result},
            {"queues", queues},
            {"accounting",
             {{"untraced_drops", m_untracedDrops},
              {"background_drops", m_backgroundDrops},
              {"probe_drops", m_probeDrops},
              {"competing_ues_now", m_competingNow},
              {"duplicate_deliveries", m_duplicates},
              {"disturbances_applied", m_disturbanceLog}}}};
}

// -- framing -----------------------------------------------------------------------------

bool
ReadFrame(std::string& frame)
{
    unsigned char header[4];
    if (!std::cin.read(reinterpret_cast<char*>(header), 4))
    {
        return false;
    }
    uint32_t length = (uint32_t(header[0]) << 24) | (uint32_t(header[1]) << 16) |
                      (uint32_t(header[2]) << 8) | uint32_t(header[3]);
    frame.resize(length);
    return bool(std::cin.read(frame.data(), length));
}

void
WriteFrame(const json& message)
{
    std::string body = message.dump();
    uint32_t length = body.size();
    unsigned char header[4] = {static_cast<unsigned char>(length >> 24),
                               static_cast<unsigned char>(length >> 16),
                               static_cast<unsigned char>(length >> 8),
                               static_cast<unsigned char>(length)};
    std::cout.write(reinterpret_cast<const char*>(header), 4);
    std::cout.write(body.data(), body.size());
    std::cout.flush();
}

} // namespace

int
main(int argc, char* argv[])
{
    std::ios::sync_with_stdio(false);
    World world;
    std::string frame;
    while (ReadFrame(frame))
    {
        json response = {{"build_id", ECORA_BUILD_ID}};
        try
        {
            json request = json::parse(frame);
            response["request_id"] = request.value("request_id", json());
            response["kind"] = request.value("kind", json());
            std::string kind = request.at("kind");
            json result;
            if (kind == "configure")
            {
                result = world.Configure(request);
            }
            else if (kind == "advance")
            {
                result = world.Advance(request);
            }
            else if (kind == "cohorts")
            {
                result = world.Cohorts(request);
            }
            else if (kind == "observe")
            {
                result = world.Observe(request);
            }
            else if (kind == "apply")
            {
                result = world.Apply(request);
            }
            else if (kind == "shutdown")
            {
                response["status"] = "ok";
                response["result"] = json::object();
                WriteFrame(response);
                break;
            }
            else
            {
                throw Refusal("unsupported_request",
                              "this simulator does not yet answer " + kind);
            }
            response["status"] = "ok";
            response["result"] = result;
        }
        catch (const Refusal& refusal)
        {
            response["status"] = "refused";
            response["reason"] = {{"code", refusal.code}, {"detail", refusal.what()}};
        }
        catch (const std::exception& error)
        {
            response["status"] = "refused";
            response["reason"] = {{"code", "malformed_request"}, {"detail", error.what()}};
        }
        WriteFrame(response);
    }
    Simulator::Destroy();
    return 0;
}
