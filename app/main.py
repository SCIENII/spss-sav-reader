#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SPSS .sav 文件阅读器 v3.0
Canvas 虚拟滚动引擎 — 百列万行丝滑浏览
"""
import sys, os, re, traceback, threading, math
from pathlib import Path

# ── 全局异常捕获 ──
def _global_excepthook(exc_type, exc_value, exc_traceback):
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    try:
        import tkinter.messagebox as mb
        mb.showerror("程序异常", f"发生未捕获的异常:\n\n{exc_value}")
    except Exception:
        pass
    desk = Path.home() / "Desktop" / "sav_reader_error.log"
    desk.write_text(msg, encoding="utf-8")

sys.excepthook = _global_excepthook

import pandas as pd
import pyreadstat
import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinterdnd2 import TkinterDnD, DND_FILES

# ── 常量 ──
APP_NAME = "SPSS 数据阅读器"
APP_VERSION = "3.0"
DEFAULT_W = 1280
DEFAULT_H = 780

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# ── 颜色 ──
BG      = "#1a1a1a"
BG2     = "#1e1e1e"
BG_ALT  = "#252525"
FG      = "#cccccc"
FG_DIM  = "#555555"
HEADER_BG = "#2d2d2d"
HEADER_FG = "#e0e0e0"
SCROLLBAR_BG = "#333333"
SCROLLBAR_FG = "#555555"
SELECT_BG = "#2b5797"

FONT_DATA   = ("Consolas", 11)
FONT_HEADER = ("Microsoft YaHei UI", 11, "bold")
FONT_MONO   = ("Consolas", 11)

ROW_H = 26
ROW_GAP = 1
HEADER_H = 30

# ── 颜色日志控件 ──
class LogFrame(ctk.CTkScrollableFrame):
    COLORS = {"INFO":"#4ec9b0","OK":"#0ecb81","WARN":"#f0b90b","ERROR":"#f6465d","SYSTEM":"#569cd6"}
    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self._lines = []
    def write(self, text, tag="INFO"):
        color = self.COLORS.get(tag, "#cccccc")
        f = ctk.CTkFont(size=12, family="Consolas")
        lbl = ctk.CTkLabel(self, text=text, font=f, text_color=color, anchor="w", justify="left", wraplength=700)
        lbl.pack(fill="x", padx=5, pady=1)
        self._lines.append(lbl)
        self.after(50, lambda: self._scroll_bottom() if hasattr(self,'_parent_canvas') else None)
    def _scroll_bottom(self):
        try: self._parent_canvas.yview_moveto(1.0)
        except: pass
    def clear(self):
        for w in self._lines: w.destroy()
        self._lines.clear()

# ── 数据表视图（Canvas 虚拟滚动） ──
class DataTableView(tk.Frame):
    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.configure(bg=BG)

        # 数据
        self._data = None
        self._columns = []
        self._col_widths = []
        self._nrows = 0
        self._ncols = 0
        self._total_w = 0
        self._total_h = 0
        self._first_vis_row = 0
        self._first_vis_col = 0
        self._vis_rows_count = 0
        self._vis_cols_count = 0
        self._xofs = 0
        self._yofs = 0
        self._placeholder_label = None
        self._loading_label = None
        self._loading_progress = None
        self._selected_row = -1
        self._row_h = ROW_H
        self._header_h = HEADER_H
        self._default_col_w = 100

        # 主框架  只创建一次
        self._table_frame = tk.Frame(self, bg=BG)
        self._table_frame.pack(fill="both", expand=True)

        # 占位用
        self._placeholder_label = tk.Label(
            self._table_frame,
            text="拖拽 .sav 文件到窗口，或点击「打开文件」\n\n支持 SPSS 数据文件 (*.sav)",
            font=("Microsoft YaHei UI", 16), bg=BG, fg=FG_DIM)
        self._placeholder_label.pack(expand=True)

    def _build_widgets(self):
        """创建 Canvas + 滚动条（在已有 _table_frame 内）"""
        # 清除占位/加载
        self._placeholder_label = None
        self._loading_label = None
        self._loading_progress = None

        # ── 头部 Canvas ──
        self._header_canvas = tk.Canvas(
            self._table_frame, height=self._header_h,
            bg=HEADER_BG, highlightthickness=0)
        self._header_canvas.pack(fill="x", side="top")
        self._header_canvas.bind("<Button-1>", self._on_header_click)

        # ── 数据体 Canvas + 滚动条 ──
        body_frame = tk.Frame(self._table_frame, bg=BG)
        body_frame.pack(fill="both", expand=True)

        self._vbar = tk.Scrollbar(body_frame, orient="vertical", bg=SCROLLBAR_BG,
                                   troughcolor=BG, activebackground="#666", width=14)
        self._vbar.pack(side="right", fill="y")

        self._hbar = tk.Scrollbar(self._table_frame, orient="horizontal", bg=SCROLLBAR_BG,
                                   troughcolor=BG, activebackground="#666", width=14)
        self._hbar.pack(fill="x", side="bottom", before=body_frame)

        self._canvas = tk.Canvas(
            body_frame, bg=BG2, highlightthickness=0,
            yscrollcommand=self._on_vscroll,
            xscrollcommand=self._on_hscroll)
        self._canvas.pack(fill="both", expand=True, side="left")

        self._vbar.config(command=self._canvas.yview)
        self._hbar.config(command=self._on_hbar_scroll)

        # 事件绑定
        self._canvas.bind("<Configure>", self._on_canvas_resize)
        self._canvas.bind("<Button-1>", self._on_cell_click)
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)
        self._canvas.bind("<B1-Motion>", self._on_cell_drag)

    # ── 数据加载 ──
    def show_placeholder(self):
        self.clear()
        self._placeholder_label = tk.Label(
            self._table_frame,
            text="拖拽 .sav 文件到窗口，或点击「打开文件」\n\n支持 SPSS 数据文件 (*.sav)",
            font=("Microsoft YaHei UI", 16), bg=BG, fg=FG_DIM)
        self._placeholder_label.pack(expand=True)

    def show_loading(self, filename=""):
        self.clear()
        self._loading_label = tk.Label(
            self._table_frame,
            text=f" 正在加载: {filename or '...'}",
            font=FONT_MONO, bg=BG, fg="#569cd6")
        self._loading_label.pack(expand=True)
        self._loading_progress = ttk.Progressbar(self._table_frame, mode="indeterminate", length=300)
        self._loading_progress.pack(pady=10)
        self._loading_progress.start(10)
        self.update()

    def load_data(self, df: pd.DataFrame, meta=None):
        self.clear()
        self._build_widgets()
        self._nrows, self._ncols = df.shape
        self._columns = list(df.columns)
        self._selected_row = -1

        # 预处理所有数据为字符串列表
        self._data = []
        col_list = self._columns
        for r in range(self._nrows):
            row = []
            for c_idx in range(self._ncols):
                val = df.iat[r, c_idx]
                if pd.isna(val):
                    row.append(None)  # None = NaN 灰色点
                elif isinstance(val, float):
                    if val == int(val):
                        row.append(str(int(val)))
                    else:
                        row.append(f"{val:.4f}")
                else:
                    row.append(str(val))
            self._data.append(row)

        # 计算列宽
        self._calc_col_widths()

        # 初始化 Canvas 滚动区域
        self._total_w = sum(self._col_widths) + 10
        self._total_h = self._nrows * self._row_h
        self._xofs = 0
        self._yofs = 0

        # 确保 Canvas 完成布局后再绘制
        self._table_frame.update_idletasks()
        self._update_scroll_region()
        self._update_view()
        self._draw_header()

    def _calc_col_widths(self):
        """智能计算每列宽度"""
        self._col_widths = []
        for i, col in enumerate(self._columns):
            # 列名字符长度
            header_w = self._text_width(col, FONT_HEADER)
            # 数据内容宽度（采样前 300 行）
            sample_w = 80
            for r in range(min(300, self._nrows)):
                val = self._data[r][i]
                if val is not None:
                    w = self._text_width(val, FONT_DATA)
                    if w > sample_w:
                        sample_w = w
            # 选最大的 + padding
            w = max(header_w, sample_w) + 16
            w = max(w, 60)   # 最小60
            w = min(w, 280)  # 最大280
            self._col_widths.append(w)

    def _text_width(self, text, font):
        """估算文本像素宽度（等宽字体近似）"""
        if not text:
            return 0
        # Consolas 近似：每个字符 ~7px
        if font == FONT_DATA or font == FONT_MONO:
            return len(str(text)) * 7
        else:
            return len(str(text)) * 8

    # ── 绘制 ├─

    def _draw_header(self):
        """绘制固定表头"""
        c = self._header_canvas
        c.delete("all")
        c.config(scrollregion=(0, 0, self._total_w, self._header_h))

        x = -self._xofs
        for i in range(self._ncols):
            w = self._col_widths[i]
            # 背景
            c.create_rectangle(x, 0, x + w, self._header_h,
                               fill=HEADER_BG, outline="#444", width=1)
            # 文字
            txt = self._columns[i]
            c.create_text(x + 6, self._header_h // 2, anchor="w",
                          text=txt, fill=HEADER_FG,
                          font=FONT_HEADER)
            # 行号列特殊
            x += w
        # 行号列
        c.create_rectangle(0, 0, 55, self._header_h,
                           fill=HEADER_BG, outline="#444", width=1)
        c.create_text(27, self._header_h // 2, anchor="center",
                      text="#", fill=HEADER_FG, font=FONT_HEADER)

    def _update_view(self):
        """重绘可见数据区域"""
        c = self._canvas
        c.delete("all")

        pad_x = -self._xofs
        pad_y = -self._yofs

        view_w = c.winfo_width()
        view_h = c.winfo_height()

        if view_w < 10 or view_h < 10:
            return

        # 计算可见行列范围
        first_row = max(0, int(self._yofs / self._row_h))
        last_row = min(self._nrows, first_row + int(view_h / self._row_h) + 2)
        first_col = 0
        x_acc = 0
        for i, w in enumerate(self._col_widths):
            if x_acc + w > self._xofs:
                first_col = i
                break
            x_acc += w
        last_col = first_col
        x_acc = 0
        for i, w in enumerate(self._col_widths):
            if i < first_col:
                continue
            x_acc += w
            if x_acc > self._xofs + view_w:
                last_col = i
                break
            last_col = i

        self._first_vis_row = first_row
        self._first_vis_col = first_col
        self._vis_rows_count = last_row - first_row + 1
        self._vis_cols_count = last_col - first_col + 1

        # 绘制行号列背景
        row_num_w = 55
        c.create_rectangle(0, 0, row_num_w, view_h,
                           fill="#222222", outline="", width=0)

        # 绘制数据
        for r in range(first_row, min(last_row + 1, self._nrows)):
            y = r * self._row_h + pad_y
            if y + self._row_h < 0 or y > view_h:
                continue

            # 行背景
            bg_color = BG_ALT if (r % 2 == 1) else BG2
            if r == self._selected_row:
                bg_color = SELECT_BG

            c.create_rectangle(row_num_w, y - 1, view_w, y + self._row_h - 1,
                               fill=bg_color, outline="", width=0)

            # 行号
            c.create_text(row_num_w - 6, y + self._row_h // 2, anchor="e",
                          text=str(r + 1), fill=FG_DIM, font=FONT_MONO)

            # 数据单元格
            x = row_num_w + pad_x
            for ci in range(first_col, min(last_col + 1, self._ncols)):
                w = self._col_widths[ci]
                val = self._data[r][ci]
                if val is None:
                    txt = "·"
                    color = FG_DIM
                else:
                    txt = val
                    color = FG if r != self._selected_row else "#ffffff"

                c.create_text(x + 6, y + self._row_h // 2, anchor="w",
                              text=txt, fill=color, font=FONT_DATA)
                x += w

        # 列分隔线（画垂直线）
        x = row_num_w + pad_x
        for ci in range(first_col, min(last_col + 1, self._ncols)):
            w = self._col_widths[ci]
            x += w
            c.create_line(x, 0, x, view_h, fill="#2a2a2a", width=1)

        # 底部分隔线
        c.create_line(0, self._total_h + pad_y, view_w, self._total_h + pad_y,
                      fill="#2a2a2a", width=1)

    def _draw_header(self):
        """绘制固定表头（行号+列名），与数据体水平同步"""
        c = self._header_canvas
        c.delete("all")

        view_w = c.winfo_width()
        row_num_w = 55

        # 行号列
        c.create_rectangle(0, 0, row_num_w, self._header_h,
                           fill="#222", outline="#444", width=1)
        c.create_text(row_num_w // 2, self._header_h // 2, anchor="center",
                      text="#", fill=HEADER_FG, font=FONT_HEADER)

        # 数据列表头
        x = row_num_w - self._xofs
        for i in range(self._ncols):
            w = self._col_widths[i]
            if x + w < row_num_w:  # 左侧不可见
                x += w
                continue
            if x > view_w:  # 右侧不可见
                break
            draw_x = max(x, row_num_w)
            draw_w = w - (draw_x - x)
            if draw_w <= 0:
                x += w
                continue

            c.create_rectangle(draw_x, 0, draw_x + draw_w, self._header_h,
                               fill=HEADER_BG, outline="#444", width=1)
            txt = self._columns[i]
            # 截断过长的列名
            max_chars = max(1, int((draw_w - 10) / 8))
            if len(txt) > max_chars and max_chars > 3:
                txt = txt[:max_chars-2] + ".."
            c.create_text(draw_x + 5, self._header_h // 2, anchor="w",
                          text=txt, fill=HEADER_FG, font=FONT_HEADER)
            x += w

    # ── 滚动 ──

    def _on_vscroll(self, *args):
        self._vbar.set(*args)
        self._yofs = float(args[0]) * self._total_h
        self._update_view()

    def _on_hscroll(self, *args):
        self._hbar.set(*args)
        self._xofs = float(args[0]) * self._total_w
        self._draw_header()
        self._update_view()

    def _on_hbar_scroll(self, *args):
        view_w = max(1, self._canvas.winfo_width())
        if args[0] == "moveto":
            frac = float(args[1])
            self._xofs = frac * self._total_w
        elif args[0] == "scroll":
            units = int(args[1])
            direction = args[2]
            if direction == "units":
                self._xofs += units * 20
            else:
                self._xofs += units * view_w * 0.8
            self._xofs = max(0, min(self._xofs, self._total_w - view_w))

        self._xofs = max(0, min(self._xofs, max(1, self._total_w - 100)))
        self._update_scroll_region()
        self._draw_header()
        self._update_view()

    def _update_scroll_region(self):
        view_w = max(100, self._canvas.winfo_width())
        view_h = max(100, self._canvas.winfo_height())
        self._canvas.config(scrollregion=(0, 0, self._total_w, self._total_h))

        # 更新滚动条
        if self._total_w > view_w:
            frac = view_w / self._total_w
            first = self._xofs / self._total_w
            self._hbar.set(first, first + frac)
        else:
            self._hbar.set(0, 1)

        if self._total_h > view_h:
            frac = view_h / self._total_h
            first = self._yofs / self._total_h
            self._vbar.set(first, first + frac)
        else:
            self._vbar.set(0, 1)

    def _on_canvas_resize(self, event):
        self._update_scroll_region()
        self._draw_header()
        self._update_view()

    def _on_mousewheel(self, event):
        """鼠标滚轮滚动"""
        delta = event.delta
        # Windows: delta 是 120 的倍数
        step = max(1, self._row_h)
        if delta > 0:
            self._yofs = max(0, self._yofs - step * 3)
        else:
            view_h = self._canvas.winfo_height()
            self._yofs = min(self._total_h - view_h, self._yofs + step * 3)
            self._yofs = max(0, self._yofs)

        self._update_scroll_region()
        self._update_view()

    # ── 点击/选中 ──
    def _on_cell_click(self, event):
        x = event.x
        y = event.y
        row = int((y + self._yofs) / self._row_h)
        if 0 <= row < self._nrows:
            self._selected_row = row
            self._update_view()

    def _on_cell_drag(self, event):
        self._on_cell_click(event)

    def _on_header_click(self, event):
        pass

    # ── 清理 ──
    def clear(self):
        """销毁 _table_frame 内所有子控件，重置状态"""
        if self._loading_progress:
            try: self._loading_progress.stop()
            except: pass
        self._loading_progress = None
        self._loading_label = None
        self._placeholder_label = None
        self._data = None
        self._canvas = None
        self._header_canvas = None
        self._vbar = None
        self._hbar = None
        # 销毁 _table_frame 内所有子控件
        for w in list(self._table_frame.winfo_children()):
            w.destroy()

# ══════════════════════════════════════════
# 主应用
# ══════════════════════════════════════════
class SavReaderApp:
    def __init__(self):
        self.root = TkinterDnD.Tk()
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.geometry(f"{DEFAULT_W}x{DEFAULT_H}")
        self._try_set_icon()
        self.root.report_callback_exception = self._tk_excepthook
        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind("<<Drop>>", self._on_drop)
        self.df = None
        self.meta = None
        self.current_path = None
        self._stats_cache = {}
        self._build_ui()
        self.root.bind("<Control-o>", lambda e: self._open_file())
        self.root.bind("<Control-s>", lambda e: self._export_csv())
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _try_set_icon(self):
        ico = Path(__file__).parent / "icon.ico"
        if ico.exists():
            try: self.root.iconbitmap(str(ico))
            except: pass

    def _tk_excepthook(self, exc_type, exc_value, exc_traceback):
        msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        desk = Path.home() / "Desktop" / "sav_reader_error.log"
        try: desk.write_text(msg, encoding="utf-8")
        except: pass
        messagebox.showerror("程序异常", f"发生错误:\n\n{exc_value}\n\n详情已保存到桌面 sav_reader_error.log")

    def _build_ui(self):
        # 菜单栏
        menu_frame = ctk.CTkFrame(self.root, height=40, fg_color="#1a1a1a")
        menu_frame.pack(fill="x", padx=0, pady=0)
        menu_frame.pack_propagate(False)
        btn_open = ctk.CTkButton(menu_frame, text=" 打开文件", width=120, command=self._open_file)
        btn_open.pack(side="left", padx=8, pady=5)
        btn_export = ctk.CTkButton(menu_frame, text=" 导出 CSV", width=110, command=self._export_csv)
        btn_export.pack(side="left", padx=8, pady=5)
        self.info_label = ctk.CTkLabel(menu_frame, text="", font=ctk.CTkFont(size=12), text_color="#888888")
        self.info_label.pack(side="right", padx=15, pady=5)

        # 主区域
        main_pane = ctk.CTkFrame(self.root)
        main_pane.pack(fill="both", expand=True, padx=5, pady=5)
        main_pane.grid_rowconfigure(0, weight=1)
        main_pane.grid_columnconfigure(0, weight=1)
        main_pane.grid_columnconfigure(1, weight=0)

        # 左侧
        left_frame = ctk.CTkFrame(main_pane)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0,2))
        left_frame.grid_rowconfigure(0, weight=1)
        left_frame.grid_rowconfigure(1, weight=0)

        self.data_view = DataTableView(left_frame)
        self.data_view.pack(fill="both", expand=True, padx=0, pady=0)

        # 底部日志
        log_frame = ctk.CTkFrame(left_frame, height=80, fg_color="#1a1a1a")
        log_frame.pack(fill="x", pady=(2,0))
        log_frame.pack_propagate(False)
        log_header = ctk.CTkLabel(log_frame, text=" 日志", font=ctk.CTkFont(size=11, weight="bold"), text_color="#888888")
        log_header.pack(anchor="w", padx=10, pady=(2,0))
        self.log = LogFrame(log_frame, fg_color="#1a1a1a")
        self.log.pack(fill="both", expand=True, padx=5, pady=(0,5))
        self.log.write(f"{APP_NAME} v{APP_VERSION} 已启动。", "SYSTEM")

        # 右侧变量面板
        right_frame = ctk.CTkFrame(main_pane, width=320)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(2,0))
        right_frame.grid_propagate(False)
        right_header = ctk.CTkLabel(right_frame, text=" 变量信息", font=ctk.CTkFont(size=14, weight="bold"), text_color="#e0e0e0")
        right_header.pack(pady=(10,5))
        self.var_listbox = ctk.CTkScrollableFrame(right_frame, fg_color="transparent")
        self.var_listbox.pack(fill="both", expand=True, padx=5, pady=5)
        self.var_detail_frame = ctk.CTkFrame(right_frame, fg_color="#1e1e1e")
        self.var_detail_frame.pack(fill="x", padx=5, pady=(0,10))
        self.var_detail_text = ctk.CTkTextbox(self.var_detail_frame, height=200,
                                               fg_color="#1e1e1e", text_color="#cccccc",
                                               font=ctk.CTkFont(size=11, family="Consolas"),
                                               wrap="word", state="disabled")
        self.var_detail_text.pack(fill="both", padx=5, pady=5)
        self._show_empty_var_panel()

    def _show_empty_var_panel(self):
        for w in self.var_listbox.winfo_children(): w.destroy()
        self.var_detail_text.configure(state="normal")
        self.var_detail_text.delete("1.0", "end")
        self.var_detail_text.insert("1.0", "打开 .sav 文件后\n显示变量详情")
        self.var_detail_text.configure(state="disabled")

    # ── 文件操作 ──
    def _open_file(self):
        path = filedialog.askopenfilename(title="选择 SPSS 数据文件",
            filetypes=[("SPSS 数据文件", "*.sav"), ("所有文件", "*.*")])
        if path: self._load_file(path)

    def _on_drop(self, event):
        raw = event.data
        files = re.findall(r'\{([^}]*)\}|(\S+)', raw)
        paths = [a or b for a, b in files if (a or b)]
        for p in paths:
            if p.lower().endswith(".sav"):
                self._load_file(p)
                return
        self.log.write("拖入的文件不是 .sav 格式", "WARN")

    def _load_file(self, path):
        if not os.path.isfile(path):
            self.log.write(f"文件不存在: {path}", "ERROR")
            return
        name = os.path.basename(path)
        self.log.write(f"正在读取: {name} ...", "INFO")
        self.current_path = path
        self.root.title(f"{APP_NAME} - {name}")
        self.data_view.show_loading(name)
        threading.Thread(target=self._do_load, args=(path,), daemon=True).start()

    def _do_load(self, path):
        try:
            df, meta = pyreadstat.read_sav(path, encoding="utf-8")
        except UnicodeDecodeError:
            try:
                df, meta = pyreadstat.read_sav(path, encoding="utf-16")
            except Exception as e2:
                self.root.after(0, lambda: self._load_error(f"编码错误: {e2}"))
                return
        except Exception as e:
            self.root.after(0, lambda: self._load_error(str(e)))
            return
        self.root.after(0, lambda: self._load_done(df, meta, path))

    def _load_error(self, msg):
        self.data_view.show_placeholder()
        self.log.write(f"读取失败: {msg}", "ERROR")
        messagebox.showerror("读取错误", f"无法读取文件:\n{msg}")

    def _load_done(self, df, meta, path):
        self.df = df
        self.meta = meta
        name = os.path.basename(path)
        n_rows, n_cols = df.shape
        try:
            self.data_view.load_data(df, meta)
        except Exception as e:
            self.data_view.show_placeholder()
            self.log.write(f"渲染失败: {e}", "ERROR")
            traceback.print_exc()
            return
        missing = int(df.isna().sum().sum())
        self.info_label.configure(text=f" 行: {n_rows:,}  |  列: {n_cols}  |  缺失值: {missing:,}  |  {name}")
        self._update_var_panel_async(df, meta)
        self.log.write(f" 加载完成: {n_rows} 行 x {n_cols} 列, 缺失值 {missing}", "OK")

    # ── 变量面板 ──
    def _update_var_panel_async(self, df, meta):
        for w in self.var_listbox.winfo_children(): w.destroy()
        columns = list(df.columns)
        variable_labels = {}
        if hasattr(meta, 'variable_labels') and meta.variable_labels:
            variable_labels = meta.variable_labels
        self._var_buttons = []
        for i, col in enumerate(columns):
            dtype = str(df[col].dtype)
            lbl_text = variable_labels.get(col, "")
            lbl_short = f"「{lbl_text[:25]}」" if lbl_text else ""
            btn = ctk.CTkButton(self.var_listbox,
                text=f"{col}  [{dtype}] {lbl_short}",
                anchor="w", fg_color="#2d2d2d", hover_color="#3a3a3a",
                text_color="#cccccc", font=ctk.CTkFont(size=11, family="Consolas"),
                command=lambda c=col, idx=i: self._show_var_detail(c, idx))
            btn.pack(fill="x", padx=2, pady=1)
            self._var_buttons.append(btn)
        if columns:
            self._show_var_detail(columns[0], 0)
        threading.Thread(target=self._precompute_stats, args=(df, meta, columns), daemon=True).start()

    def _precompute_stats(self, df, meta, columns):
        stats = {}
        for col_name in columns:
            try:
                col = df[col_name]
                info = {"dtype": str(col.dtype)}
                n_miss = int(col.isna().sum())
                info["missing"] = n_miss
                info["missing_pct"] = n_miss / len(col) * 100 if len(col) else 0
                info["nunique"] = int(col.nunique())
                if col.dtype in ('float64','int64','int32','float32'):
                    c = col.dropna()
                    if len(c) > 0:
                        info["min"] = float(c.min())
                        info["max"] = float(c.max())
                        info["mean"] = float(c.mean())
                        info["median"] = float(c.median())
                        info["std"] = float(c.std())
                        info["var"] = float(c.var())
                        info["q1"] = float(c.quantile(0.25))
                        info["q3"] = float(c.quantile(0.75))
                if info["nunique"] <= 50 and col.dtype != 'float64' and info["nunique"] > 0:
                    vc = col.value_counts().head(20)
                    info["value_counts"] = {str(k): int(v) for k, v in vc.items()}
                stats[col_name] = info
            except Exception:
                stats[col_name] = {"dtype": str(col.dtype)}
        self._stats_cache = stats

    def _show_var_detail(self, col_name, idx=0):
        if self.df is None: return
        for i, btn in enumerate(getattr(self,'_var_buttons',[])):
            btn.configure(fg_color="#3a3a3a" if i == idx else "#2d2d2d")
        meta = self.meta
        col = self.df[col_name]
        lines = [f"变量名: {col_name}", f"数据类型: {col.dtype}"]
        if hasattr(meta,'variable_labels') and meta.variable_labels:
            lbl = meta.variable_labels.get(col_name,"")
            if lbl: lines.append(f"标签: {lbl}")
        if hasattr(meta,'measure') and meta.measure:
            m = meta.measure.get(col_name,"")
            m_map = {1:"名义(Nominal)",2:"有序(Ordinal)",3:"度量(Scale)"}
            lines.append(f"测量级别: {m_map.get(m, str(m))}")
        if hasattr(meta,'variable_value_labels') and meta.variable_value_labels:
            vvl = meta.variable_value_labels.get(col_name,{})
            if vvl:
                lines.append(f"值标签 ({len(vvl)}个):")
                for k,v in list(vvl.items())[:20]: lines.append(f"  {k} -> {v}")
                if len(vvl)>20: lines.append(f"  ... 还有 {len(vvl)-20} 个")
        stat = self._stats_cache.get(col_name,{})
        if stat:
            n_miss = stat.get("missing",0)
            if n_miss>0: lines.append(f"缺失值: {n_miss} / {len(col)} ({stat['missing_pct']:.1f}%)")
            lines.append(f"唯一值: {stat.get('nunique',0)}")
            vc = stat.get("value_counts")
            if vc:
                lines.append("值分布:")
                total = sum(vc.values()) or 1
                for val,cnt in vc.items(): lines.append(f"  {str(val):<15} {cnt:>6} ({cnt/total*100:5.1f}%)")
            if "mean" in stat:
                lines.append("描述统计:")
                for k,v in [("最小值","min"),("最大值","max"),("均值","mean"),("中位数","median"),
                             ("标准差","std"),("方差","var"),("Q1","q1"),("Q3","q3")]:
                    if v in stat: lines.append(f"  {k}:   {stat[v]:.4f}")
        else:
            lines.append("[统计计算中...]")
        self.var_detail_text.configure(state="normal")
        self.var_detail_text.delete("1.0","end")
        self.var_detail_text.insert("1.0", "\n".join(lines))
        self.var_detail_text.configure(state="disabled")

    # ── 导出 ──
    def _export_csv(self):
        if self.df is None: messagebox.showinfo("提示","请先打开一个 .sav 文件"); return
        path = filedialog.asksaveasfilename(title="导出为 CSV",
            defaultextension=".csv", filetypes=[("CSV 文件","*.csv"),("所有文件","*.*")],
            initialfile=os.path.splitext(os.path.basename(self.current_path or "data"))[0]+".csv")
        if not path: return
        self.log.write(f"正在导出: {os.path.basename(path)} ...","INFO")
        threading.Thread(target=self._do_export_csv, args=(path,), daemon=True).start()

    def _do_export_csv(self, path):
        try:
            self.df.to_csv(path, index=False, encoding="utf-8-sig")
            self.root.after(0, lambda: self.log.write(f" 导出成功: {os.path.basename(path)}","OK"))
        except Exception as e:
            self.root.after(0, lambda: self.log.write(f"导出失败: {e}","ERROR"))

    def _on_close(self): self.root.destroy()
    def run(self): self.root.mainloop()

if __name__ == "__main__":
    app = SavReaderApp()
    app.run()
