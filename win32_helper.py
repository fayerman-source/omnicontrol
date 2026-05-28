import ctypes
from ctypes import wintypes, Structure, Union, POINTER, CFUNCTYPE, byref, sizeof
import sys

# Win32 Constants
WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
INPUT_HARDWARE = 2

# Mouse flags
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_XDOWN = 0x0080
MOUSEEVENTF_XUP = 0x0100
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

# Keyboard flags
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

# Clipboard Formats
CF_UNICODETEXT = 13

# Global allocations
GMEM_MOVEABLE = 0x0002
GMEM_ZEROINIT = 0x0040

# Custom types
HHOOK = wintypes.HANDLE
LRESULT = ctypes.c_int64
WPARAM = wintypes.WPARAM
LPARAM = wintypes.LPARAM
HookProc = CFUNCTYPE(LRESULT, ctypes.c_int, WPARAM, LPARAM)

# Structs
class POINT(Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

class MSLLHOOKSTRUCT(Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", ctypes.c_ulong),
        ("flags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_ulonglong)
    ]

class KBDLLHOOKSTRUCT(Structure):
    _fields_ = [
        ("vkCode", ctypes.c_ulong),
        ("scanCode", ctypes.c_ulong),
        ("flags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_ulonglong)
    ]

class MOUSEINPUT(Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_ulonglong)
    ]

class KEYBDINPUT(Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_ulonglong)
    ]

class HARDWAREINPUT(Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_ushort),
        ("wParamH", ctypes.c_ushort)
    ]

class U(Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

class INPUT(Structure):
    _fields_ = [("type", ctypes.c_ulong), ("u", U)]

# Load DLLs
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Hook functions API
SetWindowsHookEx = user32.SetWindowsHookExW
SetWindowsHookEx.argtypes = [ctypes.c_int, HookProc, wintypes.HINSTANCE, wintypes.DWORD]
SetWindowsHookEx.restype = HHOOK

UnhookWindowsHookEx = user32.UnhookWindowsHookEx
UnhookWindowsHookEx.argtypes = [HHOOK]
UnhookWindowsHookEx.restype = wintypes.BOOL

CallNextHookEx = user32.CallNextHookEx
CallNextHookEx.argtypes = [HHOOK, ctypes.c_int, WPARAM, LPARAM]
CallNextHookEx.restype = LRESULT

# Message loop APIs
GetMessage = user32.GetMessageW
GetMessage.argtypes = [POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
GetMessage.restype = wintypes.BOOL

TranslateMessage = user32.TranslateMessage
TranslateMessage.argtypes = [POINTER(wintypes.MSG)]
TranslateMessage.restype = wintypes.BOOL

DispatchMessage = user32.DispatchMessageW
DispatchMessage.argtypes = [POINTER(wintypes.MSG)]
DispatchMessage.restype = LRESULT

PostThreadMessage = user32.PostThreadMessageW
PostThreadMessage.argtypes = [wintypes.DWORD, wintypes.UINT, WPARAM, LPARAM]
PostThreadMessage.restype = wintypes.BOOL

# Input Injection API
SendInput = user32.SendInput
SendInput.argtypes = [wintypes.UINT, POINTER(INPUT), ctypes.c_int]
SendInput.restype = wintypes.UINT

# Cursor and Monitor APIs
GetSystemMetrics = user32.GetSystemMetrics
GetSystemMetrics.argtypes = [ctypes.c_int]
GetSystemMetrics.restype = ctypes.c_int

GetCursorPos = user32.GetCursorPos
GetCursorPos.argtypes = [POINTER(POINT)]
GetCursorPos.restype = wintypes.BOOL

SetCursorPos = user32.SetCursorPos
SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
SetCursorPos.restype = wintypes.BOOL

ClipCursor = user32.ClipCursor
ClipCursor.argtypes = [POINTER(wintypes.RECT)]
ClipCursor.restype = wintypes.BOOL

class RECT(Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long)
    ]

# Global Allocations and Clipboard
GlobalAlloc = kernel32.GlobalAlloc
GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
GlobalAlloc.restype = wintypes.HGLOBAL

GlobalLock = kernel32.GlobalLock
GlobalLock.argtypes = [wintypes.HGLOBAL]
GlobalLock.restype = wintypes.LPVOID

GlobalUnlock = kernel32.GlobalUnlock
GlobalUnlock.argtypes = [wintypes.HGLOBAL]
GlobalUnlock.restype = wintypes.BOOL

GlobalSize = kernel32.GlobalSize
GlobalSize.argtypes = [wintypes.HGLOBAL]
GlobalSize.restype = ctypes.c_size_t

OpenClipboard = user32.OpenClipboard
OpenClipboard.argtypes = [wintypes.HWND]
OpenClipboard.restype = wintypes.BOOL

CloseClipboard = user32.CloseClipboard
CloseClipboard.argtypes = []
CloseClipboard.restype = wintypes.BOOL

EmptyClipboard = user32.EmptyClipboard
EmptyClipboard.argtypes = []
EmptyClipboard.restype = wintypes.BOOL

GetClipboardData = user32.GetClipboardData
GetClipboardData.argtypes = [wintypes.UINT]
GetClipboardData.restype = wintypes.HANDLE

SetClipboardData = user32.SetClipboardData
SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
SetClipboardData.restype = wintypes.HANDLE

# --- High Level Wrapper Functions ---

def get_screen_size():
    """Returns the width and height of the primary monitor in pixels."""
    # SM_CXSCREEN = 0, SM_CYSCREEN = 1
    width = GetSystemMetrics(0)
    height = GetSystemMetrics(1)
    return width, height

def get_virtual_screen_size():
    """Returns total desktop size (useful for multi-monitor setups)."""
    # SM_CXVIRTUALSCREEN = 78, SM_CYVIRTUALSCREEN = 79
    width = GetSystemMetrics(78)
    height = GetSystemMetrics(79)
    if width == 0 or height == 0:
        return get_screen_size()
    return width, height

def get_mouse_position():
    """Returns current mouse coordinates (x, y) on the screen."""
    pt = POINT()
    if GetCursorPos(byref(pt)):
        return pt.x, pt.y
    return 0, 0

def set_mouse_position(x, y):
    """Moves mouse immediately to (x, y)."""
    SetCursorPos(x, y)

def lock_cursor_to_screen():
    """Locks cursor to physical screen boundaries to prevent escaping."""
    w, h = get_screen_size()
    rect = RECT(0, 0, w, h)
    ClipCursor(byref(rect))

def unlock_cursor():
    """Unlocks cursor constraints."""
    ClipCursor(None)

# Input Injection implementation

def inject_mouse_move(dx, dy, relative=True):
    """Injects mouse movement."""
    inp = INPUT()
    inp.type = INPUT_MOUSE
    if relative:
        inp.u.mi.dx = dx
        inp.u.mi.dy = dy
        inp.u.mi.dwFlags = MOUSEEVENTF_MOVE
    else:
        # Absolute coordinates require mapping to 0-65535 space
        # across the system virtual screen
        w, h = get_virtual_screen_size()
        inp.u.mi.dx = int(dx * 65536 / w)
        inp.u.mi.dy = int(dy * 65536 / h)
        inp.u.mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
        
    inp.u.mi.mouseData = 0
    inp.u.mi.time = 0
    inp.u.mi.dwExtraInfo = 0
    SendInput(1, byref(inp), sizeof(INPUT))

def inject_mouse_click(event_type, mouse_data=0):
    """
    Injects mouse click events.
    event_type: e.g. MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP, MOUSEEVENTF_WHEEL, etc.
    mouse_data: 120 (WHEEL_DELTA) or -120 for mouse wheel scrolling.
    """
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.u.mi.dx = 0
    inp.u.mi.dy = 0
    inp.u.mi.mouseData = mouse_data
    inp.u.mi.dwFlags = event_type
    inp.u.mi.time = 0
    inp.u.mi.dwExtraInfo = 0
    SendInput(1, byref(inp), sizeof(INPUT))

def inject_keyboard_key(vk_code, scan_code, flags):
    """Injects a keyboard key down/up event."""
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.u.ki.wVk = vk_code
    inp.u.ki.wScan = scan_code
    
    # We must preserve the flags like KEYEVENTF_KEYUP, KEYEVENTF_EXTENDEDKEY
    # While filtering out our own flags if any.
    inp.u.ki.dwFlags = flags
    inp.u.ki.time = 0
    inp.u.ki.dwExtraInfo = 0
    SendInput(1, byref(inp), sizeof(INPUT))

# Clipboard APIs

def get_clipboard_text():
    """Gets the current Unicode text from the clipboard."""
    if not OpenClipboard(0):
        return None
    try:
        h_data = GetClipboardData(CF_UNICODETEXT)
        if not h_data:
            return None
        ptr = GlobalLock(h_data)
        if not ptr:
            return None
        try:
            # Clipboard data is null-terminated UTF-16 on Windows
            return ctypes.wstring_at(ptr)
        finally:
            GlobalUnlock(h_data)
    finally:
        CloseClipboard()

def set_clipboard_text(text):
    """Sets the clipboard text to the provided Unicode string."""
    if not text:
        return False
    if not OpenClipboard(0):
        return False
    try:
        EmptyClipboard()
        # Encode as UTF-16-LE with null terminator
        text_bytes = (text + '\0').encode('utf-16le')
        num_bytes = len(text_bytes)
        
        # Allocate global memory
        h_global = GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, num_bytes)
        if not h_global:
            return False
            
        ptr = GlobalLock(h_global)
        if not ptr:
            return False
        try:
            ctypes.memmove(ptr, text_bytes, num_bytes)
        finally:
            GlobalUnlock(h_global)
            
        SetClipboardData(CF_UNICODETEXT, h_global)
        return True
    finally:
        CloseClipboard()
