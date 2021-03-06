from micropython import const
import board
import busio
import time
import digitalio
import samd

_PALETTE = b'\x00\x00\xff\x00\x00\xff\xff\xff\x11\x11\x44\x00\x00\x44\x44\x44'
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

K_X = const(0x01)
K_DOWN = const(0x02)
K_LEFT = const(0x04)
K_RIGHT = const(0x08)
K_UP = const(0x10)
K_O = const(0x20)

_i2c = None
_buffer = None
SLICES = True


def brightness(level):
    level = min(255, max(0, level * 16 + 16))
    _register(0x03, 0x01, level)


def show(pix):
    buffer = pix.buffer
    width = pix.width
    _register(0x01, 0x00)
    for x in range(8):
        position = 7 - x
        _buffer[0] = x * 16
        for y in range(7, -1, -1):
            color = buffer[position]
            position += width
            _buffer[y + 1] = _PALETTE[color * 2]
            _buffer[y + 9] = _PALETTE[color * 2 + 1]
        _i2c.writeto(0x50, _buffer)


def keys():
    return samd.get_buttons()


def tick(delay):
    global _tick

    _tick += delay
    time.sleep(max(0, _tick - time.monotonic()))


class GameOver(Exception):
    pass


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
                colors = (3, 7, 4, bgcolor)
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
        return pix

    def pixel(self, x, y, color=None):
        if not 0 <= x < self.width or not 0 <= y < self.height:
            return 0
        if color is None:
            return self.buffer[x + y * self.width]
        self.buffer[x + y * self.width] = color

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
        source_buffer = memoryview(source.buffer)
        self_buffer = self.buffer
        if key is None and SLICES:
            for row in range(height):
                xx = y * source.width + x
                dxx = dy * self.width + dx
                self_buffer[dxx:dxx + width] = source_buffer[xx:xx + width]
                y += 1
                dy += 1
        else:
            for row in range(height):
                xx = y * source.width + x
                dxx = dy * self.width + dx
                for col in range(width):
                    color = source_buffer[xx]
                    if color != key:
                        self_buffer[dxx] = color
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


def _register(page, register, value=None):
    global _page, _temp

    if page != _page:
        _temp[0] = 0xfe
        _temp[1] = 0xc5
        _i2c.writeto(0x50, _temp)
        _temp[0] = 0xfd
        _temp[1] = page
        _i2c.writeto(0x50, _temp)
        _page = page
    if value is None:
        _temp[0] = register
        _i2c.writeto(0x50, _temp, end=1, stop=False)
        _i2c.readfrom_into(0x50, _temp, start=1)
        return _temp[1]
    _temp[0] = register
    _temp[1] = value
    _i2c.writeto(0x50, _temp)


def init():
    global _i2c, _buffer, _temp, _tick, _page
    global SLICES

    _buffer = bytearray(17)

    if _i2c is not None:
        return

    _i2c = busio.I2C(sda=board.SDA, scl=board.SCL, frequency=600000)
    _i2c.try_lock()
    _temp = bytearray(2)
    _page = None
    _tick = time.monotonic()

    try:
        _register(0x03, 0x00, 0x03)
        _register(0x00, 0x00)
        _i2c.writeto(0x50, b'\x00\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff'
                     b'\xff\xff\xff\xff\xff\xff')
    except OSError:
        raise RuntimeError("PewPew board not found")
    try:
        _temp[0:2] = b'\x00\x00'
    except TypeError:
        SLICES = False

    _key_pins = []
    for name in (
            board.APA102_MOSI, # X
            board.D1,          # DOWN
            board.D4,          # LEFT
            board.D3,          # RIGHT
            board.D13,         # UP
            board.APA102_SCK,  # O
            ):
        pin = digitalio.DigitalInOut(name)
        _key_pins.append(pin)
    samd.setup_buttons(*_key_pins)

    brightness(7)
