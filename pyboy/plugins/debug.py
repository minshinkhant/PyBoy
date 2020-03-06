#
# License: See LICENSE file
# GitHub: https://github.com/Baekalfen/PyBoy
#

import ctypes
from array import array

import sdl2
from pyboy import windowevent
from pyboy.botsupport import constants, tilemap  # , tile
from pyboy.botsupport.sprite import Sprite
from pyboy.plugins.base_plugin import PyBoyPlugin, PyBoyWindowPlugin
from pyboy.utils import WindowEventMarkTile

try:
    from cython import compiled
    cythonmode = compiled
except ImportError:
    cythonmode = False

# Mask colors:
COLOR = 0x00000000
MASK = 0x00C0C000

# Additive colors
HOVER = 0xFF0000
mark_counter = 0
marked_tiles = set([])
MARK = [0xFF000000, 0xFFC00000, 0xFFFC0000, 0x00FFFF00,  0xFF00FF00]

SPRITE_BACKGROUND = MASK

class Debug(PyBoyWindowPlugin):
    argv = [('-d', '--debug', {"action":'store_true', "help": 'Enable emulator debugging mode'})]

    def __init__(self, pyboy, mb, pyboy_argv):
        super().__init__(pyboy, mb, pyboy_argv)

        if not self.enabled():
            return

        sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO)

        # self.scale = 2
        window_pos = 0

        self.tile1 = TileViewWindow(pyboy, mb, pyboy_argv, scale=2, title="Background", width=256, height=256, pos_x=0, pos_y=0, window_map=False, scanline_x=0, scanline_y=1)
        window_pos += (256*self.tile1.scale)

        self.tile2 = TileViewWindow(pyboy, mb, pyboy_argv, scale=2, title="Window", width=256, height=256, pos_x=window_pos, pos_y=0, window_map=True, scanline_x=2, scanline_y=3)
        window_pos += (256*self.tile2.scale)

        self.spriteview = SpriteViewWindow(pyboy, mb, pyboy_argv, scale=2, title="Sprite View", width=constants.COLS, height=constants.ROWS, pos_x=window_pos, pos_y=0)

        self.sprite = SpriteWindow(pyboy, mb, pyboy_argv, scale=3, title="Sprite Data", width=8*10, height=16*4, pos_x=window_pos, pos_y=self.spriteview.height*2+68)
        window_pos += (constants.COLS*self.spriteview.scale)

        tile_data_width = 16*8 # Change the 16 to however wide you want the tile window
        tile_data_height = ((constants.TILES*8) // tile_data_width)*8
        self.tiledata = TileDataWindow(pyboy, mb, pyboy_argv, scale=3, title="Tile Data", width=tile_data_width, height=tile_data_height, pos_x=window_pos, pos_y=0)


    def post_tick(self):
        self.tile1.post_tick()
        self.tile2.post_tick()
        self.tiledata.post_tick()
        self.sprite.post_tick()
        self.spriteview.post_tick()

    def handle_events(self, events):
        events = self.tile1.handle_events(events)
        events = self.tile2.handle_events(events)
        events = self.tiledata.handle_events(events)
        events = self.sprite.handle_events(events)
        events = self.spriteview.handle_events(events)
        return events

    def stop(self):
        # sdl2.SDL_DestroyWindow(self._window)
        sdl2.SDL_Quit()

    def enabled(self):
        return self.pyboy_argv.get('debug')


def make_buffer(w, h):
    buf = array('B', [0x55] * (w*h*4))
    if cythonmode:
        buf0 = memoryview(buf).cast('I', shape=(h, w))
        buf_p = None
    else:
        view = memoryview(buf).cast('I')
        buf0 = [view[i:i+w] for i in range(0, w*h, w)]
        buf_p = ctypes.c_void_p(buf.buffer_info()[0])
    return buf, buf0, buf_p


class DebugWindow(PyBoyPlugin):
    def __init__(self, pyboy, mb, pyboy_argv, *, scale, title, width, height, pos_x, pos_y):
        super().__init__(pyboy, mb, pyboy_argv)
        self.scale = scale
        self.width, self.height = width, height
        self.base_title = title
        self.hover_x = -1
        self.hover_y = -1

        self.window = sdl2.SDL_CreateWindow(
            self.base_title.encode('utf8'),
            pos_x,
            pos_y,
            width*scale,
            height*scale,
            sdl2.SDL_WINDOW_RESIZABLE)
        self.window_id = sdl2.SDL_GetWindowID(self.window)


        self.buf, self.buf0, self.buf_p = make_buffer(width, height)

        self.sdlrenderer = sdl2.SDL_CreateRenderer(self.window, -1, sdl2.SDL_RENDERER_ACCELERATED)
        self.sdl_texture_buffer = sdl2.SDL_CreateTexture(
            self.sdlrenderer,
            sdl2.SDL_PIXELFORMAT_RGBA8888,
            sdl2.SDL_TEXTUREACCESS_STATIC,
            width,
            height
        )

        if not cythonmode:
            self.renderer = mb.renderer

    def __cinit__(self, mb, *args):
        self.mb = mb
        self.renderer = mb.renderer

    def handle_events(self, events):
        # Feed events into the loop
        for event in events:
            if event == windowevent.INTERNAL_MOUSE:
                if event.window_id == self.window_id:
                    self.hover_x = event.mouse_x // self.scale
                    self.hover_y = event.mouse_y // self.scale
                else:
                    self.hover_x = -1
                    self.hover_y = -1

        return events

    def stop(self):
        sdl2.SDL_DestroyWindow(self.window)

    def update_title(self):
        pass

    def post_tick(self):
        self.update_title()
        self._update_display()

    def _update_display(self):
        sdl2.SDL_UpdateTexture(self.sdl_texture_buffer, None, self.buf_p, self.width*4)
        sdl2.SDL_RenderCopy(self.sdlrenderer, self.sdl_texture_buffer, None, None)
        sdl2.SDL_RenderPresent(self.sdlrenderer)
        sdl2.SDL_RenderClear(self.sdlrenderer)

    ##########################
    # Internal functions

    def copy_tile(self, tile_cache0, t, des, to_buffer):
        xx, yy = des

        for y in range(8):
            for x in range(8):
                to_buffer[yy+y][xx+x] = tile_cache0[y + t*8][x]

    def mark_tile(self, x, y, color, height=8, width=8):
        if (0 <= x < self.width) and (0 <= y < self.height): # Test that we are inside screen area
            tw = width # Tile width
            th = height # Tile height
            xx = x - (x % tw)
            yy = y - (y % th)
            for i in range(th):
                self.buf0[yy+i][xx] = color
            for i in range(tw):
                self.buf0[yy][xx+i] = color
            for i in range(tw):
                self.buf0[yy+th-1][xx+i] = color
            for i in range(th):
                self.buf0[yy+i][xx+tw-1] = color


class TileViewWindow(DebugWindow):
    def __init__(self, *args, window_map, scanline_x, scanline_y, **kwargs):
        super().__init__(*args, **kwargs)
        self.scanline_x, self.scanline_y = scanline_x, scanline_y

        self.tilemap = tilemap.TileMap(self.mb, "WINDOW" if window_map else "BACKGROUND")

    def post_tick(self):
        tile_cache0 = self.renderer._tilecache

        # Updating screen buffer by copying tiles from cache
        mem_offset = self.tilemap.map_offset - constants.VRAM_OFFSET
        for n in range(mem_offset, mem_offset + 0x400):
            tile_index = self.mb.lcd.VRAM[n]

            # Check the tile source and add offset
            # http://problemkaputt.de/pandocs.htm#lcdcontrolregister
            # BG & Window Tile Data Select   (0=8800-97FF, 1=8000-8FFF)
            if self.mb.lcd.LCDC.tiledata_select == 0:
                # (x ^ 0x80 - 128) to convert to signed, then add 256 for offset (reduces to + 128)
                tile_index = (tile_index ^ 0x80) + 128

            tile_column = (n-mem_offset) % 32
            tile_row = (n-mem_offset) // 32

            des = (tile_column * 8, tile_row * 8)
            self.copy_tile(tile_cache0, tile_index, des, self.buf0)

        self.draw_overlay()
        super().post_tick()

    def handle_events(self, events):
        global mark_counter, marked_tiles

        self.tilemap.refresh_map_data_select()

        # Feed events into the loop
        events = super().handle_events(events)
        for event in events:
            if event == windowevent.INTERNAL_MOUSE and event.window_id == self.window_id:
                if event.mouse_button == 0:
                    tile_x, tile_y = event.mouse_x //self.scale // 8, event.mouse_y // self.scale // 8
                    tile_identifier = self.tilemap.get_tile_identifier(tile_x, tile_y)
                    marked_tiles.add(
                        WindowEventMarkTile(
                            tile_identifier=tile_identifier,
                            mark_id="TILE",
                            mark_color=MARK[mark_counter]
                        )
                    )
                    mark_counter += 1
                    mark_counter %= len(MARK)
                    # event_queue.put(WindowEventMarkTile(tile_identifier=tile_identifier, mark_id="TILE"))
                elif event.mouse_button == 1:
                    marked_tiles.clear()
            elif event == windowevent.INTERNAL_MARK_TILE:
                marked_tiles.add(event.tile_identifier)

        return events

    def update_title(self):
        title = self.base_title
        title += " [HIGH MAP 0x9C00-0x9FFF]" if self.tilemap.map_offset == constants.HIGH_TILEMAP else " [LOW MAP 0x9800-0x9BFF]"
        title += " [HIGH DATA (SIGNED) 0x8800-0x97FF]" if self.tilemap.signed_tile_data else " [LOW DATA (UNSIGNED) 0x8000-0x8FFF]"
        if self.tilemap._select == "WINDOW":
            title += " [Window]"
        if self.tilemap._select == "BACKGROUND":
            title += " [Background]"
        sdl2.SDL_SetWindowTitle(self.window, title.encode('utf8'))

    def draw_overlay(self):
        global marked_tiles
        scanlineparameters = self.pyboy.get_screen_position_list()

        # Mark screen area
        for y in range(constants.ROWS):
            xx = int(scanlineparameters[y][self.scanline_x])
            yy = int(scanlineparameters[y][self.scanline_y])
            if y == 0 or y == constants.ROWS-1:
                for x in range(constants.COLS):
                    self.buf0[(yy+y) % 0xFF][(xx+x) % 0xFF] = COLOR

            else:
                self.buf0[(yy+y) % 0xFF][xx % 0xFF] = COLOR
                for x in range(constants.COLS):
                    self.buf0[(yy+y) % 0xFF][(xx+x) % 0xFF] &= MASK
                self.buf0[(yy+y) % 0xFF][(xx+constants.COLS) % 0xFF] = COLOR

        #Mark selected tiles
        for t, match in zip(marked_tiles, self.tilemap.search_for_identifiers([m.tile_identifier for m in marked_tiles])):
            for row, column in match:
                self.mark_tile(column * 8, row * 8, t.mark_color)
        self.mark_tile(self.hover_x, self.hover_y, HOVER)
        # self.mark_tile(self.mouse_x, self.mouse_y, MARK)


class TileDataWindow(DebugWindow):
    def post_tick(self):
        tile_cache0 = self.renderer._tilecache

        for t in range(constants.TILES):
            xx = (t * 8) % self.width
            yy = ((t * 8) // self.width)*8
            self.copy_tile(tile_cache0, t, (xx, yy), self.buf0)

        self.draw_overlay()
        super().post_tick()

    def handle_events(self, events):
        global mark_counter, marked_tiles
        # Feed events into the loop
        events = super().handle_events(events)
        for event in events:
            if event == windowevent.INTERNAL_MOUSE and event.window_id == self.window_id:
                if event.mouse_button == 0:
                    tile_x, tile_y = event.mouse_x //self.scale // 8, event.mouse_y // self.scale // 8
                    tile_identifier = tile_y * (self.width//8) + tile_x
                    print(tile_identifier)
                    marked_tiles.add(
                        WindowEventMarkTile(
                            tile_identifier=tile_identifier,
                            mark_id="TILE",
                            mark_color=MARK[mark_counter]
                        )
                    )
                    mark_counter += 1
                    mark_counter %= len(MARK)
                    # event_queue.put(WindowEventMarkTile(tile_identifier=tile_identifier, mark_id="TILE"))
                elif event.mouse_button == 1:
                    marked_tiles.clear()
            elif event == windowevent.INTERNAL_MARK_TILE:
                marked_tiles.add(event.tile_identifier)
        return events

    def draw_overlay(self):
        # Mark selected tiles
        for t in marked_tiles:
            column = t.tile_identifier % (self.width//8)
            row = t.tile_identifier // (self.width//8)
            # Yes, we are using the height as width. This is because we present the tile data from left to right,
            # but the sprites with a height of 16, renders them stacked ontop of each other.
            self.mark_tile(column*8, row*8, t.mark_color, width=t.sprite_height)


class SpriteWindow(DebugWindow):
    def post_tick(self):
        tile_cache0 = self.renderer._tilecache

        sprite_height = 16 if self.mb.lcd.LCDC.sprite_height else 8
        for n in range(0, 0xA0, 4):
            # x = lcd.OAM[n]
            # y = lcd.OAM[n+1]
            t = self.mb.lcd.OAM[n+2]
            # attributes = lcd.OAM[n+3]
            xx = ((n//4) * 8) % self.width
            yy = (((n//4) * 8) // self.width)*sprite_height
            self.copy_tile(tile_cache0, t, (xx, yy), self.buf0)
            if sprite_height:
                self.copy_tile(tile_cache0, t+1, (xx, yy+8), self.buf0)

        self.draw_overlay()
        super().post_tick()

    def handle_events(self, events):
        global mark_counter, marked_tiles

        # Feed events into the loop
        events = super().handle_events(events)

        sprite_height = 16 if self.mb.lcd.LCDC.sprite_height else 8
        for event in events:
            if event == windowevent.INTERNAL_MOUSE and event.window_id == self.window_id:
                if event.mouse_button == 0:
                    tile_x, tile_y = event.mouse_x //self.scale // 8, event.mouse_y // self.scale // sprite_height
                    sprite_identifier = tile_y * (self.width//8) + tile_x
                    sprite = Sprite(self.mb, sprite_identifier)
                    marked_tiles.add(
                        WindowEventMarkTile(
                            tile_identifier=sprite.tile_identifier,
                            mark_id="SPRITE",
                            mark_color=MARK[mark_counter],
                            sprite_height=sprite_height,
                        )
                    )
                    mark_counter += 1
                    mark_counter %= len(MARK)
                    # event_queue.put(WindowEventMarkTile(tile_identifier=tile_identifier, mark_id="TILE"))
                elif event.mouse_button == 1:
                    marked_tiles.clear()
            elif event == windowevent.INTERNAL_MARK_TILE:
                marked_tiles.add(event.tile_identifier)

        return events

    def draw_overlay(self):
        sprite_height = 16 if self.mb.lcd.LCDC.sprite_height else 8
        # Mark selected tiles
        for i in range(constants.SPRITES):
            sprite = Sprite(self.mb, i)
            if WindowEventMarkTile(tile_identifier=sprite.tile_identifier) in marked_tiles or \
               (sprite_height == 16 and WindowEventMarkTile(tile_identifier=sprite.tile_identifier+1) in marked_tiles):
                for t in marked_tiles:
                    if t.tile_identifier == sprite.tile_identifier or \
                       (sprite_height == 16 and t.tile_identifier == sprite.tile_identifier+1):
                        break

                xx = (i * 8) % self.width
                yy = ((i * 8) // self.width)*sprite_height
                self.mark_tile(xx, yy, t.mark_color, height=sprite_height)

        self.mark_tile(self.hover_x, self.hover_y, HOVER, height=sprite_height)

    def update_title(self):
        title = self.base_title
        title += " [8x16]" if self.mb.lcd.LCDC.sprite_height else " [8x8]"
        sdl2.SDL_SetWindowTitle(self.window, title.encode('utf8'))

class SpriteViewWindow(DebugWindow):
    def post_tick(self):
        for y in range(constants.ROWS):
            for x in range(constants.COLS):
                self.buf0[y][x] = SPRITE_BACKGROUND

        self.mb.renderer.render_sprites(self.mb.lcd, self.buf0)
        super().post_tick()

    def update_title(self):
        title = self.base_title
        title += " " if self.mb.lcd.LCDC.sprite_enable else " [Disabled]"
        sdl2.SDL_SetWindowTitle(self.window, title.encode('utf8'))
