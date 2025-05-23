from .conversion import base64_to_hex, reverse_bytes_order, hex_to_signed_decimal

def ADC_Scale(raw, fullScaleVolts, rawMax):
    return ((raw >> 2) * fullScaleVolts) / rawMax

def process_points_data(base64_points):
    streams = [[] for _ in range(6)]
    ADC_full_scale_V = 0.93
    ADC_raw_max = (1 << 21)

    result = base64_to_hex(base64_points)
    if not result or len(result) < 6:
        print("Недостаточно данных")
        return streams

    npoints = int(reverse_bytes_order(result[2:6]), 16)
    result = result[6:]

    while len(result) >= 12 * 1:
        for i in range(6):
            value_hex = result[i * 6: (i + 1) * 6]
            if not value_hex:
                break
            value = hex_to_signed_decimal(reverse_bytes_order(value_hex))
            streams[i].append(value)
        result = result[36:]

    for j in range(6):
        for i in range(len(streams[j])):
            streams[j][i] = -(ADC_Scale(streams[j][i], ADC_full_scale_V, ADC_raw_max) * 24000) / 25000

    return streams
