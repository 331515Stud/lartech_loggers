import base64

def base64_to_hex(base64_string):
    try:
        decoded_bytes = base64.b64decode(base64_string)
        return ''.join(f"{byte:02X}" for byte in decoded_bytes)
    except Exception as e:
        print(f"Base64 decode error: {e}")
        return ""

def hex_to_signed_decimal(hex_str):
    num = int(hex_str, 16)
    if len(hex_str) >= 6 and (num & (1 << (len(hex_str) * 4 - 1))):
        num -= 1 << (len(hex_str) * 4)
    return num

def reverse_bytes_order(hex_str):
    return ''.join([hex_str[i-2:i] for i in range(len(hex_str), 0, -2)])
