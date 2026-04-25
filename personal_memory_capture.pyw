# -*- coding: utf-8 -*-
"""
personal_memory_capture.pyw

低摩擦个人记忆捕捉器｜Notion / Craft 风格卡片界面

运行方式：
    双击 personal_memory_capture.pyw

快捷键：
    Ctrl + Alt + M：呼出记录窗口
    Ctrl + Alt + Shift + Q：退出后台监听

依赖：
    pip install customtkinter keyboard

文件结构：
    00_raw_archive      保存每次记录的完整快照
    01_people           人｜观察，按对象长期更新
    02_events           事｜复盘，每次生成独立文件
    03_relationships    关系｜网络更新，按对象长期更新
    04_free_notes       自由｜随手记录，每次生成独立文件
    index.md            机器索引，一行对应一次保存
    daily_updates.md    人类可读目录，按年、月、日整理每日更新
"""

from __future__ import annotations

import os
import re
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta, date
from pathlib import Path
from collections import defaultdict
import tkinter as tk
from tkinter import messagebox


try:
    import customtkinter as ctk
except Exception as exc:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "缺少依赖",
        "这个版本需要安装 customtkinter。\n\n"
        "请在 PowerShell 里运行：\n\n"
        "pip install customtkinter\n\n"
        f"错误信息：{exc}",
    )
    sys.exit(1)


# ============================================================
# 主要配置：通常只需要改这里
# ============================================================

BASE_DIR = Path(r"D:\26SPRING\Project3-个人记忆系统")

HOTKEY_CAPTURE = "ctrl+alt+m"
HOTKEY_QUIT = "ctrl+alt+shift+q"

APP_TITLE = "个人记忆捕捉器"

INSERT_NEWEST_FIRST = False
# False：同一个栏目下按时间顺序往下追加
# True：最新记录插到栏目最上方


# ============================================================
# 视觉配置
# ============================================================

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

COLOR_BG = "#F6F5F2"
COLOR_CARD = "#FFFFFF"
COLOR_SUBCARD = "#FAFAF8"
COLOR_BORDER = "#E7E3DC"
COLOR_TEXT = "#1F1F1F"
COLOR_MUTED = "#7A756E"
COLOR_ACCENT = "#2563EB"
COLOR_ACCENT_HOVER = "#1D4ED8"

FONT_TITLE = ("Microsoft YaHei UI", 24, "bold")
FONT_SUBTITLE = ("Microsoft YaHei UI", 12)
FONT_LABEL = ("Microsoft YaHei UI", 14, "bold")
FONT_HINT = ("Microsoft YaHei UI", 11)
FONT_BODY = ("Microsoft YaHei UI", 13)
FONT_BUTTON = ("Microsoft YaHei UI", 13, "bold")
FONT_SMALL = ("Microsoft YaHei UI", 11)


def place_window_on_screen(
    win,
    width_ratio: float = 0.70,
    height_ratio: float = 0.80,
    max_width: int = 900,
    max_height: int = 760,
    min_width: int = 720,
    min_height: int = 560,
) -> tuple[int, int]:
    """
    根据当前屏幕尺寸自动设置窗口大小，并尽量保证窗口完整显示在屏幕内。
    """
    win.update_idletasks()

    screen_w = win.winfo_screenwidth()
    screen_h = win.winfo_screenheight()

    width = min(max_width, max(min_width, int(screen_w * width_ratio)))
    height = min(max_height, max(min_height, int(screen_h * height_ratio)))

    width = min(width, max(520, screen_w - 80))
    height = min(height, max(420, screen_h - 120))

    x = max(20, (screen_w - width) // 2)
    y = max(20, (screen_h - height) // 2)

    win.geometry(f"{width}x{height}+{x}+{y}")

    return width, height


# ============================================================
# 表单结构
# ============================================================

@dataclass(frozen=True)
class FieldSpec:
    name: str
    hint: str = ""
    height: int = 120
    optional: bool = False


CATEGORIES = [
    "人｜观察",
    "事｜复盘",
    "关系｜网络更新",
    "自由｜随手记录",
]


PERSON_SECTIONS = [
    "我观察到的信息",
    "我的理解",
    "信息来源",
    "行动指南（可选）",
]


RELATION_SECTIONS = [
    "基本信息",
    "关系定位 / 关系感受",
    "新的交互",
    "我对这个人的认识是否更新",
    "行动指南",
]


TEMPLATES: dict[str, list[FieldSpec]] = {
    "人｜观察": [
        FieldSpec(
            name="我观察到的信息",
            hint="写具体事实、行为、偏好、表达方式、反复出现的细节。说不清时，可以直接写：暂时说不清，但当时的感觉是……",
            height=130,
        ),
        FieldSpec(
            name="我的理解",
            hint="基于上面的观察，我暂时怎样理解这个人？这个理解可以不确定，也可以以后推翻。",
            height=130,
        ),
        FieldSpec(
            name="信息来源",
            hint="这个观察来自哪一次相处、聊天、事件、别人转述、公开材料，还是长期感受？",
            height=110,
        ),
        FieldSpec(
            name="行动指南（可选）",
            hint="之后和这个人相处、聊天、合作、送礼、保持边界时，可以注意什么？",
            height=110,
            optional=True,
        ),
    ],

    "事｜复盘": [
        FieldSpec(
            name="事件简述",
            hint="用几句话写清楚时间、地点、人物、起因、经过、结果。不完整也可以。",
            height=130,
        ),
        FieldSpec(
            name="我的感知",
            hint="我有什么感受？我当时怎样认识这件事？哪些是事实，哪些可能是我的解释？",
            height=130,
        ),
        FieldSpec(
            name="我的行动",
            hint="我实际做了什么？比如沉默、解释、拒绝、转移话题、继续推进。",
            height=110,
        ),
        FieldSpec(
            name="结果怎么样",
            hint="外部结果如何？我自己的内部感受如何？有没有轻松、后悔、清楚、消耗？",
            height=110,
        ),
        FieldSpec(
            name="下一次行动指南（可选）",
            hint="如果类似事情再次发生，我想保留、改变或尝试什么？",
            height=110,
            optional=True,
        ),
    ],

    "关系｜网络更新": [
        FieldSpec(
            name="基本信息",
            hint="身份、场景、我们怎么认识的、常见交集、重要背景。已经写过的内容不用重复，除非有更新。",
            height=110,
        ),
        FieldSpec(
            name="关系定位 / 关系感受",
            hint="我现在怎样理解这段关系？它让我感到信任、轻松、紧张、消耗、被支持、被评价，还是边界不清？它目前主要承担什么关系功能？",
            height=140,
        ),
        FieldSpec(
            name="新的交互",
            hint="最近一次发生了什么？对方说了什么、做了什么？我当时有什么反应？",
            height=130,
        ),
        FieldSpec(
            name="我对这个人的认识是否更新",
            hint="这次交互让我对 TA 的理解有变化吗？还是重复验证了我之前的判断？",
            height=110,
        ),
        FieldSpec(
            name="行动指南",
            hint="接下来我要靠近、维持、观察、减少投入，还是明确边界？下次互动时具体可以怎么做？",
            height=110,
        ),
    ],

    "自由｜随手记录": [
        FieldSpec(
            name="主题",
            hint="这条记录大概关于什么？",
            height=70,
        ),
        FieldSpec(
            name="原始想法",
            hint="不需要整理，直接保留当时的念头。",
            height=160,
        ),
        FieldSpec(
            name="可能的重要性",
            hint="它为什么可能值得留下？可能和哪个问题、项目、关系、长期主题有关？",
            height=110,
        ),
        FieldSpec(
            name="之后可以如何使用（可选）",
            hint="之后可以变成文章、行动、问题清单、复盘材料，还是只是留档？",
            height=110,
            optional=True,
        ),
    ],
}


FOLDER_MAP = {
    "人｜观察": "01_people",
    "事｜复盘": "02_events",
    "关系｜网络更新": "03_relationships",
    "自由｜随手记录": "04_free_notes",
}


OBJECT_BASED_CATEGORIES = {
    "人｜观察",
    "关系｜网络更新",
}


PENDING_WORDS = [
    "暂时说不清",
    "说不清",
    "待整理",
    "没想明白",
    "以后再想",
    "之后再整理",
]


# ============================================================
# 时间与文件工具
# ============================================================

def entry_id_now() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def human_time_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure_dirs() -> None:
    BASE_DIR.mkdir(parents=True, exist_ok=True)

    (BASE_DIR / "00_raw_archive").mkdir(parents=True, exist_ok=True)

    for folder in FOLDER_MAP.values():
        (BASE_DIR / folder).mkdir(parents=True, exist_ok=True)

    index_file = BASE_DIR / "index.md"
    if not index_file.exists():
        index_file.write_text(
            "# 个人记忆系统索引\n\n"
            "这里会自动追加每一次记录，方便程序统计、追踪 Raw Snapshot 和生成热力图。\n\n",
            encoding="utf-8",
        )

    daily_file = BASE_DIR / "daily_updates.md"
    if not daily_file.exists():
        daily_file.write_text(
            "# 每日更新目录\n\n"
            "> 本文件由程序根据 index.md 自动生成。没有记录的日期不会显示。\n",
            encoding="utf-8",
        )


def safe_filename(text: str, fallback: str = "untitled") -> str:
    text = (text or "").strip()

    if not text:
        text = fallback

    text = re.sub(r"[\\/:*?\"<>|]", "_", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text[:80]

    return text or fallback


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def append_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(content)


def log_error(exc: BaseException) -> None:
    try:
        ensure_dirs()
        error_file = BASE_DIR / "error_log.txt"
        append_text(
            error_file,
            f"\n\n[{human_time_now()}]\n"
            f"{''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))}\n",
        )
    except Exception:
        pass


def has_pending_marker(text: str) -> bool:
    return any(word in text for word in PENDING_WORDS)


def get_existing_names(category: str) -> list[str]:
    folder = BASE_DIR / FOLDER_MAP[category]

    if not folder.exists():
        return []

    names = []

    for path in folder.glob("*.md"):
        if path.name.lower() == "index.md":
            continue
        names.append(path.stem)

    return sorted(set(names), key=lambda x: x.lower())


# ============================================================
# 索引解析与每日目录
# ============================================================

INDEX_LINE_RE = re.compile(
    r"^- \[(?P<entry_id>\d{8}_\d{6})｜(?P<dt>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] "
    r"\*\*(?P<category>.+?)\*\*｜\[(?P<title>.*?)\]\((?P<target>.*?)\)｜Raw:",
    flags=re.MULTILINE,
)


def parse_index_entries() -> list[dict]:
    ensure_dirs()

    index_file = BASE_DIR / "index.md"
    text = read_text(index_file)

    entries: list[dict] = []

    for match in INDEX_LINE_RE.finditer(text):
        dt_text = match.group("dt")

        try:
            dt_obj = datetime.strptime(dt_text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue

        entries.append(
            {
                "entry_id": match.group("entry_id"),
                "dt": dt_obj,
                "date": dt_obj.date(),
                "time": dt_obj.strftime("%H:%M"),
                "category": match.group("category"),
                "title": match.group("title"),
                "target": match.group("target"),
            }
        )

    entries.sort(key=lambda item: item["dt"])
    return entries


def rebuild_daily_updates() -> None:
    ensure_dirs()

    entries = parse_index_entries()

    daily_file = BASE_DIR / "daily_updates.md"

    if not entries:
        write_text(
            daily_file,
            "# 每日更新目录\n\n"
            "> 本文件由程序根据 index.md 自动生成。没有记录的日期不会显示。\n",
        )
        return

    grouped: dict[int, dict[str, dict[date, list[dict]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    for entry in entries:
        dt_obj: datetime = entry["dt"]
        year = dt_obj.year
        month_key = dt_obj.strftime("%Y-%m")
        day = dt_obj.date()
        grouped[year][month_key][day].append(entry)

    lines = [
        "# 每日更新目录\n\n",
        "> 本文件由程序根据 index.md 自动生成。没有记录的日期不会显示。\n\n",
    ]

    for year in sorted(grouped.keys()):
        lines.append(f"## {year}\n\n")

        for month_key in sorted(grouped[year].keys()):
            lines.append(f"### {month_key}\n\n")

            for day in sorted(grouped[year][month_key].keys()):
                day_entries = grouped[year][month_key][day]
                lines.append(f"#### {day.isoformat()}\n\n")
                lines.append(f"**今日更新：{len(day_entries)} 条**\n\n")

                for entry in day_entries:
                    lines.append(
                        f"- [{entry['time']}] "
                        f"**{entry['category']}**｜"
                        f"[{entry['title']}]({entry['target']})\n"
                    )

                lines.append("\n")

    write_text(daily_file, "".join(lines))


# ============================================================
# Markdown 写入逻辑
# ============================================================

def make_multiline_bullet(entry_id: str, human_time: str, content: str) -> str:
    clean = content.strip()
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    clean = clean.replace("\n", "\n  ")

    return f"- [{entry_id}｜{human_time}] {clean}\n"


def ensure_sectioned_object_file(
    path: Path,
    object_name: str,
    category: str,
    sections: list[str],
    human_time: str,
) -> None:
    if path.exists():
        text = read_text(path)
    else:
        text = (
            f"# {object_name}\n\n"
            f"**类型**：{category}\n\n"
            f"**创建时间**：{human_time}\n\n"
            f"---\n\n"
        )

    changed = False

    for section in sections:
        pattern = rf"^## {re.escape(section)}\s*$"

        if not re.search(pattern, text, flags=re.MULTILINE):
            if not text.endswith("\n"):
                text += "\n"
            text += f"\n## {section}\n\n"
            changed = True

    if changed or not path.exists():
        write_text(path, text)


def insert_bullet_under_section(
    path: Path,
    section: str,
    bullet: str,
    newest_first: bool = False,
) -> None:
    text = read_text(path)

    heading_pattern = rf"(^## {re.escape(section)}\s*\n)"

    if not re.search(heading_pattern, text, flags=re.MULTILINE):
        if not text.endswith("\n"):
            text += "\n"
        text += f"\n## {section}\n\n"

    match = re.search(heading_pattern, text, flags=re.MULTILINE)

    if not match:
        text += f"\n## {section}\n\n{bullet}"
        write_text(path, text)
        return

    if newest_first:
        insert_pos = match.end()
        text = text[:insert_pos] + bullet + text[insert_pos:]
        write_text(path, text)
        return

    section_start = match.end()
    next_heading = re.search(r"^## .+\s*$", text[section_start:], flags=re.MULTILINE)

    if next_heading:
        insert_pos = section_start + next_heading.start()
        before = text[:insert_pos].rstrip()
        after = text[insert_pos:].lstrip("\n")
        text = before + "\n" + bullet + "\n" + after
    else:
        text = text.rstrip() + "\n" + bullet

    write_text(path, text)


def save_object_based_record(
    category: str,
    object_name: str,
    field_values: dict[str, str],
    entry_id: str,
    human_time: str,
) -> Path:
    filename = safe_filename(object_name)
    folder = BASE_DIR / FOLDER_MAP[category]
    target_file = folder / f"{filename}.md"

    sections = PERSON_SECTIONS if category == "人｜观察" else RELATION_SECTIONS

    ensure_sectioned_object_file(
        path=target_file,
        object_name=object_name,
        category=category,
        sections=sections,
        human_time=human_time,
    )

    for section in sections:
        value = field_values.get(section, "").strip()

        if value:
            bullet = make_multiline_bullet(
                entry_id=entry_id,
                human_time=human_time,
                content=value,
            )
            insert_bullet_under_section(
                path=target_file,
                section=section,
                bullet=bullet,
                newest_first=INSERT_NEWEST_FIRST,
            )

    return target_file


def build_single_record_markdown(
    category: str,
    title: str,
    field_values: dict[str, str],
    entry_id: str,
    human_time: str,
) -> str:
    lines = [
        f"# {title}\n\n",
        f"**Entry ID**：{entry_id}\n\n",
        f"**记录时间**：{human_time}\n\n",
        f"**分类**：{category}\n\n",
        "---\n\n",
    ]

    for spec in TEMPLATES[category]:
        value = field_values.get(spec.name, "").strip()

        if value or not spec.optional:
            lines.append(f"## {spec.name}\n\n")
            lines.append((value or "（未填写）") + "\n\n")

    return "".join(lines)


def save_single_record(
    category: str,
    title: str,
    field_values: dict[str, str],
    entry_id: str,
    human_time: str,
) -> Path:
    filename = safe_filename(title)
    folder = BASE_DIR / FOLDER_MAP[category]
    target_file = folder / f"{entry_id}_{filename}.md"

    markdown = build_single_record_markdown(
        category=category,
        title=title,
        field_values=field_values,
        entry_id=entry_id,
        human_time=human_time,
    )

    write_text(target_file, markdown)

    return target_file


def save_raw_snapshot(
    category: str,
    title: str,
    field_values: dict[str, str],
    entry_id: str,
    human_time: str,
) -> Path:
    filename = safe_filename(title)
    raw_file = BASE_DIR / "00_raw_archive" / f"{entry_id}_{filename}.md"

    lines = [
        f"# Raw Snapshot｜{title}\n\n",
        f"**Entry ID**：{entry_id}\n\n",
        f"**记录时间**：{human_time}\n\n",
        f"**分类**：{category}\n\n",
        "---\n\n",
    ]

    for key, value in field_values.items():
        lines.append(f"## {key}\n\n")
        lines.append((value.strip() or "（未填写）") + "\n\n")

    write_text(raw_file, "".join(lines))

    return raw_file


def append_index(
    category: str,
    title: str,
    target_file: Path,
    raw_file: Path,
    field_values: dict[str, str],
    entry_id: str,
    human_time: str,
) -> None:
    all_text = "\n".join(field_values.values())

    pending_mark = "｜**待提炼**" if has_pending_marker(all_text) else ""

    target_rel = target_file.relative_to(BASE_DIR).as_posix()
    raw_rel = raw_file.relative_to(BASE_DIR).as_posix()

    line = (
        f"- [{entry_id}｜{human_time}] "
        f"**{category}**｜"
        f"[{title}]({target_rel})｜"
        f"Raw: [{raw_file.name}]({raw_rel})"
        f"{pending_mark}\n"
    )

    append_text(BASE_DIR / "index.md", line)


def save_record(
    category: str,
    title_or_object: str,
    field_values: dict[str, str],
) -> tuple[Path, str, str]:
    ensure_dirs()

    entry_id = entry_id_now()
    human_time = human_time_now()

    title = title_or_object.strip()

    raw_file = save_raw_snapshot(
        category=category,
        title=title,
        field_values=field_values,
        entry_id=entry_id,
        human_time=human_time,
    )

    if category in OBJECT_BASED_CATEGORIES:
        target_file = save_object_based_record(
            category=category,
            object_name=title,
            field_values=field_values,
            entry_id=entry_id,
            human_time=human_time,
        )
    else:
        target_file = save_single_record(
            category=category,
            title=title,
            field_values=field_values,
            entry_id=entry_id,
            human_time=human_time,
        )

    append_index(
        category=category,
        title=title,
        target_file=target_file,
        raw_file=raw_file,
        field_values=field_values,
        entry_id=entry_id,
        human_time=human_time,
    )

    rebuild_daily_updates()

    return target_file, entry_id, human_time


# ============================================================
# 热力图统计
# ============================================================

def build_daily_counts() -> tuple[dict[date, int], dict[date, list[dict]]]:
    entries = parse_index_entries()

    counts: dict[date, int] = defaultdict(int)
    entries_by_date: dict[date, list[dict]] = defaultdict(list)

    for entry in entries:
        d = entry["date"]
        counts[d] += 1
        entries_by_date[d].append(entry)

    return dict(counts), dict(entries_by_date)


def calculate_streak(counts: dict[date, int], today: date) -> int:
    streak = 0
    current = today

    while counts.get(current, 0) > 0:
        streak += 1
        current -= timedelta(days=1)

    return streak


def heatmap_color(count: int) -> str:
    if count <= 0:
        return "#EBEDF0"
    if count == 1:
        return "#CDEFD6"
    if count <= 3:
        return "#7BC96F"
    if count <= 6:
        return "#239A3B"
    return "#196127"


# ============================================================
# UI 组件
# ============================================================

class FieldBlock(ctk.CTkFrame):
    def __init__(self, master, spec: FieldSpec):
        super().__init__(
            master,
            fg_color=COLOR_SUBCARD,
            corner_radius=18,
            border_width=1,
            border_color=COLOR_BORDER,
        )

        self.spec = spec

        title = spec.name
        if spec.optional and "可选" not in title:
            title += "（可选）"

        self.title_label = ctk.CTkLabel(
            self,
            text=title,
            font=FONT_LABEL,
            text_color=COLOR_TEXT,
            anchor="w",
        )
        self.title_label.pack(fill="x", padx=18, pady=(14, 2))

        self.hint_label = ctk.CTkLabel(
            self,
            text=spec.hint,
            font=FONT_HINT,
            text_color=COLOR_MUTED,
            anchor="w",
            justify="left",
            wraplength=760,
        )
        self.hint_label.pack(fill="x", padx=18, pady=(0, 8))

        self.textbox = ctk.CTkTextbox(
            self,
            height=spec.height,
            font=FONT_BODY,
            text_color=COLOR_TEXT,
            fg_color="#FFFFFF",
            border_width=1,
            border_color=COLOR_BORDER,
            corner_radius=12,
            wrap="word",
        )
        self.textbox.pack(fill="x", padx=18, pady=(0, 16))

    def get_text(self) -> str:
        return self.textbox.get("1.0", "end").strip()


# ============================================================
# 主应用
# ============================================================

class MemoryCaptureApp:
    def __init__(self, root: ctk.CTk):
        self.root = root
        self.capture_window: ctk.CTkToplevel | None = None
        self.heatmap_window: ctk.CTkToplevel | None = None

        self.category_var = tk.StringVar(value=CATEGORIES[0])
        self.target_var = tk.StringVar()

        self.category_menu: ctk.CTkOptionMenu | None = None
        self.target_entry: ctk.CTkComboBox | None = None
        self.target_label: ctk.CTkLabel | None = None
        self.scroll_frame: ctk.CTkScrollableFrame | None = None

        self.field_blocks: dict[str, FieldBlock] = {}

        self._category_trace_added = False
        self._target_trace_added = False
        self._filtering_target = False

        ensure_dirs()
        rebuild_daily_updates()

    def get_target_label_text(self, category: str) -> str:
        if category in {"人｜观察", "关系｜网络更新"}:
            return "姓名 / 对象"
        if category == "事｜复盘":
            return "事件标题"
        return "主题"

    def show_capture_window(self) -> None:
        if self.capture_window is not None and self.capture_window.winfo_exists():
            self.capture_window.lift()
            self.capture_window.focus_force()
            self.capture_window.attributes("-topmost", True)
            self.capture_window.after(300, lambda: self.capture_window.attributes("-topmost", True))
            return

        win = ctk.CTkToplevel(self.root)
        self.capture_window = win

        win.title(APP_TITLE)
        win.configure(fg_color=COLOR_BG)
        win.attributes("-topmost", True)

        place_window_on_screen(
            win,
            width_ratio=0.70,
            height_ratio=0.80,
            max_width=900,
            max_height=760,
            min_width=720,
            min_height=560,
        )

        win.minsize(680, 520)

        shell = ctk.CTkFrame(
            win,
            fg_color=COLOR_BG,
            corner_radius=0,
        )
        shell.pack(fill="both", expand=True, padx=26, pady=24)

        card = ctk.CTkFrame(
            shell,
            fg_color=COLOR_CARD,
            corner_radius=24,
            border_width=1,
            border_color=COLOR_BORDER,
        )
        card.pack(fill="both", expand=True)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=26, pady=(24, 12))

        title_label = ctk.CTkLabel(
            header,
            text="个人记忆捕捉器",
            font=FONT_TITLE,
            text_color=COLOR_TEXT,
            anchor="w",
        )
        title_label.pack(fill="x")

        subtitle_label = ctk.CTkLabel(
            header,
            text="把模糊感觉先留下，之后再慢慢提炼。顶部标题必填，内容字段可以只写有用的部分。",
            font=FONT_SUBTITLE,
            text_color=COLOR_MUTED,
            anchor="w",
        )
        subtitle_label.pack(fill="x", pady=(4, 0))

        controls = ctk.CTkFrame(card, fg_color="transparent")
        controls.pack(fill="x", padx=26, pady=(8, 16))

        left = ctk.CTkFrame(controls, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True, padx=(0, 10))

        right = ctk.CTkFrame(controls, fg_color="transparent")
        right.pack(side="left", fill="x", expand=True, padx=(10, 0))

        category_label = ctk.CTkLabel(
            left,
            text="分类",
            font=FONT_LABEL,
            text_color=COLOR_TEXT,
            anchor="w",
        )
        category_label.pack(fill="x", pady=(0, 6))

        self.category_menu = ctk.CTkOptionMenu(
            left,
            variable=self.category_var,
            values=CATEGORIES,
            command=lambda _: self.on_category_changed(),
            height=42,
            corner_radius=12,
            fg_color="#FFFFFF",
            button_color="#FFFFFF",
            button_hover_color="#F0EFEC",
            dropdown_fg_color="#FFFFFF",
            dropdown_hover_color="#F0EFEC",
            text_color=COLOR_TEXT,
            font=FONT_BODY,
            dropdown_font=FONT_BODY,
        )
        self.category_menu.pack(fill="x")

        self.target_label = ctk.CTkLabel(
            right,
            text=self.get_target_label_text(self.category_var.get()),
            font=FONT_LABEL,
            text_color=COLOR_TEXT,
            anchor="w",
        )
        self.target_label.pack(fill="x", pady=(0, 6))

        self.target_entry = ctk.CTkComboBox(
            right,
            variable=self.target_var,
            values=[],
            height=42,
            corner_radius=12,
            fg_color="#FFFFFF",
            border_color=COLOR_BORDER,
            button_color="#FFFFFF",
            button_hover_color="#F0EFEC",
            dropdown_fg_color="#FFFFFF",
            dropdown_hover_color="#F0EFEC",
            text_color=COLOR_TEXT,
            font=FONT_BODY,
            dropdown_font=FONT_BODY,
        )
        self.target_entry.pack(fill="x")

        try:
            self.target_entry._entry.bind("<KeyRelease>", self.on_target_keyrelease)
        except Exception:
            try:
                self.target_entry.bind("<KeyRelease>", self.on_target_keyrelease)
            except Exception:
                pass

        info_bar = ctk.CTkFrame(
            card,
            fg_color="#F8FAFC",
            corner_radius=16,
            border_width=1,
            border_color="#E5E7EB",
        )
        info_bar.pack(fill="x", padx=26, pady=(0, 16))

        info_label = ctk.CTkLabel(
            info_bar,
            text="“人”和“关系”会按同一个对象持续写入长期文档；daily_updates.md 会按日期整理每天更新了什么。",
            font=FONT_HINT,
            text_color=COLOR_MUTED,
            anchor="w",
            justify="left",
            wraplength=820,
        )
        info_label.pack(fill="x", padx=16, pady=10)

        self.scroll_frame = ctk.CTkScrollableFrame(
            card,
            fg_color="transparent",
            scrollbar_button_color="#D6D3CE",
            scrollbar_button_hover_color="#BFBAB2",
        )
        self.scroll_frame.pack(fill="both", expand=True, padx=26, pady=(0, 12))

        footer = ctk.CTkFrame(card, fg_color="transparent")
        footer.pack(fill="x", padx=26, pady=(0, 24))

        open_btn = ctk.CTkButton(
            footer,
            text="打开保存文件夹",
            font=FONT_BUTTON,
            height=42,
            corner_radius=12,
            fg_color="#FFFFFF",
            hover_color="#F0EFEC",
            text_color=COLOR_TEXT,
            border_width=1,
            border_color=COLOR_BORDER,
            command=self.open_base_dir,
        )
        open_btn.pack(side="left")

        heatmap_btn = ctk.CTkButton(
            footer,
            text="查看记录热力图",
            font=FONT_BUTTON,
            height=42,
            corner_radius=12,
            fg_color="#FFFFFF",
            hover_color="#F0EFEC",
            text_color=COLOR_TEXT,
            border_width=1,
            border_color=COLOR_BORDER,
            command=self.show_heatmap_window,
        )
        heatmap_btn.pack(side="left", padx=(10, 0))

        save_btn = ctk.CTkButton(
            footer,
            text="保存记录",
            font=FONT_BUTTON,
            height=42,
            corner_radius=12,
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            text_color="#FFFFFF",
            command=self.on_save,
        )
        save_btn.pack(side="right")

        close_btn = ctk.CTkButton(
            footer,
            text="关闭",
            font=FONT_BUTTON,
            height=42,
            corner_radius=12,
            fg_color="#FFFFFF",
            hover_color="#F0EFEC",
            text_color=COLOR_TEXT,
            border_width=1,
            border_color=COLOR_BORDER,
            command=win.destroy,
        )
        close_btn.pack(side="right", padx=(0, 10))

        self.rebuild_fields()
        self.update_target_area()

        if not self._category_trace_added:
            self.category_var.trace_add("write", lambda *_: self.on_category_changed())
            self._category_trace_added = True

        if not self._target_trace_added:
            self.target_var.trace_add("write", lambda *_: self.on_target_changed())
            self._target_trace_added = True

        self.target_entry.focus_set()

        win.bind("<Control-s>", lambda event: self.on_save())
        win.bind("<Escape>", lambda event: win.destroy())

        win.after(250, lambda: win.attributes("-topmost", False))

    def on_category_changed(self) -> None:
        self.target_var.set("")
        self.rebuild_fields()
        self.update_target_area()

    def update_target_area(self) -> None:
        category = self.category_var.get()

        if self.target_label is None or self.target_entry is None:
            return

        self.target_label.configure(text=self.get_target_label_text(category))

        if category in OBJECT_BASED_CATEGORIES:
            self.target_entry.configure(values=get_existing_names(category))
        else:
            self.target_entry.configure(values=[])

    def refresh_target_candidates(self) -> list[str]:
        category = self.category_var.get()

        if category not in OBJECT_BASED_CATEGORIES:
            return []

        if self.target_entry is None:
            return []

        typed = self.target_var.get().strip().lower()
        names = get_existing_names(category)

        if typed:
            matched = [name for name in names if typed in name.lower()]
        else:
            matched = names

        self._filtering_target = True
        try:
            self.target_entry.configure(values=matched)
        finally:
            self._filtering_target = False

        return matched

    def on_target_changed(self) -> None:
        if self._filtering_target:
            return

        self.refresh_target_candidates()

    def on_target_keyrelease(self, event=None) -> None:
        matched = self.refresh_target_candidates()
        typed_raw = self.target_var.get().strip()

        if typed_raw and matched:
            if self.target_entry is not None:
                self.target_entry.after(80, self.open_target_dropdown)

    def open_target_dropdown(self) -> None:
        if self.target_entry is None:
            return

        try:
            if not self.target_entry.winfo_exists():
                return

            self.target_entry.focus_set()

            if hasattr(self.target_entry, "_open_dropdown_menu"):
                self.target_entry._open_dropdown_menu()

        except Exception:
            pass

    def rebuild_fields(self) -> None:
        if self.scroll_frame is None:
            return

        for child in self.scroll_frame.winfo_children():
            child.destroy()

        self.field_blocks.clear()

        category = self.category_var.get()
        specs = TEMPLATES.get(category, [])

        for spec in specs:
            block = FieldBlock(self.scroll_frame, spec)
            block.pack(fill="x", pady=(0, 14))
            self.field_blocks[spec.name] = block

    def collect_field_values(self) -> dict[str, str]:
        values: dict[str, str] = {}

        for key, block in self.field_blocks.items():
            values[key] = block.get_text()

        return values

    def on_save(self) -> None:
        try:
            category = self.category_var.get()
            field_values = self.collect_field_values()
            title_or_object = self.target_var.get().strip()

            if not title_or_object:
                label_text = self.get_target_label_text(category)
                messagebox.showwarning(
                    f"缺少{label_text}",
                    f"请先填写{label_text}，这样 daily_updates.md 里的目录才会清楚。",
                )
                return

            if not any(value.strip() for value in field_values.values()):
                messagebox.showwarning(
                    "没有内容",
                    "你还没有填写任何记录内容。",
                )
                return

            target_file, entry_id, human_time = save_record(
                category=category,
                title_or_object=title_or_object,
                field_values=field_values,
            )

            messagebox.showinfo(
                "已保存",
                f"记录已经保存。\n\nEntry ID：{entry_id}\n时间：{human_time}\n\n{target_file}",
            )

            if self.capture_window is not None and self.capture_window.winfo_exists():
                self.capture_window.destroy()

        except Exception as exc:
            log_error(exc)
            messagebox.showerror(
                "保存失败",
                f"保存时出现错误：\n\n{exc}",
            )

    def open_base_dir(self) -> None:
        try:
            ensure_dirs()

            if sys.platform.startswith("win"):
                os.startfile(str(BASE_DIR))
            else:
                messagebox.showinfo("保存路径", str(BASE_DIR))

        except Exception as exc:
            log_error(exc)
            messagebox.showerror(
                "打开失败",
                str(exc),
            )

    def show_heatmap_window(self) -> None:
        try:
            ensure_dirs()
            counts, entries_by_date = build_daily_counts()

            if self.heatmap_window is not None and self.heatmap_window.winfo_exists():
                self.heatmap_window.lift()
                self.heatmap_window.focus_force()
                return

            win = ctk.CTkToplevel(self.root)
            self.heatmap_window = win

            win.title("记录热力图")
            win.geometry("1040x720")
            win.minsize(940, 640)
            win.configure(fg_color=COLOR_BG)

            shell = ctk.CTkFrame(win, fg_color=COLOR_BG, corner_radius=0)
            shell.pack(fill="both", expand=True, padx=26, pady=24)

            card = ctk.CTkFrame(
                shell,
                fg_color=COLOR_CARD,
                corner_radius=24,
                border_width=1,
                border_color=COLOR_BORDER,
            )
            card.pack(fill="both", expand=True)

            header = ctk.CTkFrame(card, fg_color="transparent")
            header.pack(fill="x", padx=26, pady=(24, 12))

            title = ctk.CTkLabel(
                header,
                text="记录热力图",
                font=FONT_TITLE,
                text_color=COLOR_TEXT,
                anchor="w",
            )
            title.pack(fill="x")

            subtitle = ctk.CTkLabel(
                header,
                text="从 index.md 读取记录。每个小方块代表一天，颜色越深表示当天记录越多。",
                font=FONT_SUBTITLE,
                text_color=COLOR_MUTED,
                anchor="w",
            )
            subtitle.pack(fill="x", pady=(4, 0))

            today = datetime.now().date()
            today_count = counts.get(today, 0)
            last7 = sum(counts.get(today - timedelta(days=i), 0) for i in range(7))
            last30 = sum(counts.get(today - timedelta(days=i), 0) for i in range(30))
            total_entries = sum(counts.values())
            total_days = len(counts)
            streak = calculate_streak(counts, today)

            stats_frame = ctk.CTkFrame(card, fg_color="transparent")
            stats_frame.pack(fill="x", padx=26, pady=(8, 14))

            stats = [
                ("Today", f"{today_count} 条"),
                ("Last 7 days", f"{last7} 条"),
                ("Last 30 days", f"{last30} 条"),
                ("Total records", f"{total_entries} 条"),
                ("Active days", f"{total_days} 天"),
                ("Streak", f"{streak} 天"),
            ]

            for label, value in stats:
                block = ctk.CTkFrame(
                    stats_frame,
                    fg_color=COLOR_SUBCARD,
                    corner_radius=16,
                    border_width=1,
                    border_color=COLOR_BORDER,
                )
                block.pack(side="left", fill="x", expand=True, padx=(0, 8))

                value_label = ctk.CTkLabel(
                    block,
                    text=value,
                    font=("Microsoft YaHei UI", 18, "bold"),
                    text_color=COLOR_TEXT,
                )
                value_label.pack(pady=(10, 0))

                name_label = ctk.CTkLabel(
                    block,
                    text=label,
                    font=FONT_SMALL,
                    text_color=COLOR_MUTED,
                )
                name_label.pack(pady=(0, 10))

            heatmap_frame = ctk.CTkFrame(
                card,
                fg_color=COLOR_SUBCARD,
                corner_radius=18,
                border_width=1,
                border_color=COLOR_BORDER,
            )
            heatmap_frame.pack(fill="x", padx=26, pady=(0, 14))

            canvas_width = 920
            canvas_height = 190
            canvas = tk.Canvas(
                heatmap_frame,
                width=canvas_width,
                height=canvas_height,
                bg=COLOR_SUBCARD,
                highlightthickness=0,
            )
            canvas.pack(fill="x", padx=18, pady=18)

            detail_box = ctk.CTkTextbox(
                card,
                height=170,
                font=FONT_BODY,
                text_color=COLOR_TEXT,
                fg_color="#FFFFFF",
                border_width=1,
                border_color=COLOR_BORDER,
                corner_radius=14,
                wrap="word",
            )
            detail_box.pack(fill="both", expand=True, padx=26, pady=(0, 18))

            def show_day_detail(day: date) -> None:
                detail_box.configure(state="normal")
                detail_box.delete("1.0", "end")

                day_entries = entries_by_date.get(day, [])

                if not day_entries:
                    detail_box.insert("end", f"{day.isoformat()}｜0 条记录\n")
                    detail_box.configure(state="disabled")
                    return

                detail_box.insert("end", f"{day.isoformat()}｜{len(day_entries)} 条记录\n\n")

                for entry in sorted(day_entries, key=lambda item: item["dt"]):
                    detail_box.insert(
                        "end",
                        f"[{entry['time']}] {entry['category']}｜{entry['title']}\n\n",
                    )
                detail_box.configure(state="disabled")

            start = today - timedelta(days=364)
            aligned_start = start - timedelta(days=start.weekday())

            cell = 13
            gap = 4
            left_pad = 38
            top_pad = 34

            weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            for i, weekday in enumerate(weekdays):
                y = top_pad + i * (cell + gap) + cell / 2
                canvas.create_text(
                    18,
                    y,
                    text=weekday,
                    fill=COLOR_MUTED,
                    font=("Segoe UI", 8),
                    anchor="center",
                )

            month_names = [
                "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
            ]

            month_positions: dict[tuple[int, int], int] = {}

            total_days_to_draw = (today - aligned_start).days + 1
            total_weeks = total_days_to_draw // 7 + 1

            rect_to_info: dict[int, dict] = {}

            for offset in range(total_weeks * 7):
                current_day = aligned_start + timedelta(days=offset)
                week = offset // 7
                weekday = current_day.weekday()

                x1 = left_pad + week * (cell + gap)
                y1 = top_pad + weekday * (cell + gap)
                x2 = x1 + cell
                y2 = y1 + cell

                if current_day > today:
                    fill = "#F3F4F6"
                    outline = "#F3F4F6"
                else:
                    count = counts.get(current_day, 0)
                    fill = heatmap_color(count)
                    outline = "#FFFFFF"

                rect = canvas.create_rectangle(
                    x1,
                    y1,
                    x2,
                    y2,
                    fill=fill,
                    outline=outline,
                    width=1,
                )

                if current_day <= today:
                    rect_to_info[rect] = {
                        "date": current_day,
                        "count": counts.get(current_day, 0),
                    }

                    canvas.tag_bind(
                        rect,
                        "<Button-1>",
                        lambda event, d=current_day: show_day_detail(d),
                    )

                if current_day.day <= 7:
                    month_key = (current_day.year, current_day.month)
                    month_positions.setdefault(month_key, week)

            tooltip_bg = canvas.create_rectangle(
                0,
                0,
                0,
                0,
                fill="#24292f",
                outline="#24292f",
                state="hidden",
            )

            tooltip_text = canvas.create_text(
                0,
                0,
                text="",
                fill="#ffffff",
                font=("Segoe UI", 9),
                state="hidden",
            )

            def hide_heatmap_tooltip() -> None:
                canvas.itemconfig(tooltip_bg, state="hidden")
                canvas.itemconfig(tooltip_text, state="hidden")

            def show_heatmap_tooltip(event) -> None:
                overlap_items = canvas.find_overlapping(event.x, event.y, event.x, event.y)

                target = None
                for item in reversed(overlap_items):
                    if item in rect_to_info:
                        target = item
                        break

                if target is None:
                    hide_heatmap_tooltip()
                    return

                info = rect_to_info[target]
                day = info["date"]
                count = info["count"]

                record_word = "record" if count == 1 else "records"
                text = f"{day.isoformat()} · {count} {record_word}"

                x = event.x + 14
                y = event.y - 18

                canvas.itemconfig(tooltip_text, text=text, state="normal")
                canvas.coords(tooltip_text, x, y)

                bbox = canvas.bbox(tooltip_text)

                if bbox is None:
                    return

                pad_x = 7
                pad_y = 4

                x1, y1, x2, y2 = bbox

                if x2 + pad_x > canvas_width:
                    dx = (x2 + pad_x) - canvas_width + 8
                    x -= dx
                    canvas.coords(tooltip_text, x, y)
                    bbox = canvas.bbox(tooltip_text)
                    if bbox is None:
                        return
                    x1, y1, x2, y2 = bbox

                if y1 - pad_y < 0:
                    dy = (y1 - pad_y) - 0
                    y -= dy
                    canvas.coords(tooltip_text, x, y)
                    bbox = canvas.bbox(tooltip_text)
                    if bbox is None:
                        return
                    x1, y1, x2, y2 = bbox

                canvas.coords(
                    tooltip_bg,
                    x1 - pad_x,
                    y1 - pad_y,
                    x2 + pad_x,
                    y2 + pad_y,
                )

                canvas.itemconfig(tooltip_bg, state="normal")

                canvas.tag_raise(tooltip_bg)
                canvas.tag_raise(tooltip_text)

            canvas.bind("<Motion>", show_heatmap_tooltip)
            canvas.bind("<Leave>", lambda event: hide_heatmap_tooltip())

            for (year, month), week in month_positions.items():
                x = left_pad + week * (cell + gap)
                canvas.create_text(
                    x,
                    14,
                    text=month_names[month - 1],
                    fill=COLOR_MUTED,
                    font=("Segoe UI", 9),
                    anchor="w",
                )

            legend = ctk.CTkFrame(card, fg_color="transparent")
            legend.pack(fill="x", padx=26, pady=(0, 18))

            legend_text = ctk.CTkLabel(
                legend,
                text="点击某一天可以查看当天记录。颜色层级：0 条、1 条、2–3 条、4–6 条、7 条以上。",
                font=FONT_HINT,
                text_color=COLOR_MUTED,
                anchor="w",
            )
            legend_text.pack(side="left")

            open_daily_btn = ctk.CTkButton(
                legend,
                text="打开每日目录",
                font=FONT_BUTTON,
                height=38,
                corner_radius=12,
                fg_color="#FFFFFF",
                hover_color="#F0EFEC",
                text_color=COLOR_TEXT,
                border_width=1,
                border_color=COLOR_BORDER,
                command=self.open_daily_updates,
            )
            open_daily_btn.pack(side="right")

            show_day_detail(today)

        except Exception as exc:
            log_error(exc)
            messagebox.showerror(
                "热力图打开失败",
                f"打开热力图时出现错误：\n\n{exc}",
            )

    def open_daily_updates(self) -> None:
        try:
            ensure_dirs()
            rebuild_daily_updates()
            daily_file = BASE_DIR / "daily_updates.md"

            if sys.platform.startswith("win"):
                os.startfile(str(daily_file))
            else:
                messagebox.showinfo("每日目录路径", str(daily_file))

        except Exception as exc:
            log_error(exc)
            messagebox.showerror("打开失败", str(exc))


# ============================================================
# 启动逻辑
# ============================================================

def main() -> None:
    root = ctk.CTk()
    root.withdraw()

    app = MemoryCaptureApp(root)

    try:
        import keyboard

        keyboard.add_hotkey(
            HOTKEY_CAPTURE,
            lambda: root.after(0, app.show_capture_window),
        )

        keyboard.add_hotkey(
            HOTKEY_QUIT,
            lambda: root.after(0, root.quit),
        )

    except Exception as exc:
        log_error(exc)

        root.deiconify()
        root.title(APP_TITLE)
        root.geometry("560x280")
        root.configure(fg_color=COLOR_BG)
        root.attributes("-topmost", True)

        card = ctk.CTkFrame(
            root,
            fg_color=COLOR_CARD,
            corner_radius=22,
            border_width=1,
            border_color=COLOR_BORDER,
        )
        card.pack(fill="both", expand=True, padx=24, pady=24)

        title = ctk.CTkLabel(
            card,
            text="快捷键没有启用",
            font=FONT_TITLE,
            text_color=COLOR_TEXT,
            anchor="w",
        )
        title.pack(fill="x", padx=22, pady=(22, 4))

        msg = (
            "通常是因为没有安装 keyboard 包，或系统限制了全局键盘监听。\n\n"
            "你仍然可以点击下面的按钮记录。\n\n"
            "如需快捷键，请在 PowerShell 运行：pip install keyboard"
        )

        label = ctk.CTkLabel(
            card,
            text=msg,
            font=FONT_BODY,
            text_color=COLOR_MUTED,
            justify="left",
            anchor="w",
            wraplength=480,
        )
        label.pack(fill="x", padx=22, pady=(4, 18))

        btn = ctk.CTkButton(
            card,
            text="现在记录",
            font=FONT_BUTTON,
            height=42,
            corner_radius=12,
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            text_color="#FFFFFF",
            command=app.show_capture_window,
        )
        btn.pack(anchor="w", padx=22, pady=(0, 22))

    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log_error(exc)