# Input data schemas (column names only)

These headers were read from the one example CSV of each type in the user's
uploaded project. No original customer review text or product data is included.

## Reviews CSV

```csv
Review Count,Brand,Model,Product,Date,Review
```

## Raw aspect prediction CSV

```csv
review_id,sentence_id,window_id,context,aspect,aspect_key,sentiment,mapping_status,canonical_aspect,canonical_label,aspect_type,mapping_method,mapping_reason,laptop,source_file
```

`mapping_status` is `mapped`, `unmapped`, or `rejected`. The same column is used
in the raw pipeline outputs, v3 outputs, and correction-work prediction copies.

## Canonical aspect category CSV

```csv
canonical_aspect,canonical_label,aspect_type,description
```

See [Canonical aspect categorization and normalization](CANONICAL_ASPECT_MAPPING.md)
for Python interfaces, output filenames, and commands.

## Specifications CSV

```text
Brand, Model, Product Name, Product URL, Price ($), Image URL, Color,
Year of Release, Display Type, Screen Type, Screen Size, Screen Resolution,
Touch Screen, Refresh Rate, Brightness, Processor Brand, Processor Model,
Processor Model Number, Storage Type, Total Storage Capacity,
System Memory (RAM), Type of Memory (RAM), System Memory RAM Speed,
Number Of Memory Slots, Number of Memory Sticks Included, Graphics Type,
GPU Brand, Graphics, Operating System, Operating System Architecture,
Display Connector(s), Number of Thunderbolt Ports (Total), USB Ports,
Number of USB-C Charging Ports, Headphone Jack, Microphone Input,
Wireless Connectivity, Wireless Networking Standard, Number Of Ethernet Ports,
CPU Cooling System, Power Supply Maximum Wattage, Battery Life (up to),
Front-Facing Camera, Front Facing Camera Video Resolution, Built-In Microphone,
Product Height, Product Width, Product Depth, Product Weight
```
