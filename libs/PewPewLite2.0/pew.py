from micropython import const
import board
import busio
import time
import sys


_FONT = (
    b'{{{{{{wws{w{HY{{{{YDYDY{sUtGUsH[wyH{uHgHE{ws{{{{vyxyv{g[K[g{{]f]{{{wDw{{'
    b'{{{wy{{{D{{{{{{{w{K_w}x{VHLHe{wuwww{`KfyD{UKgKU{w}XDK{DxTKT{VxUHU{D[wyx{'
    b'UHfHU{UHEKe{{w{w{{{w{wy{KwxwK{{D{D{{xwKwx{eKg{w{VIHyB{fYH@H{dHdHd{FyxyF{'
    b'`XHX`{DxtxD{Dxtxx{FyxIF{HHDHH{wwwww{KKKHU{HXpXH{xxxxD{Y@DLH{IL@LX{fYHYf{'
    b'`HH`x{fYHIF{`HH`H{UxUKU{Dwwww{HHHIR{HHH]w{HHLD@{HYsYH{HYbww{D[wyD{txxxt{'
    b'x}w_K{GKKKG{wLY{{{{{{{{Dxs{{{{{BIIB{x`XX`{{ByyB{KBIIB{{WIpF{OwUwww{`YB[`'
    b'x`XHH{w{vwc{K{OKHUxHpXH{vwws_{{dD@H{{`XHH{{fYYf{{`XX`x{bYIBK{Ipxx{{F}_d{'
    b'wUws_{{HHIV{{HH]s{{HLD@{{HbbH{{HHV[a{D_}D{Cw|wC{wwwwwwpwOwp{WKfxu{@YYY@{'
)
_SALT = const(132)


K_X = 0x01
K_DOWN = 0x02
K_LEFT = 0x04
K_RIGHT = 0x08
K_UP = 0x10
K_O = 0x20

_i2c = None


def brightness(level):
    global _buffer, _i2c

    _buffer[0] = 0xe0 | level & 0x0f
    _i2c.writeto(0x70, _buffer, end=1)


def show(image, dx=0, dy=0):
    global _buffer, _i2c

    pixel = image.pixel
    _buffer[0] = 0x00
    for x in range(8):
        b = 0
        for y in range(8):
            color = pixel(x - dx, y - dy)
            if color & 0x01:
                b |= 0x01 << (15 - y)
            if color & 0x02:
                b |= 0x01 << y
        _buffer[15 - x * 2] = b
        _buffer[16 - x * 2] = b >> 8
    _i2c.writeto(0x70, _buffer)


def keys():
    global _buffer, _i2c
    global _last_keys, _keys

    now = time.monotonic()
    if now - _last_keys < 0.01:
        return _keys
    _last_keys = now

    _temp[0] = 0x40
    _i2c.writeto(0x70, _temp, end=1, stop=False)
    _i2c.readfrom_into(0x70, _temp)
    _keys = int.from_bytes(_temp, 'little') >> 5
    if _keys == 0b111111:
        sys.exit()
    return _keys


def tick(delay):
    global _tick

    _tick += delay
    time.sleep(max(0, _tick - time.monotonic()))


class Pix:
    def __init__(self, width=8, height=8, buffer=None):
        if buffer is None:
            buffer = bytearray(width * height)
        self.buffer = buffer
        self.width = width
        self.height = height

    @classmethod
    def from_text(cls, string, color=None, bgcolor=0, colors=None):
        pix = cls(4 * len(string), 6)
        font = memoryview(_FONT)
        if colors is None:
            if color is None:
                colors = (3, 2, bgcolor, bgcolor)
            else:
                colors = (color, color, bgcolor, bgcolor)
        x = 0
        for c in string:
            index = ord(c) - 0x20
            if not 0 <= index <= 95:
                continue
            row = 0
            for byte in font[index * 6:index * 6 + 6]:
                unsalted = byte ^ _SALT
                for col in range(4):
                    pix.pixel(x + col, row, colors[unsalted & 0x03])
                    unsalted >>= 2
                row += 1
            x += 4
        return pix

    @classmethod
    def from_iter(cls, lines):
        pix = cls(len(lines[0]), len(lines))
        y = 0
        for line in lines:
            x = 0
            for pixel in line:
                pix.pixel(x, y, pixel)
                x += 1
            y += 1

    def pixel(self, x, y, color=None):
        if not 0 <= x < self.width or not 0 <= y < self.height:
            return 0
        index = x + y * self.width
        if color is None:
            return self.buffer[index]
        self.buffer[index] = color

    def box(self, color, x=0, y=0, width=None, height=None):
        x = min(max(x, 0), self.width - 1)
        y = min(max(y, 0), self.height - 1)
        width = max(0, min(width or self.width, self.width - x))
        height = max(0, min(height or self.height, self.height - y))
        for y in range(y, y + height):
            xx = y * self.width + x
            for i in range(width):
                self.buffer[xx] = color
                xx += 1

    def blit(self, source, dx=0, dy=0, x=0, y=0,
             width=None, height=None, key=None):
        if dx < 0:
            x -= dx
            dx = 0
        if x < 0:
            dx -= x
            x = 0
        if dy < 0:
            y -= dy
            dy = 0
        if y < 0:
            dy -= y
            y = 0
        width = min(min(width or source.width, source.width - x),
                    self.width - dx)
        height = min(min(height or source.height, source.height - y),
                     self.height - dy)
        for row in range(height):
            xx = y * source.width + x
            dxx = dy * self.width + dx
            for col in range(width):
                color = source.buffer[xx]
                if color != key:
                    self.buffer[dxx] = color
                dxx += 1
                xx += 1
            y += 1
            dy += 1

    def __str__(self):
        return "\n".join(
            "".join(
                ('.', '+', '*', '@')[self.pixel(x, y)]
                for x in range(self.width)
            )
            for y in range(self.height)
        )


def init():
    global _i2c, _buffer, _temp, _keys, _last_keys, _tick

    if _i2c is not None:
        return

    _i2c = busio.I2C(sda=board.SDA, scl=board.SCL)
    _i2c.try_lock()
    _buffer = bytearray(17)
    _temp = bytearray(2)
    _keys = 0
    _last_keys = 0
    _tick = time.monotonic()

    _buffer[0] = 0x21
    try:
        _i2c.writeto(0x70, _buffer, end=1)
    except OSError:
        raise RuntimeError("PewPew Lite board not found")

    _buffer[0] = 0x81
    _i2c.writeto(0x70, _buffer, end=1)

    brightness(7)
