import os
import sys
import zlib
import time
import base64
import marshal
import py_compile
import random
import secrets
import string

# Configuration
a = random.randint(50, 70)
_input = "raw_input('%s')" if sys.version_info[0] == 2 else "input('%s')"

# Encoding functions
zlb = lambda in_ : zlib.compress(in_)
b16 = lambda in_ : base64.b16encode(in_)
b32 = lambda in_ : base64.b32encode(in_)
b64 = lambda in_ : base64.b64encode(in_)
mar = lambda in_ : marshal.dumps(compile(in_,'<x>','exec'))


def _random_name(length=2):
    """Return a random identifier (letter + alnum) to avoid fixed decoder signatures."""
    return ''.join(secrets.choice(string.ascii_lowercase) for _ in range(length))


def _random_decoder_b64():
    """Build a decoder line with random variable names and one of several equivalent forms."""
    dec_var = _random_name(random.randint(2, 4))
    arg_var = _random_name(random.randint(2, 4))
    while arg_var == dec_var:
        arg_var = _random_name(random.randint(2, 4))
    style = random.randint(0, 2)
    if style == 0:
        # Lambda with __import__ inline
        return (
            f"{dec_var} = lambda {arg_var} : __import__('zlib').decompress(__import__('base64').b64decode({arg_var}[::-1]));",
            dec_var,
        )
    if style == 1:
        # Two-step: modules then lambda
        z = _random_name(1)
        b = _random_name(1)
        return (
            f"{z}=__import__('zlib');{b}=__import__('base64');{dec_var}=lambda {arg_var}:{z}.decompress({b}.b64decode({arg_var}[::-1]));",
            dec_var,
        )
    # getattr form
    m = _random_name(1)
    return (
        f"{m}=__import__('base64');{dec_var}=lambda {arg_var}:__import__('zlib').decompress(getattr({m},'b64decode')({arg_var}[::-1]));",
        dec_var,
    )


class FileSize:
    def datas(self,z):
        for x in ['Byte','KB','MB','GB']:
            if z < 1024.0:
                return "%3.1f %s" % (z,x)
            z /= 1024.0
    def __init__(self,path):
        if os.path.isfile(path):
            dts = os.stat(path).st_size
            print('\n')
            print(" [-] Encoded File Size : %s\n" % self.datas(dts))

def Encode(data, output):
    """
    Encode data with multiple layers of base64/zlib compression.
    Uses randomized decoder variable names to reduce static signatures.
    """
    loop = int(eval(str(a)))
    decoder_line, dec_var = _random_decoder_b64()
    x_encode = "b64(zlb(data.encode('utf8')))[::-1]"
    for x in range(loop):
        try:
            data = "exec((%s)(%s))" % (dec_var, repr(eval(x_encode)))
        except TypeError as s:
            sys.exit(" TypeError : " + str(s))
    final_code = decoder_line + "\n" + data
    with open(output, 'w') as f:
        f.write(final_code)
        f.close()

def SEncode(data,output):
    for x in range(5):
        method = repr(b64(zlb(mar(data.encode('utf8'))))[::-1])
        data = "exec(__import__('marshal').loads(__import__('zlib').decompress(__import__('base64').b64decode(%s[::-1]))))" % method
    z = []
    for i in data:
        z.append(ord(i))
    sata = "_ = %s\nexec(''.join(chr(__) for __ in _))" % z
    with open(output, 'w') as f:
        f.write("exec(str(chr(35)%s));" % '+chr(1)'*10000)
        f.write(sata)
        f.close()
    py_compile.compile(output,output)

def MainMenu(file, random_suffix=False):
    """
    Obfuscate a Python file. Optionally use a random output suffix to reduce filename signatures.
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
    Encode(data, output)
    FileSize(output)
    return output


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python obfuscator.py <file.py>")
    MainMenu(sys.argv[1])