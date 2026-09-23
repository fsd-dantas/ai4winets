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
#include <iostream>
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
    READING = 3
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
    std::deque<uint64_t> held;
    bool releasing = false;
    double extraLossDb = 0;
};

// -- the world ---------------------------------------------------------------------------

class World
{
  public:
    json Configure(const json& request);
    json Advance(const json& request);
    json Cohorts(const json& request);

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
    Route();
    Schedule();
    m_configured = true;
    return Resolved();
}

void
World::BuildLte(const json& leg)
{
    const json& radio = leg.at("radio");
    // Set explicitly. With an EPC attached, ns-3 silently replaces its RLC_SM_ALWAYS
    // default by RLC_UM_ALWAYS; saying so here keeps the manifest's inherited default from
    // being mistaken for the mode that runs.
    Config::SetDefault("ns3::LteEnbRrc::EpsBearerToRlcMapping",
                       EnumValue(LteEnbRrc::RLC_UM_ALWAYS));
    Config::SetDefault("ns3::LteRlcUm::MaxTxBufferSize",
                       UintegerValue(leg.at("queue_limit_bytes").get<uint32_t>()));
    Config::SetDefault("ns3::LteEnbPhy::TxPower", DoubleValue(radio.at("enb_tx_dbm")));
    Config::SetDefault("ns3::LteUePhy::TxPower", DoubleValue(radio.at("ue_tx_dbm")));
    Config::SetDefault("ns3::LteEnbPhy::NoiseFigure",
                       DoubleValue(radio.at("enb_noise_figure_db")));
    Config::SetDefault("ns3::LteUePhy::NoiseFigure",
                       DoubleValue(radio.at("ue_noise_figure_db")));

    m_lte = CreateObject<LteHelper>();
    m_epc = CreateObject<PointToPointEpcHelper>();
    m_lte->SetEpcHelper(m_epc);
    m_lte->SetSchedulerType("ns3::PfFfMacScheduler");
    m_lte->SetPathlossModelType(TypeId::LookupByName("ns3::FriisSpectrumPropagationLossModel"));
    m_lte->SetEnbDeviceAttribute("DlBandwidth", UintegerValue(radio.at("dl_bandwidth_rb")));
    m_lte->SetEnbDeviceAttribute("UlBandwidth", UintegerValue(radio.at("ul_bandwidth_rb")));
    m_lte->SetEnbDeviceAttribute("DlEarfcn", UintegerValue(radio.at("dl_earfcn")));
    m_lte->SetEnbDeviceAttribute("UlEarfcn", UintegerValue(radio.at("ul_earfcn")));
    m_lte->SetUeDeviceAttribute("DlEarfcn", UintegerValue(radio.at("dl_earfcn")));

    m_enb = CreateObject<Node>();
    MobilityHelper mobility;
    mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    mobility.Install(m_enb);
    const json& enbAt = radio.at("enb_position_m");
    m_enb->GetObject<MobilityModel>()->SetPosition(Vector(enbAt[0], enbAt[1], enbAt[2]));
    NodeContainer gateways;
    for (auto& site : m_sites)
    {
        mobility.Install(site.gateway);
        const json& at = radio.at("site_positions_m").at(site.name);
        site.mobility = site.gateway->GetObject<MobilityModel>();
        site.mobility->SetPosition(Vector(at[0], at[1], at[2]));
        gateways.Add(site.gateway);
    }

    NetDeviceContainer enbDevices = m_lte->InstallEnbDevice(NodeContainer(m_enb));
    m_enbDevice = enbDevices.Get(0);
    NetDeviceContainer ueDevices = m_lte->InstallUeDevice(gateways);

    // Per-site radio impairment: extra loss on one site's link, zero until disturbed. It
    // sits beside the Friis spectrum model, which LteHelper installed on the spectrum slot.
    m_radioLoss = CreateObject<MatrixPropagationLossModel>();
    m_radioLoss->SetDefaultLoss(0);
    m_lte->GetDownlinkSpectrumChannel()->AddPropagationLossModel(m_radioLoss);
    m_lte->GetUplinkSpectrumChannel()->AddPropagationLossModel(m_radioLoss);
    Ptr<MobilityModel> enbMobility = m_enb->GetObject<MobilityModel>();
    for (auto& site : m_sites)
    {
        m_radioLoss->SetLoss(site.mobility, enbMobility, 0, true);
    }

    InternetStackHelper internet;
    internet.Install(gateways);
    Ipv4InterfaceContainer ueAddresses = m_epc->AssignUeIpv4Address(ueDevices);
    for (uint32_t i = 0; i < m_sites.size(); ++i)
    {
        m_sites[i].lteDevice = ueDevices.Get(i);
        m_sites[i].lteAddress = ueAddresses.GetAddress(i);
    }
    m_lte->Attach(ueDevices, m_enbDevice);
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
World::WatchBearers()
{
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
    if (kind == "radio_loss")
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
            {"disturbances_scheduled", m_scenario.at("disturbances").size()},
            {"unsupported_requests", {"observe", "apply", "truth", "fork"}}};
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
    return {{"cohorts", result},
            {"accounting",
             {{"untraced_drops", m_untracedDrops},
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
