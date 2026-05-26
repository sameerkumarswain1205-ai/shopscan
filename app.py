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
from PIL import Image, ImageFilter

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
# IMAGE MATCHING  (Scale-Invariant Multi-Feature Ensemble)
# ---------------------------------------------------------------------------
# Matching helpers ----------------------------------------------------------

def _decode_gray(image_bytes):
    return Image.open(io.BytesIO(image_bytes)).convert("L")


def _decode_color(image_bytes):
    return Image.open(io.BytesIO(image_bytes)).convert("RGB")


def _img_to_bytes(img):
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


# Foreground extraction -----------------------------------------------------

def extract_foreground(image_bytes, min_area_ratio=0.05, padding=0.20):
    img = _decode_color(image_bytes)
    if img is None:
        return None
    return _img_to_bytes(img)


# Feature computation -------------------------------------------------------

def _corr(a, b):
    n = len(a)
    if n == 0:
        return 0.0
    m1 = sum(a) / n
    m2 = sum(b) / n
    num = sum((x - m1) * (y - m2) for x, y in zip(a, b))
    d1 = sum((x - m1) ** 2 for x in a)
    d2 = sum((y - m2) ** 2 for y in b)
    if d1 == 0 or d2 == 0:
        return 0.0
    return num / (d1 ** 0.5 * d2 ** 0.5)


def compute_descriptor(gray_img):
    if gray_img is None:
        return None
    h = gray_img.histogram()
    total = sum(h)
    if total == 0:
        return None
    return [v / total for v in h]


def match_descriptors(d1, d2):
    if d1 is None or d2 is None or len(d1) == 0 or len(d2) == 0:
        return 0
    return int(_corr(d1, d2) * 100)


def compute_histogram(img):
    if img is None:
        return None
    hsv = img.convert("HSV")
    hist = hsv.histogram()
    total = sum(hist)
    if total == 0:
        return None
    return [v / total for v in hist]


def compare_histograms(hist1, hist2):
    if hist1 is None or hist2 is None:
        return 0.0
    return max(0.0, _corr(hist1, hist2))


def compute_edge_map(gray_img, target_size=(120, 120)):
    if gray_img is None:
        return None
    return gray_img.filter(ImageFilter.FIND_EDGES).resize(target_size)


def compare_edges(edges1, edges2):
    if edges1 is None or edges2 is None:
        return 0.0
    return max(0.0, _corr(list(edges1.getdata()), list(edges2.getdata())))


# Multi-scale query features ------------------------------------------------

def build_multi_scale_features(img, scales=(0.55, 0.75, 1.0)):
    if img is None:
        return None, None, None

    w, h = img.size
    des_list, edge_list = [], []
    hist_single = None

    for s in scales:
        nw, nh = int(w * s), int(h * s)
        if nw < 40 or nh < 40:
            continue
        resized = img.resize((nw, nh))
        gray = resized.convert("L")

        des_list.append(compute_descriptor(gray))
        edge_list.append(compute_edge_map(gray))

        if hist_single is None:
            hist_single = compute_histogram(resized)

    return des_list, edge_list, hist_single


# Multi-angle image-path helpers --------------------------------------------

# In-memory product catalog built from the DB on each scan so the matching
# loop always sees the freshest data.  Structure:
#
#   catalog = {
#       "infinix charger": {
#           "price": 450.0,
#           "images": [
#               "product_images/infinix_1.jpg",
#               "product_images/infinix_2.jpg",
#               "product_images/infinix_3.jpg",
#           ],
#           "row": <sqlite3.Row>,   # original DB row for stock / id
#       },
#       ...
#   }


def build_catalog():
    """Read the full inventory and return a product-name-keyed dict."""
    catalog = {}
    for row in get_all_products():
        row = dict(row)
        name = row.get("item_name", "")
        if not name:
            continue
        raw = (row.get("image_path") or "").strip()
        images = [
            p.strip() for p in raw.split("|") if p.strip() and os.path.isfile(p.strip())
        ]
        if not images:
            continue
        catalog[name] = {
            "price": row.get("price", 0),
            "images": images,
            "row": row,
        }
    return catalog


def get_image_paths(product):
    """
    Return a list of reference image paths for *product*.
    Supports a single path or multiple paths separated by ``|``
    (e.g. ``"front.jpg|back.jpg|side.jpg"``).
    """
    raw = product.get("image_path") or ""
    if not raw:
        return []
    parts = [p.strip() for p in raw.split("|") if p.strip()]
    return [p for p in parts if os.path.isfile(p)]


def _score_against_ref(q_des_list, q_edge_list, q_hist, ref_bytes):
    """Score one reference image against pre-computed query features."""
    ref_rgb = _decode_color(ref_bytes)
    if ref_rgb is None:
        return 0.0

    ref_gray = ref_rgb.convert("L")
    ref_des = compute_descriptor(ref_gray)
    ref_hist = compute_histogram(ref_rgb)
    ref_edge = compute_edge_map(ref_gray)

    # Descriptor — best across query scales
    des_score = 0
    if ref_des is not None and q_des_list:
        for q_des in q_des_list:
            cnt = match_descriptors(q_des, ref_des)
            if cnt > des_score:
                des_score = cnt
    des_norm = min(des_score / 100.0, 1.0)

    # Histogram (inherently scale-invariant)
    hist_score = compare_histograms(q_hist, ref_hist) if q_hist is not None else 0.0

    # Edges — best across query scales
    edge_score = 0.0
    if ref_edge is not None and q_edge_list:
        for q_edge in q_edge_list:
            sc = compare_edges(q_edge, ref_edge)
            if sc > edge_score:
                edge_score = sc

    combined = 0.30 * des_norm + 0.40 * hist_score + 0.30 * edge_score

    if des_score >= 30:
        combined = max(combined, 0.80)
    if hist_score >= 0.75:
        combined = max(combined, 0.75)
    if edge_score >= 0.80:
        combined = max(combined, 0.70)

    return combined


# Main matching entry point -------------------------------------------------

def find_best_match(uploaded_bytes, scales=(0.55, 0.75, 1.0)):
    """
    Multi-angle scale-invariant ensemble:
      1. Extract foreground bounding box.
      2. Build multi-scale query features (ORB / edge / histogram).
      3. Build an in-memory catalog from the DB where each product holds a
         **list** of reference-image paths (front, back, side, etc.).
      4. For each product, iterate through *all* its images and keep the
         **maximum** score across angles.
      5. Short-circuit: if any angle scores ≥ 0.75, lock that product
         immediately and return.
      6. Adaptive dominance thresholding for the final decision.

    Returns (product_row, confidence_0_100) or (None, score).
    """

    # ---------- 1.  Foreground extraction ----------
    fg_bytes = extract_foreground(uploaded_bytes)
    if fg_bytes is None:
        fg_bytes = uploaded_bytes

    bgr = _decode_color(fg_bytes)
    if bgr is None:
        return None, 0

    # ---------- 2.  Multi-scale query features ----------
    q_des_list, q_edge_list, q_hist = build_multi_scale_features(bgr, scales)
    if q_des_list is None and q_edge_list is None and q_hist is None:
        return None, 0

    # ---------- 3.  Build catalog (name → {price, images[], row}) ----------
    catalog = build_catalog()
    scored = []  # (combined_score, product_row)

    for prod_name, entry in catalog.items():
        images = entry["images"]
        best_angle_score = 0.0

        for angle_path in images:
            with open(angle_path, "rb") as f:
                ref_bytes = f.read()

            score = _score_against_ref(q_des_list, q_edge_list, q_hist, ref_bytes)
            if score > best_angle_score:
                best_angle_score = score

            # ----------  Short-circuit: ≥ 0.75 → instant lock ----------
            if best_angle_score >= 0.75:
                break

        scored.append((best_angle_score, entry["row"]))

        if best_angle_score >= 0.75:
            # This product is a near-certain match — short-circuit the
            # outer loop and return immediately.
            scored.sort(key=lambda x: x[0], reverse=True)
            return scored[0][1], 75

    if not scored:
        return None, 0

    # ----------  Adaptive dominance threshold ----------
    scored.sort(key=lambda x: x[0], reverse=True)
    best_row = scored[0][1]
    best_score = scored[0][0]

    dominance = 1.0
    if len(scored) > 1 and scored[1][0] > 0:
        dominance = best_score / scored[1][0]

    threshold = 0.28
    if dominance >= 1.8:
        threshold = 0.18

    if best_score >= threshold:
        return best_row, int(min(best_score, 1.0) * 100)
    return None, int(min(best_score, 1.0) * 100)


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

    # Process the image bytes from whichever source — runs ONCE
    if source_bytes is not None:
        with st.spinner("Identifying item..."):
            row, match_count = find_best_match(source_bytes)

        if row is not None:
            st.session_state.current_scan = row
            st.session_state.manual_select = row["item_name"]
            st.success(f"\u2705 Matched: **{row['item_name']}**  (score={match_count})")
        else:
            if match_count > 0:
                st.warning(
                    f"\u26a0\ufe0f No clear match found (best score={match_count}). "
                    "Please try again or select manually."
                )
            else:
                st.warning(
                    "\u26a0\ufe0f No clear match found. Please try again or select manually."
                )

    # -- Manual fallback dropdown (always available) --
    st.markdown("---")
    all_prods = get_all_products()
    prod_names = [p["item_name"] for p in all_prods]

    if prod_names:
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
                    st.rerun()
            if not matches:
                st.caption("No items found")
    else:
        st.info("No products in inventory yet. Go to the Admin tab to add some.")

    # -- Display scanned product & action buttons --
    scanned_product = st.session_state.current_scan

    if scanned_product is not None:
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

        if scanned_product["stock_quantity"] <= 0:
            st.error("OUT OF STOCK")
        else:
            # Fresh stock read from DB (guard against stale session data)
            fresh_prod = get_product_by_id(scanned_product["id"])
            db_stock = fresh_prod["stock_quantity"] if fresh_prod else 0

            # How many of this item already sit in the cart?
            already_in_cart = sum(
                item["qty"] for item in st.session_state.cart
                if item["id"] == scanned_product["id"]
            )
            remaining_stock = db_stock - already_in_cart

            if remaining_stock <= 0:
                st.warning("Cannot add to bill. No more units left in stock!")
            else:
                col_a, col_b = st.columns([1, 1])
                with col_a:
                    qty = st.number_input(
                        "Qty", min_value=1, max_value=remaining_stock, value=1,
                        key="add_qty"
                    )
                with col_b:
                    if st.button("\U0001f6d2 Add to Bill", use_container_width=True):
                        already_in_cart_now = sum(
                            item["qty"] for item in st.session_state.cart
                            if item["id"] == scanned_product["id"]
                        )
                        if already_in_cart_now + qty > db_stock:
                            st.error(
                                f"Cannot add to bill. Only {db_stock - already_in_cart_now} units left in stock!"
                            )
                        else:
                            cart_add(scanned_product, qty)
                            st.success(f"Added {qty} x {scanned_product['item_name']} to cart")
                            st.session_state.current_scan = None
                            st.session_state.scan_key += 1
                            st.session_state.search_key_counter += 1
                            st.rerun()

        # Independent reset button
        if st.button("\U0001f504 Reset Scanner", use_container_width=True):
            st.session_state.current_scan = None
            st.session_state.scan_key += 1
            st.rerun()

    else:
        st.info("Point your camera at an item or select one from the dropdown above.")

# ======================================================================
# TAB 2 : CURRENT BILL & CHECKOUT
# ======================================================================
with tab2:
    st.subheader("\U0001f4b0 Current Bill")

    if not st.session_state.cart:
        st.info("Cart is empty. Scan items from the first tab.")
    else:
        for i, item in enumerate(st.session_state.cart):
            current_qty = st.session_state.get(f"qty_{item['id']}_{i}", item["qty"])
            st.markdown(f"""
<div style="background:white; border:1px solid #eee; border-radius:12px; padding:14px 16px; margin-bottom:10px; box-shadow:0 1px 4px rgba(0,0,0,0.06);">
    <div style="display:flex; justify-content:space-between; align-items:center;">
        <span style="font-size:16px; font-weight:600; color:#222;">{item['name']}</span>
        <span style="font-size:15px; font-weight:700; color:#e74c3c;">\u20b9{item['price'] * current_qty:.2f}</span>
    </div>
    <div style="color:#888; font-size:13px; margin-top:4px;">
        \u20b9{item['price']:.2f} \u00d7 {current_qty} units
    </div>
</div>
""", unsafe_allow_html=True)
            col1, col2 = st.columns([4, 1])
            with col1:
                new_qty = st.number_input(
                    "", min_value=1, value=current_qty,
                    key=f"qty_{item['id']}_{i}", label_visibility="collapsed",
                )
            with col2:
                if st.button("\U0001f5d1\ufe0f", key=f"del_{item['id']}_{i}"):
                    st.session_state["cart"].pop(i)
                    st.rerun()
            if new_qty != item["qty"]:
                st.session_state["cart"][i]["qty"] = new_qty
                st.rerun()
        total = cart_total()
        st.markdown(f"""
<div style="background:#f8f9fa; border-radius:12px; padding:16px; margin:16px 0; display:flex; justify-content:space-between; align-items:center;">
    <span style="font-size:18px; font-weight:600;">Total</span>
    <span style="font-size:22px; font-weight:700; color:#e74c3c;">\u20b9{total:.2f}</span>
</div>
""", unsafe_allow_html=True)

        # -- Action buttons --
        if st.button("\u2705 Confirm Purchase & Print Bill", type="primary", use_container_width=True):
            # Deduct stock
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
                # Build itemised list string
                item_parts = [f"{i['name']} x{i['qty']}" for i in st.session_state.cart]
                items_str = ", ".join(item_parts)
                grand_total = cart_total()

                # Save to history
                save_transaction(items_str, grand_total)

                # Digital receipt
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
                cart_clear()
                st.rerun()

        if st.button("\U0001f5d1 Clear Cart", use_container_width=True):
            cart_clear()
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
        st.info("Inventory is empty. Add your first product above.")
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

        col_save, col_del, _ = st.columns([1, 1, 4])
        with col_save:
            save_clicked = st.button("\U0001f4be Save All Changes", type="primary", use_container_width=True)
        with col_del:
            delete_clicked = st.button("\u274c Delete Selected", use_container_width=True)

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

        # Low-stock warning
        low = [r[1] for r in all_rows if r[4] <= 5]
        low_running = [r[1] for r in all_rows if 5 < r[4] <= 20]
        if low:
            st.warning(f"\u26a0\ufe0f Low stock: {', '.join(low)}")
        if low_running:
            st.info(f"\U0001f550 Running low: {', '.join(low_running)}")
