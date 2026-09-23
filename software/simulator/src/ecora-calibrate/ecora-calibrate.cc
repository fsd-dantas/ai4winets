// Measure what the LTE leg delivers under a given extra path loss, in one direction.
//
// The leg is built by the same code the simulator process uses (ecora-sim/lte-leg.h), from
// a scenario file's LTE leg, so the measurement is of the leg the simulator runs. One
// process measures one point: a loss, a direction and a random run. It saturates the leg
// with UDP well above what the configured bandwidth can carry, counts application payload
// bytes received inside a window that starts after attach, and prints one JSON line.
//
//   ecora-calibrate --scenario=FILE --loss=DB --direction=up|down [--run=N]
//                   [--start=S] [--stop=S] [--payload=BYTES] [--offered=BPS]
//
// It measures delivered capacity under saturation, which is what the finite world's
// loss-to-rate table stands for. It does not measure latency, fairness between flows or
// behaviour under the study's actual workloads.

#include "../ecora-sim/build-id.h"
#include "../ecora-sim/lte-leg.h"

#include "ns3/applications-module.h"

#include <fstream>
#include <iostream>

using namespace ns3;

namespace
{
uint64_t g_received = 0;
double g_start = 1.0;
double g_stop = 6.0;

void
Received(Ptr<const Packet> packet, const Address&)
{
    double now = Simulator::Now().GetSeconds();
    if (now >= g_start && now < g_stop)
    {
        g_received += packet->GetSize();
    }
}
} // namespace

int
main(int argc, char* argv[])
{
    std::string scenarioPath;
    std::string direction = "up";
    double loss = 0;
    uint32_t run = 1;
    uint32_t payload = 544; // the 32-byte envelope plus a 512-byte reading or response
    double offered = 0;
    uint32_t competitors = 0;
    CommandLine cmd;
    cmd.AddValue("competitors",
                 "competing UEs at the site's position, each saturating the same direction",
                 competitors);
    cmd.AddValue("scenario", "scenario file whose LTE leg is measured", scenarioPath);
    cmd.AddValue("loss", "extra path loss in dB on the site's link", loss);
    cmd.AddValue("direction", "up (site to centre) or down", direction);
    cmd.AddValue("run", "RngRun", run);
    cmd.AddValue("start", "measurement window start, s", g_start);
    cmd.AddValue("stop", "measurement window end, s", g_stop);
    cmd.AddValue("payload", "UDP payload bytes per datagram", payload);
    cmd.AddValue("offered", "offered load, bit/s (default: twice the leg's ceiling)", offered);
    cmd.Parse(argc, argv);
    NS_ABORT_MSG_IF(direction != "up" && direction != "down", "direction is up or down");

    // "-" reads the scenario from standard input, so a caller on another filesystem does
    // not have to translate a path.
    nlohmann::json scenario;
    if (scenarioPath == "-")
    {
        scenario = nlohmann::json::parse(std::cin);
    }
    else
    {
        std::ifstream file(scenarioPath);
        NS_ABORT_MSG_IF(!file, "cannot read " << scenarioPath);
        scenario = nlohmann::json::parse(file);
    }
    const nlohmann::json* lte = nullptr;
    for (const auto& leg : scenario.at("topology").at("legs"))
    {
        if (leg.at("kind") == "lte")
        {
            lte = &leg;
        }
    }
    NS_ABORT_MSG_IF(!lte, "the scenario declares no LTE leg");
    std::string site = scenario.at("topology").at("sites").at(0);
    // Saturation: comfortably above what 25 resource blocks can carry in either direction.
    if (offered <= 0)
    {
        offered = direction == "down" ? 40e6 : ecora::COMPETITOR_OFFERED_BPS;
    }
    NS_ABORT_MSG_IF(competitors > ecora::MAX_COMPETITORS,
                    "more competitors than the model's valid range");

    RngSeedManager::SetSeed(1);
    RngSeedManager::SetRun(run);

    // The measured gateway is UE 0. Competitors share its position and channel, carry no
    // extra loss, and load the same direction; they stand for other users of the cell.
    NodeContainer ues;
    ues.Create(1 + competitors);
    NodeContainer gateway(ues.Get(0));
    ecora::LteLeg leg =
        ecora::BuildLteLeg(*lte, ues, std::vector<std::string>(1 + competitors, site));
    leg.SetExtraLoss(0, loss);

    Ptr<Node> remote = CreateObject<Node>();
    InternetStackHelper().Install(remote);
    PointToPointHelper core;
    core.SetDeviceAttribute("DataRate", StringValue("100Mbps"));
    core.SetChannelAttribute("Delay", StringValue("1ms"));
    NetDeviceContainer devices = core.Install(leg.epc->GetPgwNode(), remote);
    Ipv4AddressHelper addresses;
    addresses.SetBase("10.1.0.0", "255.255.255.252");
    Ipv4InterfaceContainer assigned = addresses.Assign(devices);
    Ipv4StaticRoutingHelper routing;
    routing.GetStaticRouting(remote->GetObject<Ipv4>())
        ->AddNetworkRouteTo("7.0.0.0", "255.0.0.0", assigned.GetAddress(0), 1);
    for (uint32_t i = 0; i < ues.GetN(); ++i)
    {
        routing.GetStaticRouting(ues.Get(i)->GetObject<Ipv4>())
            ->SetDefaultRoute(leg.epc->GetUeDefaultGatewayAddress(), 1);
    }

    bool up = direction == "up";
    Ptr<Node> sender = up ? gateway.Get(0) : remote;
    Ptr<Node> receiver = up ? remote : gateway.Get(0);
    Ipv4Address to = up ? assigned.GetAddress(1) : leg.ueAddresses.GetAddress(0);
    uint16_t port = 9000;

    PacketSinkHelper sink("ns3::UdpSocketFactory", InetSocketAddress(Ipv4Address::GetAny(), port));
    ApplicationContainer sinks = sink.Install(receiver);
    sinks.Start(Seconds(0));
    DynamicCast<PacketSink>(sinks.Get(0))->TraceConnectWithoutContext("Rx", MakeCallback(&Received));

    UdpClientHelper source(to, port);
    source.SetAttribute("MaxPackets", UintegerValue(0));
    source.SetAttribute("PacketSize", UintegerValue(payload));
    source.SetAttribute("Interval", TimeValue(Seconds(8.0 * payload / offered)));
    ApplicationContainer sources = source.Install(sender);
    // Start after attach; the window starts later still.
    sources.Start(Seconds(0.2));
    // Competing load on its own port, so it never reaches the measured sink.
    for (uint32_t i = 1; i < ues.GetN(); ++i)
    {
        Ptr<Node> from = up ? ues.Get(i) : remote;
        Ipv4Address toward = up ? assigned.GetAddress(1) : leg.ueAddresses.GetAddress(i);
        UdpClientHelper load(toward, port + 1);
        load.SetAttribute("MaxPackets", UintegerValue(0));
        load.SetAttribute("PacketSize", UintegerValue(payload));
        load.SetAttribute("Interval", TimeValue(Seconds(8.0 * payload / offered)));
        load.Install(from).Start(Seconds(0.2));
    }

    Simulator::Stop(Seconds(g_stop));
    Simulator::Run();
    Simulator::Destroy();

    // UdpClient writes a 12-byte sequence header inside the payload it was asked for, so
    // received payload bytes are the application bytes delivered.
    double goodput = 8.0 * g_received / (g_stop - g_start);
    // The LTE leg is built by the simulator's own code, so the simulator's identity is the
    // identity of what was measured.
    nlohmann::json point = {{"build_id", ECORA_BUILD_ID},
                            {"loss_db", loss},
                            {"competitors", competitors},
                            {"direction", direction},
                            {"goodput_bps", goodput},
                            {"received_bytes", g_received},
                            {"offered_bps", offered},
                            {"payload_bytes", payload},
                            {"window_s", {g_start, g_stop}},
                            {"rng_run", run}};
    std::cout << point.dump() << std::endl;
    return 0;
}
