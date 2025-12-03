import time
import numpy as np
import keyboard
import mouse
from mouse import ButtonEvent
from mss import mss
from PIL import Image
import tkinter as tk
import threading

# 像素变化相关阈值（可根据实际调节）
CHANGE_THRESHOLD = 8       # 单像素 RGB 平均差异阈值（数值越小越敏感）
STRONG_RATIO     = 0.05    # 强变化判定阈值（5% 像素明显变化，立即认为是“响应”）
WEAK_RATIO       = 0.01    # 弱变化阈值（1% 像素变化就算“有点变”，用于兜底参考）
TIMEOUT_SEC      = 3       # 从点击开始最多等待多久（秒）


def grab_region(sct, region):
    """从屏幕指定区域抓一帧图像"""
    img = sct.grab(region)
    return Image.frombytes("RGB", img.size, img.rgb)


def calc_diff_ratio(img1, img2):
    """计算两帧图像的像素变化比例"""
    arr1 = np.asarray(img1).astype(np.int16)
    arr2 = np.asarray(img2).astype(np.int16)
    diff = np.abs(arr1 - arr2).mean(axis=2)
    changed_pixels = (diff > CHANGE_THRESHOLD).sum()
    total_pixels = diff.size
    return changed_pixels / total_pixels


def select_region():
    """Ctrl+Alt+S 启动，鼠标拖拽选择区域，返回 {top,left,width,height}"""
    print("按 Ctrl+Alt+S 进入框选模式……")
    keyboard.wait("ctrl+alt+s")
    print("已进入框选模式：左键按下开始拖拽，松开结束。")

    root = tk.Tk()
    root.attributes("-fullscreen", True)
    root.attributes("-alpha", 0.3)
    root.config(bg="grey")
    root.attributes("-topmost", True)
    root.overrideredirect(True)

    start_x = start_y = end_x = end_y = 0
    rect = None

    def on_button_press(event):
        nonlocal start_x, start_y, rect
        start_x, start_y = event.x, event.y
        rect = canvas.create_rectangle(
            start_x, start_y, start_x, start_y,
            outline="red", width=2
        )

    def on_move_press(event):
        nonlocal rect
        cur_x, cur_y = event.x, event.y
        canvas.coords(rect, start_x, start_y, cur_x, cur_y)

    def on_button_release(event):
        nonlocal end_x, end_y
        end_x, end_y = event.x, event.y
        root.quit()

    canvas = tk.Canvas(root, cursor="cross")
    canvas.pack(fill=tk.BOTH, expand=True)

    canvas.bind("<ButtonPress-1>", on_button_press)
    canvas.bind("<B1-Motion>", on_move_press)
    canvas.bind("<ButtonRelease-1>", on_button_release)

    root.mainloop()
    root.destroy()

    left = min(start_x, end_x)
    top = min(start_y, end_y)
    width = abs(end_x - start_x)
    height = abs(end_y - start_y)

    if width == 0 or height == 0:
        raise ValueError(
            f"选中的区域宽或高为 0：left={left}, top={top}, width={width}, height={height}"
        )

    region = {"top": top, "left": left, "width": width, "height": height}
    print("选定区域：", region)
    print("选择层已关闭，你可以在该区域正常进行鼠标操作。")
    return region


def monitor_once(region):
    """
    模式 1：只记录一次
    流程：
      - 监听第一次左键按下 → 记 t1
      - 之后在区域内监控画面变化：
          · 若出现“强变化” → 记 t2 强，输出 Δt 强
          · 若超时未出现强变化、但有弱变化 → 用最大变化时刻 t2 弱 兜底
      - 输出一次结果后结束
    """
    print("\n【单次模式】")
    print("  请准备好要测的一次点击。")
    print("  将鼠标移动到目标控件上，正常左键点击即可。")

    # 初始基准图像
    with mss() as sct:
        base_img = grab_region(sct, region)

    click_lock = threading.Lock()
    click_time = {"t": None}

    def on_left_click(event):
        nonlocal base_img
        if not isinstance(event, ButtonEvent):
            return
        if event.event_type == 'down' and event.button == 'left':
            with click_lock:
                if click_time["t"] is None:  # 只记录第一次点击
                    click_time["t"] = time.time()
                    with mss() as sct_local:
                        base_img = grab_region(sct_local, region)

    mouse.hook(on_left_click)

    try:
        # 等待第一次点击
        while True:
            with click_lock:
                t1 = click_time["t"]
            if t1 is not None:
                break
            time.sleep(0.01)

        print("检测到点击，开始监控画面变化……")

        with mss() as sct:
            start_time = t1
            deadline = start_time + TIMEOUT_SEC

            best_ratio = 0.0
            best_time = None

            while True:
                now = time.time()
                if now > deadline:
                    if best_time is not None and best_ratio >= WEAK_RATIO:
                        delta_ms = (best_time - t1) * 1000
                        print(f"[单次模式·弱变化兜底] t1(点击)={t1:.6f}, "
                              f"t2(最大变化)={best_time:.6f}, "
                              f"Δt ≈ {delta_ms:.2f} ms, 最大变化比例={best_ratio:.3f}")
                    else:
                        print(f"[单次模式·无变化] 点击时间 t1={start_time:.6f} 后 {TIMEOUT_SEC}s 内，"
                              f"监控区域未检测到明显画面变化。")
                    break

                current_img = grab_region(sct, region)
                diff_ratio = calc_diff_ratio(base_img, current_img)

                # 记录最大变化
                if diff_ratio > best_ratio:
                    best_ratio = diff_ratio
                    best_time = now

                # 强变化：立即认定为响应
                if diff_ratio >= STRONG_RATIO:
                    t2 = now
                    delta_ms = (t2 - t1) * 1000
                    print(f"[单次模式·检测到响应] t1(点击)={t1:.6f}, t2(变化)={t2:.6f}, "
                          f"Δt = {delta_ms:.2f} ms, 变化比例={diff_ratio:.3f}")
                    break

                time.sleep(1 / 60.0)  # 60 FPS

    finally:
        mouse.unhook(on_left_click)


def monitor_continuous(region):
    """
    模式 2：持续无休止追加
    - 每次左键点击记录 t1
    - 在区域内寻找下一次画面变化：
        · 有强变化 → 立即输出 Δt
        · 无强变化但有弱变化 → 超时时用最大变化兜底
        · 完全无变化 → 输出“无变化”
    - 一直循环，直到按 Esc 退出
    """
    print("\n【持续模式】")
    print("  正常使用应用，每次左键点击后都会尝试测一次响应时间。")
    print("  按 Esc 退出持续监控。\n")

    with mss() as sct:
        base_img = grab_region(sct, region)

    click_lock = threading.Lock()
    last_click_time = {"t": None}

    def on_left_click(event):
        nonlocal base_img
        if not isinstance(event, ButtonEvent):
            return
        if event.event_type == 'down' and event.button == 'left':
            with click_lock:
                last_click_time["t"] = time.time()
                with mss() as sct_local:
                    base_img = grab_region(sct_local, region)

    mouse.hook(on_left_click)

    try:
        while True:
            if keyboard.is_pressed("esc"):
                print("检测到 Esc，退出持续监控。")
                break

            with click_lock:
                t1 = last_click_time["t"]

            if t1 is None:
                time.sleep(0.01)
                continue

            # 取出这次点击并清空，避免重复处理
            with click_lock:
                t1 = last_click_time["t"]
                last_click_time["t"] = None

            with mss() as sct:
                start_time = t1
                deadline = start_time + TIMEOUT_SEC

                best_ratio = 0.0
                best_time = None

                while True:
                    now = time.time()
                    if now > deadline:
                        if best_time is not None and best_ratio >= WEAK_RATIO:
                            delta_ms = (best_time - t1) * 1000
                            print(f"[弱变化兜底] t1(点击)={t1:.6f}, "
                                  f"t2(最大变化)={best_time:.6f}, "
                                  f"Δt ≈ {delta_ms:.2f} ms, 最大变化比例={best_ratio:.3f}")
                        else:
                            print(f"[无变化] 点击时间 t1={start_time:.6f} 后 {TIMEOUT_SEC}s 内，"
                                  f"监控区域未检测到明显画面变化。")
                        break

                    current_img = grab_region(sct, region)
                    diff_ratio = calc_diff_ratio(base_img, current_img)

                    # 记录最大变化
                    if diff_ratio > best_ratio:
                        best_ratio = diff_ratio
                        best_time = now

                    # 强变化：立即判定为响应
                    if diff_ratio >= STRONG_RATIO:
                        t2 = now
                        delta_ms = (t2 - t1) * 1000
                        print(f"[检测到响应] t1(点击)={t1:.6f}, t2(变化)={t2:.6f}, "
                              f"Δt = {delta_ms:.2f} ms, 变化比例={diff_ratio:.3f}")
                        base_img = current_img
                        break

                    time.sleep(1 / 60.0)  # 60 FPS

    finally:
        mouse.unhook(on_left_click)


def main():
    print("步骤 1：按 Ctrl+Alt+S 进入框选模式，拖一个矩形选择【要监控的区域】。")
    region = select_region()

    print("\n请选择模式：")
    print("  1 = 只记录一次（单次模式）")
    print("  2 = 持续记录（持续模式，直到 Esc 退出）")
    mode = input("请输入 1 或 2，然后回车：").strip()

    if mode == "1":
        monitor_once(region)
    elif mode == "2":
        monitor_continuous(region)
    else:
        print("输入非法，退出程序。")


if __name__ == "__main__":
    main()