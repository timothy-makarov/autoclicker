import argparse
import logging
import signal
import sys
import time
from datetime import datetime

import cv2
import numpy as np
import pyautogui
from PIL import ImageGrab

__version__ = "1.0.0"
__appname__ = "autoclicker"


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
        help="Output version information and exit.",
        action="store_true",
        default=False,
    )

    parser.add_argument(
        "--failsafe",
        help="Close the program when the mouse pointer reaches the top-left corner of the screen.",
        action="store_true",
        default=False,
    )

    parser.add_argument(
        "--button",
        help="Set one or more image files as the button template.",
        default="button.png",
    )

    parser.add_argument(
        "--confidence",
        help="Set the confidence threshold for template matching.",
        default=0.8,
    )

    parser.add_argument(
        "--interval", help="Set the interval between screen checks.", default=1.0
    )

    return parser.parse_args()


def capture_screen():
    screenshot = ImageGrab.grab()
    return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)


def find_button(screen, template, confidence):
    result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    if max_val >= confidence:
        th, tw = template.shape[:2]
        center_x = max_loc[0] + tw // 2
        center_y = max_loc[1] + th // 2
        logging.info(
            f"High confidence ({max_val:.2f}): button at ({center_x}, {center_y})."
        )
        return center_x, center_y
    else:
        logging.info(f"Low confidence ({max_val:.2f}): no button.")

    return None


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    init_logging(__appname__)
    args = init_args()

    if args.version:
        print(__version__)
        return

    logging.info(f"Program {__appname__} v{__version__} started.")

    buttons = str(args.button).split(",")
    confidence = float(args.confidence)
    interval = float(args.interval)

    templates = [cv2.imread(x) for x in buttons]
    logging.info(f"Loaded {len(templates)} templates: {', '.join(buttons)}.")

    pyautogui.FAILSAFE = bool(args.failsafe)
    logging.info("Press Ctrl+C to stop.")

    while True:
        screen = capture_screen()

        for template in templates:
            match = find_button(screen, template, confidence)

            if not match:
                continue

            pyautogui.click(*match)
            logging.info("Clicked!")
            break

        time.sleep(interval)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.exception("Program failed.", exc_info=e)
