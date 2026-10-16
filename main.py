import argparse
import ctypes
import logging
import signal
import sys
import time
from datetime import datetime

import cv2
import numpy as np
import win32api
import win32con
import win32gui
import win32ui
from PIL import Image
from pywinauto.application import Application

__version__ = "1.1.0"
__appname__ = "autoclicker"

PW_CLIENTONLY = 0x1
PW_RENDERFULLCONTENT = 0x2


def init_logging(log_file_name):
    format = "%(asctime)s [%(levelname)s] %(message)s"

    logging.basicConfig(
        format=format,
        filename=f"{log_file_name}_{datetime.now():%Y%m%d}.log",
        level=logging.DEBUG,
    )

    formatter = logging.Formatter(format)

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.DEBUG)
    stdout_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.addHandler(stdout_handler)


def init_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--version",
        help="Display version information and exit.",
        action="store_true",
        default=False,
    )

    parser.add_argument(
        "--list-windows",
        help="Output a list of all available windows and their corresponding window handles.",
        action="store_true",
        default=False,
    )

    parser.add_argument(
        "--window",
        help="Specify the application window containing the buttons to be clicked.",
    )

    parser.add_argument(
        "--topmost-child-class-name",
        help="Specify the class name of the application's topmost child window to convert click coordinates.",
        default="Chrome_RenderWidgetHostHWND",
    )

    parser.add_argument(
        "--buttons",
        help="Select one or more image files to use as button templates.",
        default="button.png",
    )

    parser.add_argument(
        "--confidence",
        help="Set the confidence threshold for matching button templates.",
        default=0.8,
    )

    parser.add_argument(
        "--interval", help="Set the interval between screen checks.", default=1.0
    )

    return parser.parse_args()


def match_button(img, template, confidence):
    if img is None:
        logging.getLogger(__appname__).warning("The window may be minimized.")
        return None

    if isinstance(img, Image.Image):
        if img.width <= 1 or img.height <= 1:
            logging.getLogger(__appname__).warning("The window may be minimized.")
            return None
        img = np.array(img.convert("RGB"))[:, :, ::-1].copy()

    if img.shape[0] <= 1 or img.shape[1] <= 1:
        logging.getLogger(__appname__).warning("The window may be minimized.")
        return None

    result = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    if max_val >= confidence:
        th, tw = template.shape[:2]
        center_x = max_loc[0] + tw // 2
        center_y = max_loc[1] + th // 2
        logging.getLogger(__appname__).info(
            f"High confidence ({max_val:.2f}): button at ({center_x}, {center_y})."
        )
        return center_x, center_y
    else:
        logging.getLogger(__appname__).info(
            f"Low confidence ({max_val:.2f}): no button."
        )

    return None


def capture_window(hwnd, client_only=True):
    if client_only:
        _, _, w, h = win32gui.GetClientRect(hwnd)
    else:
        l, t, r, b = win32gui.GetWindowRect(hwnd)
        w, h = r - l, b - t

    if w <= 0 or h <= 0:
        return None

    hwnd_dc = win32gui.GetWindowDC(hwnd)
    src_dc = win32ui.CreateDCFromHandle(hwnd_dc)
    mem_dc = src_dc.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(src_dc, w, h)
    mem_dc.SelectObject(bmp)

    flags = PW_RENDERFULLCONTENT | (PW_CLIENTONLY if client_only else 0)
    ok = ctypes.windll.user32.PrintWindow(hwnd, mem_dc.GetSafeHdc(), flags)
    bits = bmp.GetBitmapBits(True)
    img = Image.frombuffer("RGB", (w, h), bits, "raw", "BGRX", 0, 1)

    win32gui.DeleteObject(bmp.GetHandle())
    mem_dc.DeleteDC()
    src_dc.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwnd_dc)

    return img if ok else None


def list_windows():
    result = []

    def visit(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title:
                result.append((hwnd, title))
        return True

    win32gui.EnumWindows(visit, None)

    return result


def click_window_point(
    top_hwnd, x, y, topmost_child_class_name="Chrome_RenderWidgetHostHWND"
):
    app = Application(backend="win32").connect(handle=top_hwnd)
    main_window = app.window()
    child_control = main_window.child_window(class_name=topmost_child_class_name)
    child_hwnd = child_control.wrapper_object().handle

    screen_x, screen_y = win32gui.ClientToScreen(top_hwnd, (x, y))
    x, y = win32gui.ScreenToClient(child_hwnd, (screen_x, screen_y))

    l_param = win32api.MAKELONG(x, y)
    win32gui.PostMessage(
        child_hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, l_param
    )
    time.sleep(0.05)
    win32gui.PostMessage(child_hwnd, win32con.WM_LBUTTONUP, 0, l_param)


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    ctypes.windll.shcore.SetProcessDpiAwareness(2)

    init_logging(__appname__)
    args = init_args()

    if args.version:
        print(__version__)
        return

    if args.list_windows:
        print(f"{'HWND':<8} | {'TITLE':<15}")
        print("-" * 80)
        for hwnd, title in list_windows():
            print(f"{hwnd:<8} | {title:<15}")
        return

    logging.getLogger(__appname__).info(
        f"Program {__appname__} v{__version__} started."
    )

    buttons = str(args.buttons).split(",")
    confidence = float(args.confidence)
    interval = float(args.interval)

    templates = [cv2.imread(x) for x in buttons]
    logging.getLogger(__appname__).info(
        f"Loaded {len(templates)} templates: {', '.join(buttons)}."
    )

    logging.getLogger(__appname__).info("Press Ctrl+C to stop.")

    while True:
        windows = list_windows()

        for hwnd, title in windows:
            if args.window == title:
                img = capture_window(hwnd)

                for template in templates:
                    crds = match_button(img, template, confidence)

                    if not crds:
                        logging.getLogger(__appname__).info("No match found.")
                        continue

                    click_window_point(
                        hwnd,
                        crds[0],
                        crds[1],
                    )
                    logging.getLogger(__appname__).info(
                        f'Clicked on window "{title}" ({crds[0]}; {crds[1]}).'
                    )
                    break

        time.sleep(interval)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.getLogger(__appname__).exception("Program failed.", exc_info=e)
