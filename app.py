"""
Electrical Shop Inventory & Billing System
-------------------------------------------
A Streamlit + SQLite app for retail electrical stores.
Runs smoothly on mobile browsers.

Required folders (created automatically):
  - product_images/   : store reference product images here
"""

import streamlit as st

st.markdown(
    """
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
    iframe {
        allow: camera;
    }
</style>
""",
    unsafe_allow_html=True,
)

import os
import io
import base64
import sqlite3
import tempfile
from datetime import datetime

import pandas as pd
from PIL import Image

st.markdown("""
<style>
iframe[title*="camera"] video {
    transform: scaleX(-1) !important;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------
DB_PATH = "shop.db"
IMAGE_DIR = "product_images"
os.makedirs(IMAGE_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# DATABASE HELPERS
# ---------------------------------------------------------------------------
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name      TEXT    NOT NULL,
            category       TEXT    NOT NULL DEFAULT 'General',
            price          REAL    NOT NULL,
            stock_quantity INTEGER NOT NULL DEFAULT 0,
            image_path     TEXT
        )
        """
    )
    try:
        conn.execute("ALTER TABLE inventory ADD COLUMN image_data TEXT")
    except:
        pass
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS history (
            bill_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT    NOT NULL,
            items       TEXT    NOT NULL,
            total       REAL    NOT NULL,
            status      TEXT    NOT NULL DEFAULT 'Paid'
        )
        """
    )
    conn.commit()
    conn.close()


def update_product_price_stock(pid, price, stock):
    conn = get_connection()
    conn.execute(
        "UPDATE inventory SET price=?, stock_quantity=? WHERE id=?",
        (price, stock, pid),
    )
    conn.commit()
    conn.close()


def add_product(name, category, price, stock, image_path, image_data=None):
    try:
        conn = get_connection()
        conn.execute(
            "INSERT INTO inventory (item_name, category, price, stock_quantity, image_path, image_data) VALUES (?, ?, ?, ?, ?, ?)",
            (name, category, price, stock, image_path, image_data),
        )
        conn.commit()
        conn.close()
        return True, None
    except Exception as e:
        return False, str(e)


def update_stock(item_id, quantity_sold):
    conn = get_connection()
    conn.execute(
        "UPDATE inventory SET stock_quantity = stock_quantity - ? WHERE id = ? AND stock_quantity >= ?",
        (quantity_sold, item_id, quantity_sold),
    )
    conn.commit()
    conn.close()


def get_all_existing_categories():
    conn = get_connection()
    rows = conn.execute("SELECT DISTINCT category FROM inventory WHERE category IS NOT NULL AND category != '' ORDER BY category").fetchall()
    conn.close()
    return [r["category"] for r in rows]


def get_all_products():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM inventory ORDER BY item_name").fetchall()
    conn.close()
    return rows


def get_product_by_id(product_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM inventory WHERE id = ?", (product_id,)).fetchone()
    conn.close()
    return row


def get_product_by_name(name):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM inventory WHERE LOWER(item_name) = LOWER(?)", (name,)
    ).fetchone()
    conn.close()
    return row


def save_transaction(items_str, total):
    conn = get_connection()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO history (timestamp, items, total, status) VALUES (?, ?, ?, 'Paid')",
        (ts, items_str, round(total, 2)),
    )
    conn.commit()
    conn.close()


def get_transaction_history():
    conn = get_connection()
    rows = conn.execute(
        "SELECT bill_id, timestamp, items, total, status FROM history ORDER BY bill_id DESC"
    ).fetchall()
    conn.close()
    return rows


def clear_transaction_history():
    conn = get_connection()
    conn.execute("DELETE FROM history")
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# MULTI-METHOD MATCHING: OCR + Color + Shape
# ---------------------------------------------------------------------------

import re
import cv2
import numpy as np
import pytesseract


def _img_to_array(image_bytes):
    """Convert image bytes to RGB numpy array."""
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return None
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def _crop_scan_box(rgb):
    """Crop to the green dotted rectangle (15% inset, 70% wide, 55% tall)."""
    h, w = rgb.shape[:2]
    x1 = int(w * 0.15)
    y1 = int(h * 0.15)
    x2 = int(w * 0.85)
    y2 = int(h * 0.70)
    return rgb[y1:y2, x1:x2]


def _load_ref(path):
    """Load a product reference image as RGB array."""
    img = cv2.imread(path)
    if img is None:
        return None
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def _ocr_score(query_rgb, product_name, category=""):
    """Score 0-100 based on OCR text match with product name or category."""
    # Preprocess for better OCR
    gray = cv2.cvtColor(query_rgb, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    _, thresh = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    text = pytesseract.image_to_string(thresh, config="--psm 6").lower().strip()
    if not text:
        return 0
    text_words = set(re.sub(r"[^a-z0-9\s]", "", text).split())
    if not text_words:
        return 0

    targets = [product_name.lower(), category.lower()]
    for target in targets:
        target_words = set(re.sub(r"[^a-z0-9\s]", "", target).split())
        if not target_words:
            continue
        matches = target_words & text_words
        if matches:
            return min(len(matches) / max(len(target_words), 1) * 100, 100)
    return 0


def _color_score(query_rgb, ref_rgb):
    """Score 0-100 based on HSV histogram correlation."""
    q_hsv = cv2.cvtColor(query_rgb, cv2.COLOR_RGB2HSV)
    r_hsv = cv2.cvtColor(ref_rgb, cv2.COLOR_RGB2HSV)
    q_hist = cv2.calcHist([q_hsv], [0, 1], None, [8, 8], [0, 180, 0, 256])
    r_hist = cv2.calcHist([r_hsv], [0, 1], None, [8, 8], [0, 180, 0, 256])
    cv2.normalize(q_hist, q_hist)
    cv2.normalize(r_hist, r_hist)
    return max(0, cv2.compareHist(q_hist, r_hist, cv2.HISTCMP_CORREL) * 100)


def _shape_score(query_rgb, ref_rgb):
    """Score 0-100 based on aspect ratio and Hu-moment similarity."""
    q_gray = cv2.cvtColor(query_rgb, cv2.COLOR_RGB2GRAY)
    r_gray = cv2.cvtColor(ref_rgb, cv2.COLOR_RGB2GRAY)
    q_edges = cv2.Canny(q_gray, 50, 150)
    r_edges = cv2.Canny(r_gray, 50, 150)
    q_conts, _ = cv2.findContours(q_edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    r_conts, _ = cv2.findContours(r_edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not q_conts or not r_conts:
        return 0
    q_cnt = max(q_conts, key=cv2.contourArea)
    r_cnt = max(r_conts, key=cv2.contourArea)
    if cv2.contourArea(q_cnt) < 100 or cv2.contourArea(r_cnt) < 100:
        return 0
    q_x, q_y, q_w, q_h = cv2.boundingRect(q_cnt)
    r_x, r_y, r_w, r_h = cv2.boundingRect(r_cnt)
    q_ar = q_w / max(q_h, 1)
    r_ar = r_w / max(r_h, 1)
    ar_score = 100 - min(abs(q_ar - r_ar) / max(max(q_ar, r_ar), 0.01) * 100, 100)
    q_hu = cv2.HuMoments(cv2.moments(q_cnt)).flatten()
    r_hu = cv2.HuMoments(cv2.moments(r_cnt)).flatten()
    q_log = np.log(np.abs(q_hu) + 1e-10)
    r_log = np.log(np.abs(r_hu) + 1e-10)
    hu_dist = sum(abs(a - b) for a, b in zip(q_log, r_log))
    hu_score = max(0, 100 - hu_dist * 10)
    return ar_score * 0.4 + hu_score * 0.6


def multi_method_match(image_bytes):
    """
    Match product using OCR + Color + Shape ensemble.
    Returns (product_row, status_message).
    """
    query_rgb = _img_to_array(image_bytes)
    if query_rgb is None:
        return None, "Could not read image."

    query_rgb = _crop_scan_box(query_rgb)
    h, w = query_rgb.shape[:2]
    if h < 20 or w < 20:
        return None, "No matching product found."

    products = get_all_products()
    if not products:
        return None, "No products in database."

    results = []
    for p in products:
        raw = (p["image_path"] or "").strip()
        if not raw:
            continue
        paths = [x.strip() for x in raw.split("|") if x.strip() and os.path.isfile(x.strip())]
        if not paths:
            continue
        ref_rgb = _load_ref(paths[0])
        if ref_rgb is None:
            continue
        ocr = _ocr_score(query_rgb, p["item_name"], p["category"]) * 0.35
        color = _color_score(query_rgb, ref_rgb) * 0.35
        shape = _shape_score(query_rgb, ref_rgb) * 0.30
        combined = round(ocr + color + shape, 1)
        results.append((combined, p))

    if not results:
        return None, "No matching product found."

    results.sort(key=lambda x: x[0], reverse=True)
    best_score, best_row = results[0]

    if best_score >= 25:
        return best_row, None

    return None, "No matching product found."


# ---------------------------------------------------------------------------
# CART HELPERS (st.session_state)
# ---------------------------------------------------------------------------
def init_cart():
    if "cart" not in st.session_state:
        st.session_state.cart = []  # list of {id, name, price, qty}
    if "current_scan" not in st.session_state:
        st.session_state.current_scan = None  # matched product row (sqlite3.Row)
    if "scan_key" not in st.session_state:
        st.session_state.scan_key = 0  # incremented to reset camera widget
    if "captured_images" not in st.session_state:
        st.session_state.captured_images = []
    if "capture_step" not in st.session_state:
        st.session_state.capture_step = 0  # 0=idle, 1-4=capturing
    if "camera_active" not in st.session_state:
        st.session_state.camera_active = False
    if "preview_capture" not in st.session_state:
        st.session_state.preview_capture = None
    if "search_key_counter" not in st.session_state:
        st.session_state.search_key_counter = 0
    if "selected_category" not in st.session_state:
        st.session_state.selected_category = "Electrical"
    if "confirm_delete_all" not in st.session_state:
        st.session_state.confirm_delete_all = False



def cart_add(product, qty):
    cart = st.session_state.cart
    for item in cart:
        if item["id"] == product["id"]:
            item["qty"] += qty
            return
    cart.append(
        {"id": product["id"], "name": product["item_name"], "price": product["price"], "qty": qty}
    )


def cart_remove(index):
    if 0 <= index < len(st.session_state.cart):
        st.session_state.cart.pop(index)


def cart_clear():
    st.session_state.cart = []


def cart_total():
    return sum(item["price"] * item["qty"] for item in st.session_state.cart)


# ---------------------------------------------------------------------------
# STREAMLIT UI
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="ShopScan - Electrical Store",
    page_icon="\U0001f50c",
    layout="centered",
)

st.markdown(
    """
<script>
// Override getUserMedia to force back camera
const _getUserMedia = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
navigator.mediaDevices.getUserMedia = function(constraints) {
    if (constraints && constraints.video !== false) {
        constraints = {
            ...constraints,
            video: {
                facingMode: { ideal: "environment" },
                width: { ideal: 1280 },
                height: { ideal: 720 }
            }
        };
    }
    return _getUserMedia(constraints);
};
</script>
""",
    unsafe_allow_html=True,
)

init_db()
init_cart()

st.title("\U0001f50c ShopScan")

# ── SIDEBAR ───────────────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("\U0001f4e5 Backup & Export")
    if st.button("\U0001f4e5 Export Database to CSV", use_container_width=True):
        df = pd.read_sql_query(
            "SELECT id, item_name, category, price, stock_quantity, image_path "
            "FROM inventory ORDER BY item_name",
            sqlite3.connect(DB_PATH),
        )
        csv = df.to_csv(index=False)
        st.download_button(
            "\U0001f4e5 Download inventory_backup.csv",
            data=csv,
            file_name="inventory_backup.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.markdown("---")
    st.subheader("\U0001f4c2 Import Data")
    uploaded_file = st.file_uploader(
        "\U0001f4c3 Import Inventory from CSV", type=["csv"]
    )
    if st.button("\U0001f504 Restore Inventory", use_container_width=True):
        if uploaded_file is None:
            st.warning("Please upload a CSV file first.")
        else:
            try:
                df = pd.read_csv(uploaded_file)
                required = {
                    "id", "item_name", "category", "price",
                    "stock_quantity", "image_path"
                }
                if not required.issubset(df.columns):
                    st.error(
                        "CSV must contain columns: "
                        "id, item_name, category, price, stock_quantity, image_path"
                    )
                else:
                    pd.options.mode.chained_assignment = None
                    # Fill any missing IDs with sequential numbers
                    df["id"] = df["id"].fillna(0).astype(int)
                    df.loc[df["id"] == 0, "id"] = range(
                        1, (df["id"] == 0).sum() + 1
                    )
                    conn = sqlite3.connect(DB_PATH)
                    df.to_sql("inventory", conn, if_exists="replace", index=False)
                    conn.close()
                    st.success("Inventory restored successfully!")
                    st.rerun()
            except Exception as e:
                st.error(f"Import failed: {e}")

# ── TABS ──────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["\U0001f4f7 Scan & Sell", "\U0001f4b0 Current Bill", "\u2699\ufe0f Inventory Admin"])

# ======================================================================
# TAB 1 : SCAN & SELL
# ======================================================================
with tab1:
    # ── Visual framing overlay for the camera viewfinder ──────────────
    st.markdown(
        """
        <style>
        [data-testid="stCameraInput"] {
            position: relative !important;
        }
        [data-testid="stCameraInput"]::before {
            content: "" !important;
            position: absolute !important;
            top: 15% !important;
            left: 15% !important;
            width: 70% !important;
            height: 55% !important;
            border: 3px dashed #39FF14 !important;
            border-radius: 8px !important;
            box-shadow: 0 0 10px rgba(57, 255, 20, 0.5) !important;
            pointer-events: none !important;
            z-index: 99 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("\U0001f4f7 Scan an item")

    st.caption(
        "\U0001f4a1 Tip: Center the item inside the dashed box for the best matching score."
    )

    # -- Camera input (dynamic key lets us force-reset the widget) --
    camera_key = f"cam_{st.session_state.scan_key}"
    st.markdown("""
<style>
.mobile-camera-hint { display: none; }
@media (max-width: 768px) { .mobile-camera-hint { display: block; } }
</style>
<div class="mobile-camera-hint" style="padding:0.5rem;border-radius:8px;background:#e6f7ff;border:1px solid #91d5ff;font-size:14px;margin-bottom:8px;">
📱 On mobile: tap the 🔄 flip icon in the camera to switch to back camera
</div>
""", unsafe_allow_html=True)
    cam_img = st.camera_input("Take a photo of the item", key=camera_key)

    # -- File uploader fallback (also uses dynamic key so reset clears it) --
    upload_key = f"upload_{st.session_state.scan_key}"
    uploaded_file = st.file_uploader(
        "Or upload/snap a photo from device storage",
        type=["jpg", "jpeg", "png", "webp"],
        key=upload_key,
    )

    # Determine which source to use (camera takes priority)
    source_bytes = None
    if cam_img is not None:
        source_bytes = cam_img.getvalue()
    elif uploaded_file is not None:
        source_bytes = uploaded_file.getvalue()

    # Auto-analyze when a photo is taken or uploaded
    if source_bytes is not None:
        with st.spinner("Analyzing..."):
            row, status_msg = multi_method_match(source_bytes)

        if row is not None:
            st.session_state.current_scan = row
            st.session_state.manual_select = row["item_name"]
            st.success(f"\u2705 Product Matched: **{row['item_name']}**")
            st.session_state.scroll_to_result = True
        else:
            st.error(f"\u274c No matching product found")

    # -- Display scanned product & action buttons --
    st.markdown('<div id="result"></div>', unsafe_allow_html=True)
    scanned_product = st.session_state.current_scan

    if scanned_product is not None:
        if st.session_state.pop("scroll_to_result", False):
            st.markdown("""
<script>
setTimeout(() => document.getElementById('result')?.scrollIntoView({behavior: 'smooth'}), 100);
</script>
""", unsafe_allow_html=True)
        col1, col2 = st.columns([1, 2])
        with col1:
            if scanned_product["image_data"]:
                img_bytes = base64.b64decode(scanned_product["image_data"])
                st.image(Image.open(io.BytesIO(img_bytes)), width=140)
            else:
                img_path = scanned_product["image_path"]
                if img_path:
                    image_paths = img_path.split("|")
                    if image_paths and os.path.exists(image_paths[0]):
                        st.image(image_paths[0], width=140)
        with col2:
            st.markdown(
                f"**{scanned_product['item_name']}**  \n"
                f"Category: {scanned_product['category']}  |  "
                f"**\u20b9{scanned_product['price']:.2f}**  \n"
                f"Stock: {scanned_product['stock_quantity']} units"
            )

            if scanned_product["stock_quantity"] > 0:
                cart_qty = sum(
                    item["qty"] for item in st.session_state.cart
                    if item["id"] == scanned_product["id"]
                )

                if cart_qty >= scanned_product["stock_quantity"]:
                    st.warning(
                        f"Only {scanned_product['stock_quantity']} units available!"
                    )
                else:
                    max_qty = scanned_product["stock_quantity"] - cart_qty
                    col_a, col_b = st.columns([1, 1])
                    with col_a:
                        qty = st.number_input(
                            "Qty", min_value=1, max_value=max_qty, value=1,
                            key="add_qty"
                        )
                    with col_b:
                        if st.button("\U0001f6d2 Add to Bill", key="add_bill_scan", use_container_width=True):
                            cart_add(scanned_product, qty)
                            st.success(
                                f"Added {qty} x {scanned_product['item_name']} to cart"
                            )
                            st.session_state.current_scan = None
                            st.session_state.scan_key += 1
                            st.session_state.search_key_counter += 1
                            st.rerun()
            else:
                st.error("OUT OF STOCK")

        # Independent reset button
        if st.button("\U0001f504 Reset Scanner", key="reset_scan", use_container_width=True):
            st.session_state.current_scan = None
            st.session_state.scan_key += 1
            st.rerun()

        st.markdown("---")

    else:
        st.info("Point your camera at an item or select one from the dropdown above.")

    # -- Manual fallback search (always visible below product card) --
    all_prods = get_all_products()
    if all_prods:
        search_query = st.text_input(
            "\U0001f50d Search item...",
            key=f"item_search_{st.session_state.search_key_counter}",
        )
        if search_query:
            matches = [
                p for p in all_prods
                if search_query.lower() in p["item_name"].lower()
            ][:5]
            for match in matches:
                if st.button(
                    f"{match['item_name']} \u2014 \u20b9{match['price']:.2f}",
                    key=f"match_{match['id']}",
                ):
                    st.session_state.current_scan = match
                    st.session_state.scroll_to_result = True
                    st.rerun()

        if st.button("\U0001f504 Reset Scanner", key="reset_search", use_container_width=True):
            st.session_state.current_scan = None
            st.session_state.scan_key += 1
            st.rerun()
    else:
        st.info("No products in inventory yet. Go to the Admin tab to add some.")

# ======================================================================
# TAB 2 : CURRENT BILL & CHECKOUT
# ======================================================================
with tab2:
    st.subheader("\U0001f9fe Current Bill")

    if not st.session_state["cart"]:
        st.info("Cart is empty. Scan or search items to add.")
    else:
        for i, item in enumerate(st.session_state["cart"]):
            st.markdown(f"""
        <div style="background:white; border-radius:12px; padding:14px; margin-bottom:10px; border:1px solid #eee; box-shadow:0 1px 3px rgba(0,0,0,0.08);">
            <div style="display:flex; justify-content:space-between;">
                <b style="font-size:15px;">{item['name']}</b>
                <b style="color:#e74c3c;">\u20b9{item['price'] * item['qty']:.2f}</b>
            </div>
            <div style="color:#888; font-size:13px; margin-top:2px;">
                \u20b9{item['price']:.2f} per unit
            </div>
        </div>
        """, unsafe_allow_html=True)
            col1, col2 = st.columns([3, 1])
            with col1:
                new_qty = st.number_input(
                    "Qty", min_value=1, value=item["qty"],
                    key=f"bill_qty_{i}", label_visibility="visible",
                )
            with col2:
                st.write("")
                st.write("")
                if st.button("\U0001f5d1", key=f"bill_del_{i}", use_container_width=True):
                    st.session_state["cart"].pop(i)
                    st.rerun()
            if new_qty != item["qty"]:
                st.session_state["cart"][i]["qty"] = new_qty
                st.rerun()
            st.divider()

        total = sum(item["price"] * item["qty"] for item in st.session_state["cart"])

        st.markdown(f"""
        <div style="background:#fff5f5; border-radius:12px; padding:16px; margin:10px 0; border:2px solid #e74c3c;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-size:18px; font-weight:600;">Total</span>
                <span style="font-size:24px; font-weight:700; color:#e74c3c;">\u20b9{total:.2f}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("\u2705 Confirm Purchase & Print Bill", type="primary", use_container_width=True, key="confirm_bill"):
            errors = []
            for item in st.session_state.cart:
                prod = get_product_by_id(item["id"])
                if prod and prod["stock_quantity"] >= item["qty"]:
                    update_stock(item["id"], item["qty"])
                else:
                    errors.append(f"{item['name']} (only {prod['stock_quantity']} in stock)" if prod else f"{item['name']} not found")
            if errors:
                st.error("Could not fulfil:\n" + "\n".join(errors))
            else:
                item_parts = [f"{i['name']} x{i['qty']}" for i in st.session_state.cart]
                items_str = ", ".join(item_parts)
                grand_total = sum(item["price"] * item["qty"] for item in st.session_state.cart)
                save_transaction(items_str, grand_total)
                now = datetime.now().strftime("%d-%b-%Y %I:%M %p")
                st.markdown("---")
                st.markdown(
                    f"""
                    <div style="border:2px dashed #4CAF50; padding:1rem; border-radius:8px; background:#f9fff9;">
                    <h3 style="text-align:center;">\U0001f4b3 ShopScan Receipt</h3>
                    <p style="text-align:center; font-size:0.9rem;">{now}</p>
                    <hr>
                    <table style="width:100%; font-size:1rem;">
                    <tr><th>Item</th><th>Qty</th><th style="text-align:right;">Amount</th></tr>
                    """
                    + "".join(
                        f"<tr><td>{i['name']}</td><td>{i['qty']}</td><td style='text-align:right;'>\u20b9{i['price']*i['qty']:.2f}</td></tr>"
                        for i in st.session_state.cart
                    )
                    + f"""
                    </table>
                    <hr>
                    <h4 style="text-align:right;">Total: \u20b9{grand_total:.2f}</h4>
                    <p style="text-align:center; font-size:0.8rem; color:gray;">Thank you for your purchase!</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.session_state["cart"] = []
                st.rerun()

        if st.button("\U0001f5d1 Clear Cart", use_container_width=True, key="clear_cart"):
            st.session_state["cart"] = []
            st.rerun()

    # ── Sales & Bill History ────────────────────────────────────────────
    st.markdown("---")
    st.subheader("\U0001f4ca Sales & Bill History")
    history_rows = get_transaction_history()

    if not history_rows:
        st.info("No transactions yet.")
    else:
        hist_data = [
            {
                "Bill ID": r["bill_id"],
                "Timestamp": r["timestamp"],
                "Items Bought": r["items"],
                "Total Amount": f"\u20b9{r['total']:.2f}",
                "Status": r["status"],
            }
            for r in history_rows
        ]
        df = pd.DataFrame(hist_data)
        df = df.sort_values("Bill ID", ascending=True).reset_index(drop=True)
        df.insert(0, "S.No", range(1, len(df) + 1))
        df["Date"] = pd.to_datetime(df["Timestamp"]).dt.strftime("%Y-%m-%d")
        df["Time"] = pd.to_datetime(df["Timestamp"]).dt.strftime("%H:%M:%S")
        df = df.drop(columns=["Timestamp"])
        df["Item Name"] = df["Items Bought"].str.rsplit(" x", n=1).str[0]
        df["Quantity"] = df["Items Bought"].str.rsplit(" x", n=1).str[1]
        df = df.drop(columns=["Items Bought"])
        st.dataframe(
            df[["S.No", "Bill ID", "Date", "Time", "Item Name", "Quantity", "Total Amount", "Status"]],
            width="stretch",
            hide_index=True,
        )

        col_exp, col_clr = st.columns([1, 1])
        with col_exp:
            # Build CSV export
            csv_lines = ["S.No,Bill ID,Date,Time,Item Name,Quantity,Total Amount,Status"]
            sno = 1
            for r in sorted(history_rows, key=lambda x: x["bill_id"]):
                parts = r["items"].rsplit(" x", 1)
                item_name = parts[0]
                qty = parts[1] if len(parts) > 1 else ""
                ts = r["timestamp"]
                date_part = ts[:10] if len(ts) >= 10 else ts
                time_part = ts[11:19] if len(ts) >= 19 else ""
                csv_lines.append(
                    f'{sno},{r["bill_id"]},{date_part},{time_part},"{item_name}",{qty},\u20b9{r["total"]:.2f},{r["status"]}'
                )
                sno += 1
            csv_str = "\n".join(csv_lines)
            st.download_button(
                "\U0001f4e4 Export CSV",
                data=csv_str,
                file_name="sales_history.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with col_clr:
            if st.button("\U0001f5d1 Clear History", use_container_width=True):
                clear_transaction_history()
                st.rerun()

# ======================================================================
# TAB 3 : INVENTORY ADMIN PANEL
# ======================================================================
with tab3:
    # ── Add New Product ───────────────────────────────────────────────
    st.subheader("\u2795 Add New Product")

    if st.session_state.get("product_saved"):
        st.success("Product added to inventory successfully!")
        st.session_state.product_saved = False

    # ── Image Capture ─────────────────────────────────────────────────
    camera_on = st.session_state.get("camera_active", False)
    uploaded_files = []

    if camera_on:
        step = st.session_state.capture_step
        st.write(f"**Photos taken: {step} / 4**")
        img = st.camera_input(" ", key=f"cap_cam_{step}", label_visibility="collapsed")
        if img:
            if len(st.session_state.captured_images) < 4:
                st.session_state.captured_images.append(img)
                st.session_state.capture_step = len(st.session_state.captured_images)
                if len(st.session_state.captured_images) >= 4:
                    st.session_state.camera_active = False
            st.rerun()
        if st.button("Skip", use_container_width=True):
            st.session_state.camera_active = False
            st.session_state.capture_step = 0
            st.rerun()
    else:
        qp = st.query_params
        if "cap_preview" in qp:
            try:
                st.session_state.preview_capture = int(qp["cap_preview"])
            except ValueError:
                pass
            st.query_params.clear()
            st.rerun()

        col_cam, col_up = st.columns(2)
        with col_cam:
            if len(st.session_state.captured_images) < 4:
                st.button("\U0001f4f7 Capture", use_container_width=True,
                          on_click=lambda: setattr(st.session_state, "camera_active", True))
            captured = st.session_state.captured_images
            if captured:
                st.markdown("**Capture Images (max 4)**")
                for idx, cap in enumerate(captured):
                    size_kb = len(cap.getvalue()) / 1024
                    c1, c2 = st.columns([1, 0.12])
                    with c1:
                        st.markdown(f"""
<div style="display:flex;align-items:center;background:white;border:1px solid #e8e8e8;border-radius:10px;padding:8px 12px;box-shadow:0 1px 3px rgba(0,0,0,0.06);">
    <div style="width:36px;height:36px;background:#f0f0f0;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:18px;margin-right:10px;">🖼\ufe0f</div>
    <div style="flex:1;font-size:13px;color:#333;cursor:pointer;" onclick="window.history.replaceState({{}},'','?cap_preview={idx}')">capture_{idx+1}.jpg</div>
    <div style="font-size:12px;color:#999;">{size_kb:.1f} KB</div>
</div>
""", unsafe_allow_html=True)
                    with c2:
                        if st.button("\u2716", key=f"del_cap_{idx}"):
                            st.session_state.captured_images.pop(idx)
                            st.session_state.capture_step = len(st.session_state.captured_images)
                            st.session_state.preview_capture = None
                            st.rerun()
                prev = st.session_state.get("preview_capture", None)
                if prev is not None and 0 <= prev < len(captured):
                    st.image(captured[prev], use_container_width=True)
                    if st.button("\u2190 Close Preview", key="close_preview",
                                 use_container_width=True):
                        st.session_state.preview_capture = None
                        st.rerun()
        with col_up:
            cap_count = len(st.session_state.captured_images)
            remain = 4 - cap_count
            if remain > 0:
                uploaded_files = st.file_uploader(
                    "Upload Images (max 4)",
                    type=["jpg", "jpeg", "png", "webp"],
                    accept_multiple_files=True,
                    key="admin_file",
                )
                if uploaded_files:
                    if len(uploaded_files) > remain:
                        uploaded_files = uploaded_files[:remain]
                        st.warning(f"Total images cannot exceed 4. Only {remain} upload slot(s) free.")
            else:
                uploaded_files = []
                st.info("Max images reached. Remove a captured photo to upload.")

    # ── Category selector (outside form for live updates) ─────
    all_categories = get_all_existing_categories()
    selected_cat = st.selectbox(
        "Existing Categories",
        [""] + all_categories,
        key="cat_selector",
    )
    if selected_cat:
        st.session_state.current_category = selected_cat

    # ── Product Details Form ──────────────────────────────────────────
    with st.form("add_product_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            new_name = st.text_input("Item Name *")
            new_category = st.text_input(
                "Category",
                value=st.session_state.get("current_category", ""),
                placeholder="Enter category name...",
            )
        with col2:
            new_price = st.text_input("Price (\u20b9) *", placeholder="e.g. 149.50")
            new_stock = st.text_input("Initial Stock *", placeholder="e.g. 10")

        submitted = st.form_submit_button(
            "\U0001f4c0 Save Product", type="primary", use_container_width=True
        )

    # ── Submission Logic ──────────────────────────────────────────────
    if submitted:
        if not new_name.strip():
            st.error("Item name is required.")
        elif not new_price.strip():
            st.error("Price is required.")
        else:
            try:
                price_val = float(new_price.strip())
            except ValueError:
                st.error("Price must be a valid number.")
                price_val = 0.0

            try:
                stock_val = int(new_stock.strip()) if new_stock.strip() else 0
            except ValueError:
                st.error("Stock must be a valid whole number.")
                stock_val = 0

            if price_val <= 0:
                st.error("Price must be greater than zero.")
            else:
                # Collect images (captured + uploaded)
                final_paths = []
                safe_name = new_name.strip().replace(" ", "_").lower()
                for idx, cap in enumerate(st.session_state.captured_images, start=1):
                    filename = f"{safe_name}_captured_{idx}_{datetime.now().strftime('%H%M%S')}.jpg"
                    full_path = os.path.join(IMAGE_DIR, filename)
                    with open(full_path, "wb") as f:
                        f.write(cap.getvalue())
                    final_paths.append(full_path)

                if uploaded_files:
                    if len(uploaded_files) > 4:
                        st.warning(
                            "\u26a0\ufe0f You can upload a maximum of 4 reference photos. "
                            "Only the first 4 will be saved."
                        )
                        uploaded_files = uploaded_files[:4]
                    safe_name = new_name.strip().replace(" ", "_").lower()
                    for idx, uf in enumerate(uploaded_files, start=1):
                        ext = os.path.splitext(uf.name)[1] or ".jpg"
                        filename = f"{safe_name}_upload_{idx}{ext}"
                        full_path = os.path.join(IMAGE_DIR, filename)
                        if os.path.exists(full_path):
                            base, ext = os.path.splitext(full_path)
                            full_path = f"{base}_{idx}_{datetime.now().strftime('%H%M%S')}{ext}"
                        try:
                            with open(full_path, "wb") as f:
                                f.write(uf.getvalue())
                            final_paths.append(full_path)
                        except Exception as e:
                            st.error(f"Failed to save upload #{idx}: {e}")

                # Build pipe-delimited path string for the DB
                img_path_str = "|".join(final_paths) if final_paths else None

                # Convert first image to base64 for mobile display
                img_data_b64 = None
                if final_paths:
                    try:
                        with open(final_paths[0], "rb") as f:
                            img_data_b64 = base64.b64encode(f.read()).decode("utf-8")
                    except:
                        pass

                ok, err = add_product(
                    new_name.strip(), new_category.strip(),
                    price_val, stock_val, img_path_str, img_data_b64,
                )
                if ok:
                    st.session_state.captured_images = []
                    st.session_state.capture_step = 0
                    st.session_state.camera_active = False
                    st.session_state.current_category = new_category.strip()
                    st.session_state.product_saved = True
                    st.rerun()
                else:
                    st.error(f"Database error: {err}")

    st.markdown("---")


    # ── View Stock ────────────────────────────────────────────────────
    st.subheader("\U0001f4ca Current Stock")

    # ── Bulk Price Update ─────────────────────────────────────────────
    with st.expander("\U0001f4b5 Bulk Price Update", expanded=False):
        col_type, col_val, col_btn = st.columns([2, 2, 1])
        with col_type:
            change_type = st.selectbox(
                "Price Change Type",
                ["Increase by %", "Decrease by %", "Increase by \u20b9", "Decrease by \u20b9"],
                key="bulk_change_type",
            )
        with col_val:
            value = st.number_input("Value", min_value=0.0, value=10.0, step=1.0,
                                    key="bulk_change_value")
        with col_btn:
            st.write("")
            st.write("")
            if st.button("Apply to All Products", key="bulk_apply", use_container_width=True):
                try:
                    conn = get_connection()
                    rows = conn.execute("SELECT id, price FROM inventory").fetchall()
                    for r in rows:
                        pid, old_price = r[0], r[1]
                        new_price = float(old_price)
                        if change_type == "Increase by %":
                            new_price *= 1 + value / 100
                        elif change_type == "Decrease by %":
                            new_price *= 1 - value / 100
                        elif change_type == "Increase by \u20b9":
                            new_price += value
                        elif change_type == "Decrease by \u20b9":
                            new_price -= value
                        new_price = max(round(new_price, 2), 1.0)
                        conn.execute("UPDATE inventory SET price = ? WHERE id = ?", (new_price, pid))
                    conn.commit()
                    conn.close()
                    st.success("All prices updated successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to update prices: {e}")

    search = st.text_input("\U0001f50d Search product...", key="stock_search",
                           placeholder="Search by name, category...")
    with get_db() as conn:
        all_rows = conn.execute("SELECT * FROM inventory ORDER BY id ASC").fetchall()

    if not all_rows:
        st.info("No products yet. Add your first product!")
    else:
        df = pd.DataFrame(
            [
                {
                    "ID": r[0],
                    "Name": r[1],
                    "Category": r[2],
                    "Price": r[3],
                    "Stock": r[4],
                    "Image": f"data:image/jpeg;base64,{r[6]}" if r[6] else "",
                    "Delete?": False,
                }
                for r in all_rows
            ]
        )
        df["ID"] = df["ID"].fillna(0).astype(int)
        df.reset_index(drop=True, inplace=True)
        df.insert(0, "Serial No.", range(1, len(df) + 1))
        if search:
            df = df[
                df["Name"].str.contains(search, case=False, na=False)
                | df["Category"].str.contains(search, case=False, na=False)
            ]
            if df.empty:
                st.info("No products found matching your search.")

        column_config = {
            "Serial No.": st.column_config.NumberColumn(disabled=True),
            "ID": st.column_config.NumberColumn(disabled=True),
            "Name": st.column_config.TextColumn(required=True),
            "Category": st.column_config.TextColumn(),
            "Price": st.column_config.NumberColumn(format="₹%.2f", required=True),
            "Stock": st.column_config.NumberColumn(format="%d", required=True),
            "Image": st.column_config.ImageColumn(),
            "Delete?": st.column_config.CheckboxColumn("Delete?"),
        }

        edited_df = st.data_editor(
            df,
            key="stock_editor",
            num_rows="dynamic",
            column_config=column_config,
            hide_index=True,
            use_container_width=True,
        )

        col1, col2, col3 = st.columns([2, 2, 2])
        with col1:
            save_clicked = st.button("\U0001f4be Save All Changes", type="primary", use_container_width=True)
        with col2:
            delete_clicked = st.button("\u274c Delete Selected", use_container_width=True)
        with col3:
            delete_all_clicked = st.button("\U0001f5d1 Delete All", use_container_width=True)

        if save_clicked:
            try:
                conn = sqlite3.connect(DB_PATH)
                orig_ids = {r[0] for r in all_rows}
                current_ids = set(edited_df["ID"].dropna().astype(int))

                for removed_id in orig_ids - current_ids:
                    conn.execute("DELETE FROM inventory WHERE id = ?", (int(removed_id),))

                for _, row in edited_df.iterrows():
                    pid = row["ID"]
                    if pd.isna(pid) or pid == 0:
                        conn.execute(
                            "INSERT INTO inventory (item_name, category, price, stock_quantity, image_path) VALUES (?, ?, ?, ?, ?)",
                            (row["Name"], row["Category"], row["Price"], int(row["Stock"]), row["Image"] or None),
                        )
                    else:
                        conn.execute(
                            "UPDATE inventory SET item_name=?, category=?, price=?, stock_quantity=?, image_path=? WHERE id=?",
                            (row["Name"], row["Category"], row["Price"], int(row["Stock"]), row["Image"] or None, int(pid)),
                        )
                conn.commit()
                conn.close()
                st.success("Changes saved.")
                st.rerun()
            except Exception as e:
                st.error(f"Save failed: {e}")

        if delete_clicked:
            try:
                selected_rows = edited_df[edited_df["Delete?"] == True]
                st.write(selected_rows)
                valid_rows = selected_rows[selected_rows["ID"].notna()]
                valid_rows = valid_rows[valid_rows["ID"] != "None"]
                if valid_rows.empty:
                    st.warning("No valid IDs selected for deletion.")
                    st.stop()
                conn = sqlite3.connect(DB_PATH)
                for id_to_delete in valid_rows["ID"]:
                    conn.execute("DELETE FROM inventory WHERE id = ?", (int(id_to_delete),))
                    st.success(f"Deleted row with ID {id_to_delete}")
                conn.commit()
                conn.close()
                st.rerun()
            except Exception as e:
                st.error(f"Delete failed: {e}")

        if delete_all_clicked:
            if st.session_state.get("confirm_delete_all"):
                conn = sqlite3.connect(DB_PATH)
                conn.execute("DELETE FROM inventory")
                conn.execute("DELETE FROM sqlite_sequence WHERE name='inventory'")
                conn.commit()
                conn.close()
                st.success("All products deleted!")
                st.session_state["confirm_delete_all"] = False
                st.rerun()
            else:
                st.session_state["confirm_delete_all"] = True
                st.warning("Are you sure? Click again to confirm")

        # Low-stock warning
        low = [r[1] for r in all_rows if r[4] <= 5]
        low_running = [r[1] for r in all_rows if 5 < r[4] <= 20]
        if low:
            st.warning(f"\u26a0\ufe0f Low stock: {', '.join(low)}")
        if low_running:
            st.info(f"\U0001f550 Running low: {', '.join(low_running)}")
