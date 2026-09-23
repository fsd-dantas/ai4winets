// The LTE leg, built one way for every program that needs one.
//
// The simulator process and the calibration program both build it from here, so what the
// calibration measures is the leg the simulator runs, not a second construction of it that
// could drift. Everything comes from the scenario's leg declaration and the gateways passed
// in; nothing is chosen here.

#pragma once

#include "json.hpp"

#include "ns3/core-module.h"
#include "ns3/internet-module.h"
#include "ns3/lte-module.h"
#include "ns3/mobility-module.h"
#include "ns3/network-module.h"
#include "ns3/point-to-point-module.h"

#include <string>
#include <vector>

namespace ecora
{

// Cell congestion: each competing UE shares a site's position and radio conditions, carries
// no extra loss, and offers this much uplink load in datagrams of this size, which is
// saturating at any share the cell can give it. The simulator and the calibration use the
// same values, so a measured load-to-rate entry describes the load the simulator applies.
constexpr double COMPETITOR_OFFERED_BPS = 20e6;
constexpr uint32_t COMPETITOR_PAYLOAD_BYTES = 544;
// The model's valid range. Measured: a site's share falls smoothly to 35 competitors and is
// zero at 40, where the cell stops admitting UEs. Beyond this the model is not the cell the
// scenario means, so a larger load is refused rather than run.
constexpr uint32_t MAX_COMPETITORS = 35;

struct LteLeg
{
    ns3::Ptr<ns3::LteHelper> lte;
    ns3::Ptr<ns3::PointToPointEpcHelper> epc;
    ns3::Ptr<ns3::Node> enb;
    ns3::Ptr<ns3::NetDevice> enbDevice;
    ns3::NetDeviceContainer ueDevices;
    ns3::Ipv4InterfaceContainer ueAddresses;
    // Per-site radio impairment: extra loss on one site's link, zero until disturbed. It
    // sits beside the Friis spectrum model, which LteHelper installs on the spectrum slot.
    ns3::Ptr<ns3::MatrixPropagationLossModel> radioLoss;
    std::vector<ns3::Ptr<ns3::MobilityModel>> siteMobility;

    void SetExtraLoss(uint32_t site, double db)
    {
        radioLoss->SetLoss(siteMobility.at(site), enb->GetObject<ns3::MobilityModel>(), db, true);
    }
};

// Build the leg for these gateways, which become the UEs, named in the same order as the
// scenario's site_positions_m keys they are positioned from. Installs the internet stack
// on the gateways, assigns their LTE addresses and attaches them.
inline LteLeg
BuildLteLeg(const nlohmann::json& leg,
            ns3::NodeContainer gateways,
            const std::vector<std::string>& names)
{
    using namespace ns3;
    const nlohmann::json& radio = leg.at("radio");
    // Set explicitly. With an EPC attached, ns-3 silently replaces its RLC_SM_ALWAYS
    // default by RLC_UM_ALWAYS; saying so here keeps the manifest's inherited default from
    // being mistaken for the mode that runs.
    Config::SetDefault("ns3::LteEnbRrc::EpsBearerToRlcMapping",
                       EnumValue(LteEnbRrc::RLC_UM_ALWAYS));
    Config::SetDefault("ns3::LteRlcUm::MaxTxBufferSize",
                       UintegerValue(leg.at("queue_limit_bytes").get<uint32_t>()));
    Config::SetDefault("ns3::LteEnbPhy::TxPower", DoubleValue(radio.at("enb_tx_dbm")));
    Config::SetDefault("ns3::LteUePhy::TxPower", DoubleValue(radio.at("ue_tx_dbm")));
    Config::SetDefault("ns3::LteEnbPhy::NoiseFigure", DoubleValue(radio.at("enb_noise_figure_db")));
    Config::SetDefault("ns3::LteUePhy::NoiseFigure", DoubleValue(radio.at("ue_noise_figure_db")));

    LteLeg built;
    built.lte = CreateObject<LteHelper>();
    built.epc = CreateObject<PointToPointEpcHelper>();
    built.lte->SetEpcHelper(built.epc);
    built.lte->SetSchedulerType("ns3::PfFfMacScheduler");
    built.lte->SetPathlossModelType(TypeId::LookupByName("ns3::FriisSpectrumPropagationLossModel"));
    built.lte->SetEnbDeviceAttribute("DlBandwidth", UintegerValue(radio.at("dl_bandwidth_rb")));
    built.lte->SetEnbDeviceAttribute("UlBandwidth", UintegerValue(radio.at("ul_bandwidth_rb")));
    built.lte->SetEnbDeviceAttribute("DlEarfcn", UintegerValue(radio.at("dl_earfcn")));
    built.lte->SetEnbDeviceAttribute("UlEarfcn", UintegerValue(radio.at("ul_earfcn")));
    built.lte->SetUeDeviceAttribute("DlEarfcn", UintegerValue(radio.at("dl_earfcn")));

    built.enb = CreateObject<Node>();
    MobilityHelper mobility;
    mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    mobility.Install(built.enb);
    const nlohmann::json& enbAt = radio.at("enb_position_m");
    built.enb->GetObject<MobilityModel>()->SetPosition(Vector(enbAt[0], enbAt[1], enbAt[2]));
    for (uint32_t i = 0; i < gateways.GetN(); ++i)
    {
        mobility.Install(gateways.Get(i));
        const nlohmann::json& at = radio.at("site_positions_m").at(names.at(i));
        Ptr<MobilityModel> placed = gateways.Get(i)->GetObject<MobilityModel>();
        placed->SetPosition(Vector(at[0], at[1], at[2]));
        built.siteMobility.push_back(placed);
    }

    built.enbDevice = built.lte->InstallEnbDevice(NodeContainer(built.enb)).Get(0);
    built.ueDevices = built.lte->InstallUeDevice(gateways);

    built.radioLoss = CreateObject<MatrixPropagationLossModel>();
    built.radioLoss->SetDefaultLoss(0);
    built.lte->GetDownlinkSpectrumChannel()->AddPropagationLossModel(built.radioLoss);
    built.lte->GetUplinkSpectrumChannel()->AddPropagationLossModel(built.radioLoss);
    for (uint32_t i = 0; i < gateways.GetN(); ++i)
    {
        built.SetExtraLoss(i, 0);
    }

    InternetStackHelper internet;
    internet.Install(gateways);
    built.ueAddresses = built.epc->AssignUeIpv4Address(built.ueDevices);
    built.lte->Attach(built.ueDevices, built.enbDevice);
    return built;
}

} // namespace ecora
