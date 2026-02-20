# Component Roles

## PC

- Source device.
- Generates base video timing/resolution (currently 1280 x 960).
- Source scaling/aspect/refresh affects all downstream stages.

## StarTech HDMI2VGA

- Active HDMI-to-analog conversion stage.
- Converts HDMI/DVI signal to VGA output.
- EDID/format negotiation at this stage can affect timing selected upstream.

## OSSC (VoidScaler firmware)

- Main low-latency processing/scaling stage.
- Handles timing transitions and output mode shaping.
- Likely major contributor to effective active-area and edge behavior in this setup.

## HDMI-to-YPbPr Converter (HD2YPBPR)

- Final digital-to-analog conversion into component video for CRT.
- Can be a compatibility gate based on source resolution/format settings.

## Sony Trinitron CRT

- Model: KV-27FV300 (27-inch)
- CRT Database reference: https://crtdatabase.com/crts/sony/sony-kv-27fv300
- Final analog display stage.
- Native geometry/overscan behavior is most visible at outer edges.
