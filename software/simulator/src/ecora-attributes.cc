// Export every registered TypeId and the initial value of each of its attributes, plus
// every global value, as one JSON document on standard output.
//
// This is the evidence behind the model manifest's "settings inherited from the pinned
// release": the values a model would take for anything a scenario does not set. It reads
// the attribute registry and nothing else. It builds no topology and runs no simulation.
//
// Each module whose types the v1 model uses is referenced below so that its library is
// linked, and its types registered, whatever the linker does with unreferenced libraries.
// The manifest assembly refuses a dump in which one of those groups is missing.

#include "ns3/applications-module.h"
#include "ns3/core-module.h"
#include "ns3/internet-module.h"
#include "ns3/lte-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/traffic-control-module.h"

#include <iostream>
#include <sstream>
#include <string>

using namespace ns3;

namespace
{

std::string
Quote(const std::string& text)
{
    std::ostringstream out;
    out << '"';
    for (unsigned char c : text)
    {
        switch (c)
        {
        case '"':
            out << "\\\"";
            break;
        case '\\':
            out << "\\\\";
            break;
        case '\n':
            out << "\\n";
            break;
        case '\r':
            out << "\\r";
            break;
        case '\t':
            out << "\\t";
            break;
        default:
            if (c < 0x20)
            {
                static const char* hex = "0123456789abcdef";
                out << "\\u00" << hex[c >> 4] << hex[c & 0xf];
            }
            else
            {
                out << c;
            }
        }
    }
    out << '"';
    return out.str();
}

std::string
Flags(uint32_t flags)
{
    std::string text;
    text += (flags & TypeId::ATTR_GET) ? "g" : "-";
    text += (flags & TypeId::ATTR_SET) ? "s" : "-";
    text += (flags & TypeId::ATTR_CONSTRUCT) ? "c" : "-";
    return text;
}

} // namespace

int
main(int argc, char* argv[])
{
    // Anchors: one type per module the v1 model draws on.
    TypeId anchors[] = {LteHelper::GetTypeId(),
                        PointToPointEpcHelper::GetTypeId(),
                        PointToPointNetDevice::GetTypeId(),
                        Ipv4L3Protocol::GetTypeId(),
                        UdpClient::GetTypeId(),
                        TrafficControlLayer::GetTypeId()};
    (void)anchors;

    std::ostream& out = std::cout;
    out << "{\"types\":[";
    bool firstType = true;
    for (uint16_t i = 0; i < TypeId::GetRegisteredN(); ++i)
    {
        TypeId tid = TypeId::GetRegistered(i);
        if (tid.MustHideFromDocumentation())
        {
            continue;
        }
        out << (firstType ? "" : ",") << "{\"name\":" << Quote(tid.GetName())
            << ",\"group\":" << Quote(tid.GetGroupName()) << ",\"parent\":"
            << Quote(tid.HasParent() ? tid.GetParent().GetName() : "") << ",\"attributes\":[";
        for (std::size_t j = 0; j < tid.GetAttributeN(); ++j)
        {
            TypeId::AttributeInformation info = tid.GetAttribute(j);
            std::string value = info.initialValue->SerializeToString(info.checker);
            // A pointer default serialises as an address, which changes from process to
            // process and says nothing about the model. What it points to is the setting.
            if (auto pointer = dynamic_cast<const PointerValue*>(PeekPointer(info.initialValue)))
            {
                Ptr<Object> target = pointer->Get<Object>();
                value = target ? "object:" + target->GetInstanceTypeId().GetName() : "null";
            }
            out << (j ? "," : "") << "{\"name\":" << Quote(info.name)
                << ",\"value\":" << Quote(value)
                << ",\"type\":" << Quote(info.checker->GetValueTypeName())
                << ",\"flags\":" << Quote(Flags(info.flags))
                << ",\"support\":" << Quote(info.supportLevel == TypeId::SUPPORTED    ? "supported"
                                            : info.supportLevel == TypeId::DEPRECATED ? "deprecated"
                                                                                      : "obsolete")
                << "}";
        }
        out << "]}";
        firstType = false;
    }
    out << "],\"globals\":[";
    bool first = true;
    for (auto i = GlobalValue::Begin(); i != GlobalValue::End(); ++i)
    {
        StringValue value;
        (*i)->GetValue(value);
        out << (first ? "" : ",") << "{\"name\":" << Quote((*i)->GetName())
            << ",\"value\":" << Quote(value.Get()) << "}";
        first = false;
    }
    out << "]}\n";
    return 0;
}
