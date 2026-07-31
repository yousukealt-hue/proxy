import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import requests
import io
import json
import os

# ============================
# 設定
# ============================
WIDTH = 300
HEIGHT = 400
FONT_PATH = "MPLUS1-Medium.ttf"
MARGIN = 12
HEADERS = {"User-Agent": "MomirProxy/1.0"}

DICT_PATH = "jp_en_map.json"
BULK_URL = "https://api.scryfall.com/bulk-data"
NAMED_URL = "https://api.scryfall.com/cards/named"


# ============================
# 日本語名 → 英語名辞書生成（初回のみ）
# ============================
def generate_jp_en_dict():
    st.write("[INFO] 辞書生成中…（初回のみ数分かかります）")

    r = requests.get(BULK_URL, headers=HEADERS)
    r.raise_for_status()
    bulk_list = r.json()["data"]

    all_cards_url = None
    for item in bulk_list:
        if item["type"] == "all_cards":
            all_cards_url = item["download_uri"]
            break

    r2 = requests.get(all_cards_url, headers=HEADERS)
    r2.raise_for_status()
    all_cards = r2.json()

    jp_en = {}
    for card in all_cards:
        printed_name = card.get("printed_name")
        name = card.get("name")
        if printed_name and name:
            jp_en[printed_name] = name

    with open(DICT_PATH, "w", encoding="utf-8") as f:
        json.dump(jp_en, f, ensure_ascii=False, indent=2)

    return jp_en


# ============================
# 辞書ロード
# ============================
def load_jp_en_dict():
    if os.path.exists(DICT_PATH):
        with open(DICT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return generate_jp_en_dict()


# ============================
# 英語名処理関数
# ============================
def fuzzy_search_english_name(name):
    url = "https://api.scryfall.com/cards/search"
    r = requests.get(url, params={"q": name}, headers=HEADERS)

    if r.status_code != 200:
        raise RuntimeError(f"英語名 '{name}' で検索できませんでした")

    data = r.json().get("data", [])
    if not data:
        raise RuntimeError(f"英語名 '{name}' の候補が見つかりません")

    # 最初の候補を採用
    return data[0]["name"]

# ============================
# 日本語名 → 英語名（部分一致対応）
# ============================
def resolve_english_name(jp_or_en_name, jp_en_dict):
    # ① 日本語名の完全一致
    if jp_or_en_name in jp_en_dict:
        return jp_en_dict[jp_or_en_name]

    # ② 日本語名の部分一致
    candidates = [jp for jp in jp_en_dict.keys() if jp_or_en_name in jp]
    if candidates:
        best = sorted(candidates, key=len)[0]
        return jp_en_dict[best]

    # ③ 辞書に無い → 英語名として扱う（曖昧検索）
    return fuzzy_search_english_name(jp_or_en_name)


# ============================
# カード情報取得（日本語版優先）
# ============================
def fetch_card(en_name):
    # まず英語版を取得（確実にヒットする）
    r = requests.get(NAMED_URL, params={"exact": en_name, "lang": "en"}, headers=HEADERS)
    r.raise_for_status()
    base = r.json()

    # set と collector_number を使って日本語版を探す
    set_code = base["set"]
    cn = base["collector_number"]

    url_ja = f"https://api.scryfall.com/cards/{set_code}/{cn}/ja"
    r2 = requests.get(url_ja, headers=HEADERS)

    if r2.status_code == 200:
        return r2.json()   # ★日本語版があれば絶対にこちらを返す

    return base            # ★日本語版が無ければ英語版



# ============================
# モミールの描画関数群（あなたのコードそのまま）
# ============================

def draw_card_name_and_cost(draw, y, name, mana_cost, max_height=36):
    start_y = y
    size = 32
    MIN_SIZE = 12

    while True:
        font_name = ImageFont.truetype(FONT_PATH, size)
        font_cost = ImageFont.truetype(FONT_PATH, max(size - 6, 10))

        name_ok = draw.textlength(name, font=font_name) <= (WIDTH - MARGIN*2)

        if mana_cost:
            bbox = draw.textbbox((0, 0), mana_cost, font=font_cost)
            cost_width = bbox[2] - bbox[0]
            cost_ok = cost_width <= (WIDTH - MARGIN*2)
        else:
            cost_ok = True

        total_height = font_name.size + 2 + font_name.size + 2
        height_ok = total_height <= max_height

        if name_ok and cost_ok and height_ok:
            break

        size -= 2
        if size < MIN_SIZE:
            size = MIN_SIZE
            font_name = ImageFont.truetype(FONT_PATH, size)
            font_cost = ImageFont.truetype(FONT_PATH, max(size - 6, 10))
            break

    draw.text((MARGIN, y), name, font=font_name, fill=0)
    y += font_name.size + 2

    if mana_cost:
        bbox = draw.textbbox((0, 0), mana_cost, font=font_cost)
        w_cost = bbox[2] - bbox[0]
        draw.text((WIDTH - MARGIN - w_cost, y), mana_cost, font=font_cost, fill=0)

    y += font_name.size + 4

    if y - start_y > max_height:
        y = start_y + max_height

    return y


def draw_type_line(draw, x, y, type_line, max_width=300 - 24, max_height=20):
    size = 14
    MIN_SIZE = 10

    while True:
        font_type = ImageFont.truetype(FONT_PATH, size)
        if draw.textlength(type_line, font=font_type) <= max_width:
            break
        size -= 2
        if size < MIN_SIZE:
            size = MIN_SIZE
            font_type = ImageFont.truetype(FONT_PATH, size)
            break

    draw.text((x, y), type_line, font=font_type, fill=0)
    return y + font_type.size + 6


def wrap_by_pixel(draw, text, font, max_width):
    lines = []
    for paragraph in text.split("\n"):
        current = ""
        for char in paragraph:
            test = current + char
            if draw.textlength(test, font=font) <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = char
        if current:
            lines.append(current)
    return lines


def draw_text_block(draw, x, y, text, font, max_width, max_height, line_spacing=1):
    size = font.size
    MIN_SIZE = 10

    while size >= MIN_SIZE:
        test_font = ImageFont.truetype(FONT_PATH, size)
        lines = wrap_by_pixel(draw, text, test_font, max_width)

        total_height = len(lines) * (test_font.size + line_spacing)
        too_wide = any(draw.textlength(line, font=test_font) > max_width for line in lines)

        if not too_wide and total_height <= max_height:
            break

        size -= 1

    test_font = ImageFont.truetype(FONT_PATH, size)
    lines = wrap_by_pixel(draw, text, test_font, max_width)

    for line in lines:
        draw.text((x, y), line, font=test_font, fill=0)
        y += test_font.size + line_spacing

    return y


def crop_art_from_card(image):
    w, h = image.size
    top = int(h * 0.12) + 10
    bottom = int(h * 0.52) + 10
    return image.crop((0, top, w, bottom))


def to_monochrome(img):
    return img.convert("L").convert("1")


# ============================
# プロキシカード生成
# ============================
def generate_proxy_card(jp_name):
    jp_en_dict = load_jp_en_dict()
    en_name = resolve_english_name(jp_name, jp_en_dict)
    card = fetch_card(en_name)

    name = card.get("printed_name") or card.get("name")
    type_line = card.get("printed_type_line") or card.get("type_line")
    oracle = card.get("printed_text") or card.get("oracle_text") or ""
    p = card.get("power", "?")
    t = card.get("toughness", "?")
    rarity = card.get("rarity", "")
    set_code = card.get("set", "").upper()

    img_url = card["image_uris"]["normal"]
    img_data = requests.get(img_url, headers=HEADERS).content
    card_img = Image.open(io.BytesIO(img_data))

    art = crop_art_from_card(card_img)
    w, h = art.size
    scale = WIDTH / w
    art = art.resize((WIDTH, int(h * scale)), Image.LANCZOS)
    art = to_monochrome(art)

    base = Image.new("1", (WIDTH, HEIGHT), 1)
    base.paste(art, (0, 0))

    draw = ImageDraw.Draw(base)
    y = art.height + 2

    mana_cost = card.get("mana_cost", "")
    y = draw_card_name_and_cost(draw, y, name, mana_cost)

    y = draw_type_line(draw, MARGIN, y, type_line)

    font_pt = ImageFont.truetype(FONT_PATH, 18)
    pt_text = f"{p}/{t}"
    bbox = draw.textbbox((0, 0), pt_text, font=font_pt)
    h_pt = bbox[3] - bbox[1]

    pt_reserved = 20 + h_pt
    remaining_height = HEIGHT - y - pt_reserved
    if remaining_height < 20:
        remaining_height = 20

    font_rules = ImageFont.truetype(FONT_PATH, 14)
    y = draw_text_block(
        draw,
        MARGIN,
        y,
        oracle,
        font_rules,
        max_width=WIDTH - MARGIN*2,
        max_height=remaining_height
    )

    info_text = f"{set_code} • {rarity}"
    font_info = ImageFont.truetype(FONT_PATH, 14)
    draw.text((MARGIN, HEIGHT - 10 - h_pt), info_text, font=font_info, fill=0)

    bbox = draw.textbbox((0, 0), pt_text, font=font_pt)
    w_pt = bbox[2] - bbox[0]
    pt_y = HEIGHT - 10 - h_pt
    draw.text((WIDTH - MARGIN - w_pt, pt_y), pt_text, font=font_pt, fill=0)

    return base


# ============================
# Streamlit UI
# ============================
st.title("Momir Proxy Printer")
st.write("日本語カード名を入力してプロキシを生成しよう")

if "history" not in st.session_state:
    st.session_state.history = []

if "last_image" not in st.session_state:
    st.session_state.last_image = None

jp_name = st.text_input("カード名（日本語）")

if st.button("プロキシ生成", use_container_width=True):
    try:
        img = generate_proxy_card(jp_name)
        st.session_state.last_image = img

        st.session_state.history.append(img)
        st.session_state.history = st.session_state.history[-5:]
    except Exception as e:
        st.error(str(e))

if st.session_state.last_image is not None:
    st.image(st.session_state.last_image, caption="生成されたプロキシ", width=300)

if st.session_state.history:
    st.write("### 生成履歴（最新5枚）")
    cols = st.columns(len(st.session_state.history))
    for col, hist_img in zip(cols, st.session_state.history):
        with col:
            st.image(hist_img, width=300)
