# Device Listing Details

## StarTech HDMI2VGA

Reference:
- https://www.startech.com/en-eu/audio-video-products/hdmi2vga

Relevant notes:
- Active converter (not passive cable behavior).
- HDMI/DVI to VGA conversion.
- EDID behavior can influence upstream mode selection.

## OSSC Unit (BitFunx XLL-OSSC, HW 1.8)

Listing:
- https://www.aliexpress.us/item/3256807770139411.html

Firmware project:
- https://github.com/e8root/voidscaler

Recorded listing specs:
- Brand: BitFunx
- Model: XLL-OSSC
- HW revision: 1.8
- Inputs: RGB SCART, Component/YPbPr, VGA (D-Sub15)
- Output: HDMI
- Power: 5V adapter (listing references 1A minimum; package note shows 5V/1.5A)
- Firmware update: MicroSD

Listing caveat:
- AliExpress revision/firmware/accessory bundles can vary by batch.
- Use measured behavior in this project as source of truth if listing claims differ.

## HDMI-to-YPbPr Converter (HDmatters HD2YPBPR)

Listing:
- https://www.aliexpress.us/item/3256805444134465.html

Recorded listing specs:
- Brand: HDmatters
- Model: HD2YPBPR
- Direction: HDMI in -> YPbPr out only
- Input: 1x HDMI
- Outputs: YPbPr video + stereo RCA audio + digital coax audio
- HDMI input resolutions listed: 480p, 576i/p, 720p, 1080i, 1080p
- YPbPr output resolutions listed: 480p/60, 576p/60, 720p 50/60, 1080p 50/60

Important listing limitations:
- No downscaler.
- No HDCP decoding.
- No deep-color support.
- Not composite-compatible.
- Does not support 480i and lower on this model.
